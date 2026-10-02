"""Independent cached-metadata audit checks; no network or financial inputs.

Run only against a terminal audit attempt after the root authorizes verification.
The reconstruction and comparisons use stdlib, not audit implementation imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET_ENVELOPE_START = "2012-01-01"
ET_ENVELOPE_END = "2025-12-31"
MICROS = 1_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def utc_clock(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def item_tokens(row):
    if "items" not in row or row["items"] is None:
        return None
    value = row["items"]
    if not isinstance(value, str) or not value.strip():
        return None
    tokens = [token.strip() for token in value.split(",")]
    if any(not re.fullmatch(r"[0-9]+\.[0-9]{2}", token) for token in tokens):
        return None
    return tokens


def delta_micros(q_clock, k_clock):
    elapsed = k_clock - q_clock
    return (elapsed.days * 86400 + elapsed.seconds) * MICROS + elapsed.microseconds


def classify(q_clock, k_clock, preceding_seconds, late_seconds):
    if q_clock is None or k_clock is None:
        return "unavailable", None
    value = delta_micros(q_clock, k_clock)
    if value == 0:
        category = "same_clock"
    elif -preceding_seconds * MICROS <= value < 0:
        category = "preceding"
    elif 0 < value <= late_seconds * MICROS:
        category = "late"
    elif value < 0:
        category = "outside_before"
    else:
        category = "outside_after"
    return category, value / MICROS


def parallel_rows(table):
    assert isinstance(table, dict), "Metadata table is not a dictionary"
    columns = list(table)
    assert {"accessionNumber", "form", "filingDate"} <= set(columns)
    assert all(isinstance(table[key], list) for key in columns)
    size = len(table["accessionNumber"])
    assert all(len(table[key]) == size for key in columns), "Unequal metadata arrays"
    return [dict(zip(columns, values)) for values in zip(*(table[key] for key in columns))]


def json_lines(path):
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            assert line.strip(), f"Blank JSONL row at {path}:{number}"
            yield json.loads(line)


def source_path(repo, source_root, source):
    return (
        (
            repo
            if source.get("reused") or source["path"].startswith(".qualification/")
            else source_root
        )
        / source["path"]
    ).resolve()


def selected_history_descriptors(files, cik, request):
    assert isinstance(files, list)
    selected = []
    interval_start = datetime.strptime(request["filed_from"], "%Y-%m-%d").date()
    interval_end = datetime.strptime(request["filed_through"], "%Y-%m-%d").date()
    for descriptor in files:
        assert re.fullmatch(r"CIK" + cik + r"-submissions-[0-9]+\.json", descriptor["name"])
        lower = datetime.strptime(descriptor["filingFrom"], "%Y-%m-%d").date()
        upper = datetime.strptime(descriptor["filingTo"], "%Y-%m-%d").date()
        assert lower <= upper
        if lower <= interval_end and upper >= interval_start:
            selected.append(descriptor)
    return selected


def origin_record(relative, url, raw_sha, raw_length, page_number, row_number, descriptor):
    return {
        "source_path": relative,
        "source_url": url,
        "source_sha256": raw_sha,
        "source_bytes": raw_length,
        "page_ordinal": page_number,
        "row_ordinal": row_number,
        "table": "filings.recent" if page_number == 0 else "history",
        "history_descriptor": descriptor,
    }


def reconstruct(repo, definition):
    source_root = repo / definition["source_root"]
    registry = read_json(source_root / "registry.json")
    request = read_json(source_root / "request.json")
    completion = read_json(source_root / "completion.json")
    assert not (source_root / "STOP.json").exists(), "Unreconciled source STOP"
    assert completion["status"] in {
        "captured",
        "incomplete",
        "captured_with_coverage_review_needed",
    }
    members = definition["membership"]
    assert request["issuers"] == members
    assert [item["issuer"] for item in registry["issuers"]] == members
    assert registry["request_sha256"] == digest(source_root / "request.json")
    assert len(members) == len({item["cik"] for item in members}) == 100
    originals = []
    groups = {}
    raw_paths = set()
    occurrences = 0
    original_origins = {}
    for item in registry["issuers"]:
        issuer, discovery = item["issuer"], item["discovery"]
        reconstructed = []
        acc_variants = defaultdict(dict)
        selected_history = None
        for page_number, source in enumerate(discovery["sources"]):
            path = source_path(repo, source_root, source)
            relative = path.relative_to(repo).as_posix()
            raw = path.read_bytes()
            assert source["status"] == 200
            assert len(raw) == source["bytes"]
            assert hashlib.sha256(raw).hexdigest() == source["sha256"]
            assert definition["inputs"][relative] == source["sha256"]
            raw_paths.add(relative)
            body = json.loads(raw)
            if page_number == 0:
                assert source["url"] == f"https://data.sec.gov/submissions/CIK{issuer['cik']}.json"
                assert str(body["cik"]).zfill(10) == issuer["cik"]
                assert issuer["symbol"] in body["tickers"]
                selected_history = selected_history_descriptors(
                    body["filings"]["files"], issuer["cik"], request
                )
                assert len(selected_history) == len(discovery["sources"]) - 1
                descriptor = None
                table = body["filings"]["recent"]
            else:
                assert selected_history is not None
                descriptor = selected_history[page_number - 1]
                assert source["url"] == "https://data.sec.gov/submissions/" + descriptor["name"]
                if "cik" in body:
                    assert str(body["cik"]).zfill(10) == issuer["cik"]
                assert re.fullmatch(
                    r"https://data\.sec\.gov/submissions/CIK"
                    + issuer["cik"]
                    + r"-submissions-\d+\.json",
                    source["url"],
                )
                table = body
            rows = parallel_rows(table)
            reconstructed.extend(rows)
            for row_number, row in enumerate(rows):
                occurrences += 1
                key = canonical(row)
                origin = origin_record(
                    relative,
                    source["url"],
                    hashlib.sha256(raw).hexdigest(),
                    len(raw),
                    page_number,
                    row_number,
                    descriptor,
                )
                variants = acc_variants[row["accessionNumber"]]
                if key not in variants:
                    variants[key] = {"row": row, "origins": []}
                variants[key]["origins"].append(origin)
        assert canonical(reconstructed) == canonical(discovery["rows"]), "Registry/raw rows differ"
        for row in discovery["original_accessions"]:
            assert row["form"] == "10-Q"
            assert request["filed_from"] <= row["filingDate"] <= request["filed_through"]
            variants = acc_variants[row["accessionNumber"]]
            assert canonical(row) in variants
            original_origins[(issuer["cik"], row["accessionNumber"])] = variants[canonical(row)][
                "origins"
            ]
            originals.append(
                {
                    "symbol": issuer["symbol"],
                    "cik": issuer["cik"],
                    "accession": row["accessionNumber"],
                    "filingDate": row["filingDate"],
                    "reportDate": row.get("reportDate"),
                }
            )
        for accession, variants in acc_variants.items():
            if any(variant["row"].get("form") in {"8-K", "8-K/A"} for variant in variants.values()):
                groups[(issuer["cik"], accession)] = {"issuer": issuer, "variants": variants}
    assert originals == definition["requested_events"]
    assert len(originals) == definition["requested_originals"] == 4057
    assert len(raw_paths) == definition["raw_discovery_unique_inputs"] == 179
    return registry, groups, occurrences, original_origins


def expected_group_row(group):
    variants = group["variants"]
    return next(iter(variants.values()))["row"] if len(variants) == 1 else None


def clock_status(row):
    if row is None:
        return "conflicting_metadata"
    if "acceptanceDateTime" not in row:
        return "missing"
    value = row["acceptanceDateTime"]
    if value is None:
        return "null"
    if not isinstance(value, str):
        return "invalid_type"
    if value == "":
        return "empty"
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (ValueError, OverflowError):
        return "invalid_encoding"
    return "naive" if parsed.tzinfo is None or parsed.utcoffset() is None else "aware"


def item_status(row):
    if row is None:
        return "conflicting_metadata"
    if "items" not in row:
        return "missing"
    if row["items"] is None:
        return "null"
    if not isinstance(row["items"], str):
        return "invalid_type"
    if not row["items"].strip():
        return "empty"
    tokens = item_tokens(row)
    if tokens is None:
        return "invalid_encoding"
    return "qualified_token" if "2.02" in tokens else "valid_nonmatching"


def metadata_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def verify_output_identities(attempt, completion):
    outputs = completion["outputs"]
    assert isinstance(outputs, dict) and outputs, "Terminal outputs identities missing"
    for name, record in outputs.items():
        path = attempt / name
        assert path.resolve().parent == attempt.resolve(), "Unexpected completion output path"
        assert path.stat().st_size == record["bytes"]
        assert digest(path) == record["sha256"], "Output identity mismatch: " + name
    required = {
        "events.json",
        "metadata-records.jsonl",
        "pairs.jsonl",
        "issuer-year-denominators.json",
        "report.json",
        "report.md",
    }
    assert required <= set(outputs), "Required outputs omitted from completion"
    return len(outputs)


def verify(repo, definition_path, attempt):
    prior_checker = Path(__file__).with_name("independent_check.py")
    assert (
        digest(prior_checker) == "e49032b1ee619c5bac3ca46f88c9093fad563c7e003f7293d15da0420985bf39"
    )
    prior_review = Path(__file__).parent / "review"
    prior_failure_identities = {
        name: digest(prior_review / name)
        for name in ["attempt.json", "failure.json", "stdout.txt", "stderr.txt"]
    }
    definition = read_json(definition_path)
    clarification_path = definition_path.parent / "clarification.json"
    clarification = read_json(clarification_path)
    completion = read_json(attempt / "completion.json")
    assert completion["status"] == "complete", "Audit attempt is not terminal/complete"
    assert completion["definition_sha256"] == digest(definition_path)
    assert completion["clarification_sha256"] == digest(clarification_path)
    output_count = verify_output_identities(attempt, completion)
    assert clarification["definition_sha256"] == digest(definition_path)
    assert definition["network_requests_allowed"] == 0
    assert definition["economic_paths_allowed"] == 0
    assert definition["document_requests_allowed"] == 0
    assert definition["source_writes_allowed"] is False
    for relative, expected in definition["inputs"].items():
        assert digest(repo / relative) == expected, "Changed frozen input: " + relative
    registry, groups, occurrence_count, original_origins = reconstruct(repo, definition)
    metadata = {}
    known_group_rows = {}
    group_clocks = {}
    group_tokens = {}
    group_item_status = {}
    for observed in json_lines(attempt / "metadata-records.jsonl"):
        key = observed["cik"], observed["accession"]
        assert key in groups and key not in metadata, "Unexpected or duplicate metadata group"
        expected = groups[key]
        assert observed["symbol"] == expected["issuer"]["symbol"]
        assert observed["group_id"] == ":".join(key)
        assert observed["conflicting_metadata"] == (len(expected["variants"]) > 1)
        variants = {canonical(variant["row"]): variant for variant in observed["variants"]}
        assert len(variants) == len(observed["variants"])
        assert set(variants) == set(expected["variants"]), "Missing or changed row variant"
        for identity, original in expected["variants"].items():
            assert Counter(map(canonical, variants[identity]["origins"])) == Counter(
                map(canonical, original["origins"])
            )
        row = expected_group_row(expected)
        clock = utc_clock(row.get("acceptanceDateTime")) if row else None
        tokens = item_tokens(row) if row else None
        status = item_status(row)
        assert canonical(observed["row"]) == canonical(row)
        assert observed["form"] == (row.get("form") if row else None)
        assert observed["items"]["status"] == status
        if tokens is not None:
            assert observed["items"]["tokens"] == tokens
        saved_clock = utc_clock(observed["api_clock"]["utc"])
        assert saved_clock == clock
        assert observed["api_clock"]["status"] == clock_status(row)
        if clock is None:
            assert observed["api_clock"]["utc"] is None
        metadata[key] = observed
        known_group_rows[key] = row
        group_clocks[key] = clock
        group_tokens[key] = tokens
        group_item_status[key] = status
    assert set(metadata) == set(groups), "Metadata group completeness failure"
    events = read_json(attempt / "events.json")
    requested = definition["requested_events"]
    assert len(events) == len(requested)
    event_map = {}
    original_rows = {
        (item["issuer"]["cik"], row["accessionNumber"]): row
        for item in registry["issuers"]
        for row in item["discovery"]["original_accessions"]
    }
    by_cik = defaultdict(list)
    for key in groups:
        by_cik[key[0]].append(key)
    expected_pairs = {}
    expected_event_audits = {}
    full_pair_count = 0
    primary_total = 0
    preceding_seconds = definition["criteria"]["preceding_window_seconds"]
    late_seconds = definition["criteria"]["late_window_seconds"]
    assert preceding_seconds == 45 * 86400 and late_seconds == 7 * 86400
    for expected, observed in zip(requested, events):
        key = expected["cik"], expected["accession"]
        assert observed["cik"] == key[0] and observed["accession"] == key[1]
        assert observed["symbol"] == expected["symbol"]
        assert observed["event_id"] == ":".join(key)
        assert canonical(observed["original_row"]) == canonical(original_rows[key])
        assert Counter(map(canonical, observed["original_origins"])) == Counter(
            map(canonical, original_origins[key])
        )
        manifest_path = (
            repo / definition["source_root"] / "filings" / expected["symbol"] / (key[1] + ".json")
        )
        manifest = read_json(manifest_path)
        annotation = observed["manifest_annotation"]
        assert annotation.get("status") == manifest.get("status")
        assert annotation.get("error") == manifest.get("error")
        assert annotation.get("clock") == manifest.get("clock")
        assert key not in event_map
        event_map[key] = observed
        q_clock = utc_clock(original_rows[key].get("acceptanceDateTime"))
        assert utc_clock(observed["api_clock"]["utc"]) == q_clock
        assert observed["api_clock"]["status"] == clock_status(original_rows[key])
        if q_clock is None:
            assert observed["api_clock"]["utc"] is None
        coverage = observed["window_coverage"]
        assert coverage["source_filed_from"] == ET_ENVELOPE_START
        assert coverage["source_filed_through"] == ET_ENVELOPE_END
        assert coverage["unknown"] == (q_clock is None)
        if q_clock:
            lower_date = (
                (q_clock - timedelta(seconds=preceding_seconds))
                .astimezone(ZoneInfo("America/New_York"))
                .date()
                .isoformat()
            )
            upper_date = (
                (q_clock + timedelta(seconds=late_seconds))
                .astimezone(ZoneInfo("America/New_York"))
                .date()
                .isoformat()
            )
            assert coverage["before_source_envelope"] == (lower_date < ET_ENVELOPE_START)
            assert coverage["after_source_envelope"] == (upper_date > ET_ENVELOPE_END)
        all_timing, original_timing, amendment_timing, items = (
            Counter(),
            Counter(),
            Counter(),
            Counter(),
        )
        unavailable, preceding_ids, same_ids, late_ids = set(), set(), set(), set()
        for k_key in by_cik[key[0]]:
            full_pair_count += 1
            k_row = known_group_rows[k_key]
            timing, elapsed = classify(
                q_clock, group_clocks[k_key], preceding_seconds, late_seconds
            )
            tokens = group_tokens[k_key]
            matches = tokens is not None and "2.02" in tokens
            original = bool(k_row and k_row.get("form") == "8-K")
            amendment = bool(k_row and k_row.get("form") == "8-K/A")
            primary = bool(original and matches and timing == "preceding")
            group_id = ":".join(k_key)
            all_timing[timing] += 1
            items[group_item_status[k_key]] += 1
            if original and matches:
                original_timing[timing] += 1
                if timing == "preceding":
                    preceding_ids.add(":".join(key) + "|" + group_id)
                elif timing == "same_clock":
                    same_ids.add(":".join(key) + "|" + group_id)
                elif timing == "late":
                    late_ids.add(":".join(key) + "|" + group_id)
            if amendment and matches:
                amendment_timing[timing] += 1
            if timing == "unavailable":
                unavailable.add(group_id)
            primary_total += int(primary)
            if timing in {"preceding", "same_clock", "late"}:
                expected_pairs[(key, k_key)] = (timing, elapsed, primary, amendment)
        expected_status = (
            "q_clock_unavailable"
            if q_clock is None
            else "multiple_preceding_candidates"
            if len(preceding_ids) > 1
            else "preceding_candidate_observed"
            if preceding_ids
            else "same_or_late_only"
            if same_ids or late_ids
            else "no_observed_candidate"
        )
        assert observed["status"] == expected_status
        assert observed["unknown_undiscovered_disclosures"] is None
        assert coverage["complete_coverage_verified"] is False
        expected_event_audits[key] = {
            "status": expected_status,
            "manifest_status": str(manifest.get("status")),
            "q_clock_status": clock_status(original_rows[key]),
            "preceding_pairs": len(preceding_ids),
        }
        assert Counter(observed["group_timing_counts"]) == all_timing
        assert Counter(observed["original_item202_timing_counts"]) == original_timing
        assert Counter(observed["amendment_item202_timing_counts"]) == amendment_timing
        assert Counter(observed["item_status_counts"]) == items
        for field, wanted in [
            ("unavailable_group_ids", unavailable),
            ("preceding_candidate_ids", preceding_ids),
            ("same_clock_item202_ids", same_ids),
            ("late_item202_ids", late_ids),
        ]:
            assert len(observed[field]) == len(set(observed[field]))
            assert set(observed[field]) == wanted, "Q group reference mismatch: " + field
    seen_pairs = set()
    for pair in json_lines(attempt / "pairs.jsonl"):
        event_key = pair["cik"], pair["q_accession"]
        k_key = pair["cik"], pair["k_accession"]
        pair_key = event_key, k_key
        assert pair_key in expected_pairs and pair_key not in seen_pairs, (
            "Unexpected/duplicate window pair"
        )
        seen_pairs.add(pair_key)
        timing, elapsed, primary, amendment = expected_pairs[pair_key]
        assert pair["timing"] == timing
        assert pair["elapsed_seconds"] == elapsed
        assert pair["primary_candidate"] is primary
        assert pair["event_id"] == ":".join(event_key)
        assert pair["pair_id"] == ":".join(event_key) + "|" + ":".join(k_key)
        assert pair["k_group_id"] == ":".join(k_key)
        assert pair["symbol"] == event_map[event_key]["symbol"]
        assert pair["fiscal_period_verified"] is False
        assert pair["disclosed_components_verified"] is False
        assert pair["amendment"] == amendment
        assert pair["q_reportDate"] == original_rows[event_key].get("reportDate")
        assert pair["k_reportDate"] == known_group_rows[k_key].get("reportDate")
        assert pair["public_dissemination_instant_verified"] is False
        assert pair["k_items_status"] == group_item_status[k_key]
        q_date = metadata_date(original_rows[event_key].get("reportDate"))
        k_date = metadata_date(known_group_rows[k_key].get("reportDate"))
        relation = (
            "unavailable"
            if not q_date or not k_date
            else ("equal_metadata_dates" if q_date == k_date else "different_metadata_dates")
        )
        assert pair["reportDate_relation"] == relation
    assert seen_pairs == set(expected_pairs), "Window-pair completeness failure"
    denominator_rows = read_json(attempt / "issuer-year-denominators.json")
    wanted_denominators = {
        (member["cik"], str(year)): {"symbol": member["symbol"], "count": 0}
        for member in definition["membership"]
        for year in range(2012, 2026)
    }
    for item in wanted_denominators.values():
        item.update(
            status_counts=Counter(),
            manifest_status_counts=Counter(),
            q_clock_status_counts=Counter(),
            preceding_candidate_events=0,
            multiple_preceding_candidate_events=0,
            original_preceding_pairs=0,
        )
    for row in requested:
        year_record = wanted_denominators[(row["cik"], row["filingDate"][:4])]
        year_record["count"] += 1
        audit = expected_event_audits[(row["cik"], row["accession"])]
        year_record["status_counts"][audit["status"]] += 1
        year_record["manifest_status_counts"][audit["manifest_status"]] += 1
        year_record["q_clock_status_counts"][audit["q_clock_status"]] += 1
        year_record["preceding_candidate_events"] += int(audit["preceding_pairs"] > 0)
        year_record["multiple_preceding_candidate_events"] += int(audit["preceding_pairs"] > 1)
        year_record["original_preceding_pairs"] += audit["preceding_pairs"]
    seen_denominators = set()
    for row in denominator_rows:
        key = row["cik"], str(row["filed_year"])
        assert key in wanted_denominators and key not in seen_denominators
        seen_denominators.add(key)
        assert row["symbol"] == wanted_denominators[key]["symbol"]
        assert row["requested_originals"] == wanted_denominators[key]["count"]
        for name in ["status_counts", "manifest_status_counts", "q_clock_status_counts"]:
            assert Counter(row[name]) == wanted_denominators[key][name]
        for name in [
            "preceding_candidate_events",
            "multiple_preceding_candidate_events",
            "original_preceding_pairs",
        ]:
            assert row[name] == wanted_denominators[key][name]
        assert row["unknown_undiscovered_disclosures"] is None
        assert row["unknown_undiscovered_originals"] is None
        assert row["fiscal_period_verified"] is False
        assert row["disclosed_components_verified"] is False
        issuer_discovery = next(
            item["discovery"] for item in registry["issuers"] if item["issuer"]["cik"] == key[0]
        )
        assert row["source_window_complete_flag"] == issuer_discovery["complete"]
    assert seen_denominators == set(wanted_denominators)
    report = read_json(attempt / "report.json")
    assert report["status"] == "complete"
    assert report["definition_sha256"] == digest(definition_path)
    assert report["clarification_sha256"] == digest(clarification_path)
    assert report["implementation_sha256"] == completion["implementation_sha256"]
    expected_report = {
        "requested_issuers": len(definition["membership"]),
        "requested_originals": len(events),
        "original_discovery_sources": definition["raw_discovery_unique_inputs"],
        "metadata_groups": len(groups),
        "conflicting_metadata_groups": sum(len(group["variants"]) > 1 for group in groups.values()),
        "metadata_raw_occurrences": sum(
            len(variant["origins"])
            for group in groups.values()
            for variant in group["variants"].values()
        ),
        "original_preceding_candidate_pairs": primary_total,
        "events_with_preceding_candidates": sum(
            audit["preceding_pairs"] > 0 for audit in expected_event_audits.values()
        ),
        "events_with_multiple_preceding_candidates": sum(
            audit["preceding_pairs"] > 1 for audit in expected_event_audits.values()
        ),
        "before_source_envelope_events": sum(
            event["window_coverage"]["before_source_envelope"] is True for event in events
        ),
        "after_source_envelope_events": sum(
            event["window_coverage"]["after_source_envelope"] is True for event in events
        ),
        "source_envelope_unknown_events": sum(
            event["window_coverage"]["unknown"] for event in events
        ),
        "issuer_year_rows": len(denominator_rows),
        "network_requests": 0,
        "documents_requested": 0,
        "economic_paths": 0,
        "financial_facts_extracted": False,
        "prices_or_returns_read": False,
        "fiscal_period_verified": False,
        "disclosed_components_verified": False,
    }
    for name, expected in expected_report.items():
        assert report[name] == expected, "Aggregate report mismatch: " + name
    expected_counters = {
        "event_status_counts": Counter(audit["status"] for audit in expected_event_audits.values()),
        "manifest_status_counts": Counter(
            audit["manifest_status"] for audit in expected_event_audits.values()
        ),
        "q_api_clock_status_counts": Counter(
            audit["q_clock_status"] for audit in expected_event_audits.values()
        ),
        "k_item_status_counts": Counter(group_item_status.values()),
        "k_api_clock_status_counts": Counter(
            clock_status(row) for row in known_group_rows.values()
        ),
        "pair_timing_counts": Counter(values[0] for values in expected_pairs.values()),
    }
    for name, expected in expected_counters.items():
        assert Counter(report[name]) == expected, "Aggregate counter mismatch: " + name
    for relative, expected in definition["inputs"].items():
        assert digest(repo / relative) == expected, (
            "Frozen input changed during checker: " + relative
        )
    verify_output_identities(attempt, completion)
    return {
        "schema": 1,
        "status": "passed",
        "checker_version": 2,
        "checker_sha256": digest(Path(__file__)),
        "prior_checker_sha256": digest(prior_checker),
        "prior_failed_review": prior_review.relative_to(repo).as_posix(),
        "prior_failure_identities": prior_failure_identities,
        "revision_rationale": (
            "Frozen v1 compared five reconstructed origin fields with eight saved fields. "
            "V2 derives source_bytes from verified raw length, table from root/history kind, "
            "and history_descriptor from exact ordered overlapping original root descriptors. "
            "Full origin equality remains required; source/audit/output/v1 failure retained."
        ),
        "definition_sha256": digest(definition_path),
        "clarification_sha256": digest(clarification_path),
        "completion_sha256": digest(attempt / "completion.json"),
        "terminal_output_identities": output_count,
        "frozen_input_identities": len(definition["inputs"]),
        "requested_originals": len(events),
        "issuer_year_denominators": len(denominator_rows),
        "discovery_row_occurrences": occurrence_count,
        "metadata_groups": len(metadata),
        "full_cartesian_pairs_checked": full_pair_count,
        "serialized_window_pairs": len(seen_pairs),
        "primary_candidate_pairs": primary_total,
        "scope": (
            "Independent frozen identities, raw reconstruction/origins, requests/Q annotations, "
            "issuer/year denominators, full Cartesian category counts and exact serialized window "
            "union; no facts/outcomes/network."
        ),
    }


def origin_shape_regression():
    cik = "0000000001"
    descriptor = {
        "name": "CIK0000000001-submissions-001.json",
        "filingCount": 2,
        "filingFrom": "2012-01-01",
        "filingTo": "2013-12-31",
    }
    outside = {
        "name": "CIK0000000001-submissions-002.json",
        "filingCount": 1,
        "filingFrom": "2009-01-01",
        "filingTo": "2011-12-31",
    }
    selected = selected_history_descriptors(
        [descriptor, outside], cik, {"filed_from": "2012-01-01", "filed_through": "2025-12-31"}
    )
    assert selected == [descriptor]
    raw = b'{"parallel_arrays":"synthetic_only"}'
    raw_hash = hashlib.sha256(raw).hexdigest()
    root = origin_record("root.bin", "root-url", raw_hash, len(raw), 0, 7, None)
    expected_root = {
        "source_path": "root.bin",
        "source_url": "root-url",
        "source_sha256": raw_hash,
        "source_bytes": len(raw),
        "page_ordinal": 0,
        "row_ordinal": 7,
        "table": "filings.recent",
        "history_descriptor": None,
    }
    assert root == expected_root
    history = origin_record("history.bin", "history-url", raw_hash, len(raw), 1, 0, selected[0])
    expected_history = {
        "source_path": "history.bin",
        "source_url": "history-url",
        "source_sha256": raw_hash,
        "source_bytes": len(raw),
        "page_ordinal": 1,
        "row_ordinal": 0,
        "table": "history",
        "history_descriptor": descriptor,
    }
    assert history == expected_history
    for field in ["source_bytes", "table", "history_descriptor"]:
        damaged = dict(history)
        damaged[field] = None
        assert Counter(map(canonical, [damaged])) != Counter(map(canonical, [expected_history]))


def self_test():
    origin_shape_regression()
    q = utc_clock("2020-03-08T12:00:00Z")
    before, late = 45 * 86400, 7 * 86400
    for seconds, expected in [
        (-before - 1, "outside_before"),
        (-before, "preceding"),
        (-1, "preceding"),
        (0, "same_clock"),
        (1, "late"),
        (late, "late"),
        (late + 1, "outside_after"),
    ]:
        assert classify(q, q + timedelta(seconds=seconds), before, late)[0] == expected
    assert utc_clock("2020-03-08T08:00:00-04:00") == q
    assert utc_clock("2020-03-08T12:00:00") is None
    assert utc_clock(None) is None
    assert utc_clock("invalid") is None
    assert item_tokens({"items": "2.02, 9.01"}) == ["2.02", "9.01"]
    assert "2.02" not in item_tokens({"items": "12.02"})
    assert item_tokens({"items": "2.020"}) is None
    assert item_tokens({"items": "2.02,,9.01"}) is None
    assert item_tokens({"items": 2.02}) is None
    assert item_tokens({}) is None
    assert canonical({"flag": True}) != canonical({"flag": 1})
    assert (
        parallel_rows({"accessionNumber": ["a"], "form": ["8-K"], "filingDate": ["2020-01-01"]})[0][
            "form"
        ]
        == "8-K"
    )
    try:
        parallel_rows({"accessionNumber": ["a"], "form": [], "filingDate": ["2020-01-01"]})
    except AssertionError:
        pass
    else:
        raise AssertionError("Mismatched parallel arrays were accepted")
    print(json.dumps({"status": "passed", "synthetic_only": True, "actual_sources_read": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--definition", type=Path)
    parser.add_argument("--attempt", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.definition or not args.attempt or not args.report:
        parser.error("Verification requires --definition, --attempt and a new --report path")
    if args.report.exists():
        raise FileExistsError("Refusing to overwrite an existing review report")
    repo = Path(__file__).resolve().parents[2]
    result = verify(repo, args.definition.resolve(), args.attempt.resolve())
    with args.report.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

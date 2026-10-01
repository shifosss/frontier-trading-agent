"""Offline frozen SEC metadata timing audit; no facts, outcomes or transports."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import traceback
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFINITION_SHA256 = "3946aac2f8f4bd0ab697ae36ba9ce41ee117fb2d05b4e40d0fe0a6485902b9a3"
CLARIFICATION_SHA256 = "b02bad1b52da722e8885e2d0e6f97453afca6a95d320979c682f51ef474511d1"
PARSER_NAME = ".qualification/filing-source20260928/capture.py"
BEFORE_SECONDS = 45 * 86400
AFTER_SECONDS = 7 * 86400
WINDOW_TIMINGS = ("preceding", "same_clock", "late")
ALL_TIMINGS = WINDOW_TIMINGS + ("outside_before", "outside_after", "unavailable")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read(path):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Invalid JSON numeric constant: " + value)

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=object_pairs,
        parse_constant=invalid_constant,
    )


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def resolve(repo, name):
    path = (Path(repo) / name).resolve()
    path.relative_to(Path(repo).resolve())
    return path


def verify_inputs(repo, identities):
    for name, expected in identities.items():
        path = resolve(repo, name)
        if not path.is_file() or sha(path) != expected:
            raise ValueError("Bound input changed: " + name)


def load_parser(repo):
    spec = importlib.util.spec_from_file_location(
        "novelty_frozen_table_parser", resolve(repo, PARSER_NAME)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.table_rows


def required_code_paths(repo=REPO):
    # Import defines Cache but never constructs a transport.
    load_parser(repo)
    names = {
        Path(__file__).resolve().relative_to(Path(repo).resolve()).as_posix(),
        (HERE / "test_audit.py").resolve().relative_to(Path(repo).resolve()).as_posix(),
        PARSER_NAME,
    }
    names.update(
        Path(module.__file__).resolve().relative_to(Path(repo).resolve()).as_posix()
        for name, module in sys.modules.items()
        if name.startswith("frontier.") and getattr(module, "__file__", "").endswith(".py")
    )
    return sorted(names)


def api_clock(row):
    if "acceptanceDateTime" not in row:
        return {"status": "missing", "utc": None}
    value = row["acceptanceDateTime"]
    if value is None or value == "":
        return {"status": "null" if value is None else "empty", "utc": None}
    if not isinstance(value, str):
        return {"status": "invalid_type", "utc": None}
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return {"status": "naive", "utc": None}
        instant = instant.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return {"status": "invalid_encoding", "utc": None}
    return {"status": "aware", "utc": instant.isoformat()}


def item_tokens(row):
    if "items" not in row:
        return {"status": "missing", "tokens": []}
    value = row["items"]
    if value is None:
        return {"status": "null", "tokens": []}
    if not isinstance(value, str):
        return {"status": "invalid_type", "tokens": []}
    if not value.strip():
        return {"status": "empty", "tokens": []}
    tokens = [token.strip() for token in value.split(",")]
    if any(not re.fullmatch(r"[0-9]+\.[0-9]{2}", token) for token in tokens):
        return {"status": "invalid_encoding", "tokens": tokens}
    return {
        "status": "qualified_token" if "2.02" in tokens else "valid_nonmatching",
        "tokens": tokens,
    }


def group_rows(issuer, occurrences):
    groups = {}
    for row, origin in occurrences:
        accession = row["accessionNumber"]
        group = groups.setdefault(accession, {})
        variant = group.setdefault(canonical(row), {"row": row, "origins": []})
        variant["origins"].append(origin)
    result = []
    for accession, variants in groups.items():
        variants = list(variants.values())
        conflict = len(variants) > 1
        row = variants[0]["row"] if not conflict else None
        result.append(
            {
                "group_id": issuer["cik"] + ":" + accession,
                **issuer,
                "accession": accession,
                "conflicting_metadata": conflict,
                "variants": variants,
                "row": row,
                "form": row.get("form") if row is not None else None,
                "items": item_tokens(row)
                if row is not None
                else {"status": "conflicting_metadata", "tokens": []},
                "api_clock": api_clock(row)
                if row is not None
                else {"status": "conflicting_metadata", "utc": None},
            }
        )
    return result


def source_path(repo, source_root, meta):
    original = meta["path"]
    if Path(original).is_absolute():
        raise ValueError("Absolute raw source path is not allowed")
    name = (
        original
        if meta.get("reused") or original.replace("\\", "/").startswith(".qualification/")
        else (source_root.relative_to(repo) / original).as_posix()
    )
    return resolve(repo, name)


def reconstruct_discovery(definition, repo, table_rows):
    repo = Path(repo).resolve()
    source_root = resolve(repo, definition["source_root"])
    registry = read(source_root / "registry.json")
    request = read(source_root / "request.json")
    membership = definition["membership"]
    if (
        request["issuers"] != membership
        or [item["issuer"] for item in registry["issuers"]] != membership
    ):
        raise ValueError("Ordered issuer membership mismatch")
    if not registry["complete"] or registry["request_sha256"] != sha(source_root / "request.json"):
        raise ValueError("Terminal registry identity/completeness mismatch")
    declared_sources = definition["discovery_sources"]
    declared_by_url = {source["url"]: source for source in declared_sources}
    if len(declared_by_url) != len(declared_sources):
        raise ValueError("Duplicate declared discovery URL")
    used_sources, metadata, originals = [], [], []
    for item in registry["issuers"]:
        issuer, discovery = item["issuer"], item["discovery"]
        if discovery["complete"] is not True or discovery.get("error") is not None:
            raise ValueError("Issuer discovery is not terminal complete: " + issuer["symbol"])
        sources = discovery["sources"]
        if not sources:
            raise ValueError("Missing original root")
        root_url = "https://data.sec.gov/submissions/CIK" + issuer["cik"] + ".json"
        if sources[0]["url"] != root_url:
            raise ValueError("Root URL/CIK mismatch")
        occurrences, selected_history = [], None
        for page_ordinal, meta in enumerate(sources):
            declared = declared_by_url.get(meta["url"])
            path = source_path(repo, source_root, meta)
            name = path.relative_to(repo).as_posix()
            actual = {
                "symbol": issuer["symbol"],
                "cik": issuer["cik"],
                "url": meta["url"],
                "path": name,
                "sha256": meta["sha256"],
                "bytes": meta["bytes"],
            }
            if actual != declared or meta.get("status") != 200 or meta.get("error"):
                raise ValueError("Original discovery descriptor mismatch")
            if path.stat().st_size != meta["bytes"] or sha(path) != meta["sha256"]:
                raise ValueError("Original discovery raw identity mismatch")
            body = read(path)
            if page_ordinal == 0:
                if (
                    str(body["cik"]).zfill(10) != issuer["cik"]
                    or issuer["symbol"] not in body["tickers"]
                ):
                    raise ValueError("Root current CIK/ticker mismatch")
                if not isinstance(body["filings"]["files"], list):
                    raise ValueError("History descriptors are not a list")
                selected_history = []
                for descriptor in body["filings"]["files"]:
                    name_in_root = descriptor["name"]
                    if not isinstance(name_in_root, str) or not re.fullmatch(
                        r"CIK" + issuer["cik"] + r"-submissions-[0-9]+\.json", name_in_root
                    ):
                        raise ValueError("History descriptor CIK/name mismatch")
                    lower = datetime.strptime(descriptor["filingFrom"], "%Y-%m-%d").date()
                    upper = datetime.strptime(descriptor["filingTo"], "%Y-%m-%d").date()
                    if lower > upper:
                        raise ValueError("Reversed original history descriptor range")
                    if (
                        descriptor["filingFrom"] <= request["filed_through"]
                        and descriptor["filingTo"] >= request["filed_from"]
                    ):
                        selected_history.append(descriptor)
                if len(selected_history) != len(sources) - 1:
                    raise ValueError("History source/descriptor count mismatch")
                table = body["filings"]["recent"]
            else:
                descriptor = selected_history[page_ordinal - 1]
                expected_url = "https://data.sec.gov/submissions/" + descriptor["name"]
                if meta["url"] != expected_url:
                    raise ValueError("History URL/descriptor CIK mismatch")
                if "cik" in body and str(body["cik"]).zfill(10) != issuer["cik"]:
                    raise ValueError("History body CIK mismatch")
                table = body
            rows = table_rows(table)
            for row_ordinal, row in enumerate(rows):
                origin = {
                    "source_path": name,
                    "source_url": meta["url"],
                    "source_sha256": meta["sha256"],
                    "source_bytes": meta["bytes"],
                    "page_ordinal": page_ordinal,
                    "row_ordinal": row_ordinal,
                    "table": "filings.recent" if page_ordinal == 0 else "history",
                    "history_descriptor": None
                    if page_ordinal == 0
                    else selected_history[page_ordinal - 1],
                }
                occurrences.append((row, origin))
            used_sources.append(actual)
        raw_rows = [row for row, _ in occurrences]
        if canonical(raw_rows) != canonical(discovery["rows"]):
            raise ValueError("Reconstructed raw table/registry rows differ")
        groups = group_rows(issuer, occurrences)
        q_rows = [
            group["row"]
            for group in groups
            if group["row"] is not None
            and group["row"].get("form") == "10-Q"
            and request["filed_from"] <= group["row"]["filingDate"] <= request["filed_through"]
        ]
        q_rows.sort(
            key=lambda row: (
                row["filingDate"],
                row.get("acceptanceDateTime") or "",
                row["accessionNumber"],
            )
        )
        if canonical(q_rows) != canonical(discovery["original_accessions"]):
            raise ValueError("Reconstructed fixed original-Q membership differs")
        by_accession = {group["accession"]: group for group in groups}
        originals.extend((issuer, row, by_accession[row["accessionNumber"]]) for row in q_rows)
        metadata.extend(
            group
            for group in groups
            if any(variant["row"].get("form") in ("8-K", "8-K/A") for variant in group["variants"])
        )
    if (
        used_sources != declared_sources
        or len(used_sources) != definition["raw_discovery_unique_inputs"]
    ):
        raise ValueError("Ordered original discovery source identity mismatch")
    requested = [
        {
            "symbol": issuer["symbol"],
            "cik": issuer["cik"],
            "accession": row["accessionNumber"],
            "filingDate": row["filingDate"],
            "reportDate": row.get("reportDate"),
        }
        for issuer, row, _ in originals
    ]
    if (
        requested != definition["requested_events"]
        or len(originals) != definition["requested_originals"]
    ):
        raise ValueError("Requested original-Q denominator differs")
    return originals, metadata, request


def time_relation(q_clock, group):
    k_clock = group["api_clock"]
    if q_clock["status"] != "aware" or k_clock["status"] != "aware":
        return "unavailable", None
    delta = datetime.fromisoformat(k_clock["utc"]) - datetime.fromisoformat(q_clock["utc"])
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    if -BEFORE_SECONDS * 1000000 <= micros < 0:
        relation = "preceding"
    elif micros == 0:
        relation = "same_clock"
    elif 0 < micros <= AFTER_SECONDS * 1000000:
        relation = "late"
    else:
        relation = "outside_before" if micros < 0 else "outside_after"
    seconds = micros // 1000000 if micros % 1000000 == 0 else micros / 1000000
    return relation, seconds


def report_date(row):
    value = row.get("reportDate")
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def window_coverage(clock, request):
    result = {
        "source_filed_from": request["filed_from"],
        "source_filed_through": request["filed_through"],
        "unknown": clock["status"] != "aware",
        "before_source_envelope": None,
        "after_source_envelope": None,
        "complete_coverage_verified": False,
    }
    if clock["status"] == "aware":
        instant = datetime.fromisoformat(clock["utc"])
        eastern = ZoneInfo("America/New_York")
        result["before_source_envelope"] = (instant - timedelta(seconds=BEFORE_SECONDS)).astimezone(
            eastern
        ).date().isoformat() < request["filed_from"]
        result["after_source_envelope"] = (instant + timedelta(seconds=AFTER_SECONDS)).astimezone(
            eastern
        ).date().isoformat() > request["filed_through"]
    return result


def evaluate_event(issuer, q_row, q_group, manifest, groups, request):
    event_id = issuer["cik"] + ":" + q_row["accessionNumber"]
    q_clock = api_clock(q_row)
    event = {
        "event_id": event_id,
        **issuer,
        "accession": q_row["accessionNumber"],
        "original_row": q_row,
        "original_origins": q_group["variants"][0]["origins"],
        "api_clock": q_clock,
        "manifest_annotation": {
            "status": manifest.get("status"),
            "error": manifest.get("error"),
            "clock": manifest.get("clock"),
        },
        "window_coverage": window_coverage(q_clock, request),
        "unknown_undiscovered_disclosures": None,
        "group_timing_counts": dict.fromkeys(ALL_TIMINGS, 0),
        "original_item202_timing_counts": dict.fromkeys(ALL_TIMINGS, 0),
        "amendment_item202_timing_counts": dict.fromkeys(ALL_TIMINGS, 0),
        "item_status_counts": {},
        "unavailable_group_ids": [],
        "preceding_candidate_ids": [],
        "same_clock_item202_ids": [],
        "late_item202_ids": [],
    }
    pairs = []
    item_counts = Counter()
    for group in groups:
        timing, elapsed = time_relation(q_clock, group)
        event["group_timing_counts"][timing] += 1
        item_counts[group["items"]["status"]] += 1
        original, amendment = group["form"] == "8-K", group["form"] == "8-K/A"
        token = group["items"]["status"] == "qualified_token"
        if token and original:
            event["original_item202_timing_counts"][timing] += 1
        if token and amendment:
            event["amendment_item202_timing_counts"][timing] += 1
        if timing == "unavailable":
            event["unavailable_group_ids"].append(group["group_id"])
        if timing not in WINDOW_TIMINGS:
            continue
        primary = original and token and timing == "preceding"
        pair_id = event_id + "|" + group["group_id"]
        q_period, k_period = report_date(q_row), report_date(group["row"])
        period_relation = (
            "unavailable"
            if q_period is None or k_period is None
            else "equal_metadata_dates"
            if q_period == k_period
            else "different_metadata_dates"
        )
        reasons = []
        if not original:
            reasons.append("amendment_excluded")
        if not token:
            reasons.append("item202_not_qualified")
        if timing != "preceding":
            reasons.append("not_strictly_preceding")
        pair = {
            "pair_id": pair_id,
            "event_id": event_id,
            **issuer,
            "q_accession": q_row["accessionNumber"],
            "k_accession": group["accession"],
            "k_group_id": group["group_id"],
            "timing": timing,
            "elapsed_seconds": elapsed,
            "primary_candidate": primary,
            "amendment": amendment,
            "k_items_status": group["items"]["status"],
            "exclusion_reasons": reasons,
            "q_reportDate": q_row.get("reportDate"),
            "k_reportDate": group["row"].get("reportDate"),
            "reportDate_relation": period_relation,
            "fiscal_period_verified": False,
            "disclosed_components_verified": False,
            "public_dissemination_instant_verified": False,
        }
        pairs.append(pair)
        if primary:
            event["preceding_candidate_ids"].append(pair_id)
        elif original and token and timing == "same_clock":
            event["same_clock_item202_ids"].append(pair_id)
        elif original and token and timing == "late":
            event["late_item202_ids"].append(pair_id)
    event["item_status_counts"] = dict(item_counts)
    n = len(event["preceding_candidate_ids"])
    event["status"] = (
        "q_clock_unavailable"
        if q_clock["status"] != "aware"
        else "multiple_preceding_candidates"
        if n > 1
        else "preceding_candidate_observed"
        if n == 1
        else "same_or_late_only"
        if event["same_clock_item202_ids"] or event["late_item202_ids"]
        else "no_observed_candidate"
    )
    return event, pairs


def issuer_year_denominators(definition, events):
    by_issuer = defaultdict(list)
    for event in events:
        by_issuer[event["symbol"]].append(event)
    result = []
    for fixed in definition["issuer_denominators"]:
        rows = by_issuer[fixed["symbol"]]
        if len(rows) != fixed["requested_originals"]:
            raise ValueError("Issuer denominator changed")
        for year, requested in fixed["filed_year_counts"].items():
            cohort = [
                row for row in rows if row["original_row"]["filingDate"].startswith(year + "-")
            ]
            if len(cohort) != requested:
                raise ValueError("Issuer/filed-year denominator changed")
            result.append(
                {
                    "symbol": fixed["symbol"],
                    "cik": fixed["cik"],
                    "filed_year": int(year),
                    "requested_originals": requested,
                    "status_counts": dict(Counter(row["status"] for row in cohort)),
                    "manifest_status_counts": dict(
                        Counter(str(row["manifest_annotation"]["status"]) for row in cohort)
                    ),
                    "q_clock_status_counts": dict(
                        Counter(row["api_clock"]["status"] for row in cohort)
                    ),
                    "preceding_candidate_events": sum(
                        bool(row["preceding_candidate_ids"]) for row in cohort
                    ),
                    "multiple_preceding_candidate_events": sum(
                        len(row["preceding_candidate_ids"]) > 1 for row in cohort
                    ),
                    "original_preceding_pairs": sum(
                        len(row["preceding_candidate_ids"]) for row in cohort
                    ),
                    "unknown_undiscovered_originals": fixed["unknown_undiscovered_originals"],
                    "unknown_undiscovered_disclosures": None,
                    "source_window_complete_flag": fixed["source_window_complete_flag"],
                    "fiscal_period_verified": False,
                    "disclosed_components_verified": False,
                }
            )
    return result


@contextmanager
def readonly_lock(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Required source lock missing: " + str(path))
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        connection.execute("BEGIN")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        yield
    finally:
        connection.rollback()
        connection.close()


@contextmanager
def study_locks(repo, source_root):
    with ExitStack() as stack:
        stack.enter_context(readonly_lock(source_root / "capture.lock.sqlite"))
        stack.enter_context(readonly_lock(source_root.parent / "sec-source.lock.sqlite"))
        path = Path(repo) / "data/historical/worker.lock.sqlite"
        if not path.is_file():
            raise ValueError("Historical worker lock missing")
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0)
        try:
            connection.execute("BEGIN EXCLUSIVE")
            yield
        finally:
            connection.rollback()
            connection.close()


def validate_execution(definition_path, implementation_path, repo):
    if sha(definition_path) != DEFINITION_SHA256:
        raise ValueError("Frozen metadata definition changed")
    definition, implementation = read(definition_path), read(implementation_path)
    if (
        implementation.get("schema") != 1
        or implementation.get("reviewed_for_execution") is not True
    ):
        raise ValueError("Root-reviewed implementation is required")
    if implementation.get("definition_sha256") != DEFINITION_SHA256:
        raise ValueError("Implementation/definition mismatch")
    if (
        implementation.get("clarification_sha256") != CLARIFICATION_SHA256
        or sha(HERE / "clarification.json") != CLARIFICATION_SHA256
    ):
        raise ValueError("Frozen clarification changed")
    files = implementation["files"]
    if PARSER_NAME not in files:
        raise ValueError("Implementation omits reused parser")
    verify_inputs(repo, files)
    if set(required_code_paths(repo)) - files.keys():
        raise ValueError("Implementation omits required executed code")
    if (
        definition["schema"] != 1
        or len(definition["membership"]) != 100
        or definition["requested_originals"] != 4057
    ):
        raise ValueError("Frozen100-issuer/4057-original scope differs")
    if (
        definition["criteria"]["preceding_window_seconds"] != BEFORE_SECONDS
        or definition["criteria"]["late_window_seconds"] != AFTER_SECONDS
    ):
        raise ValueError("Frozen elapsed-window definition differs")
    if (
        definition["network_requests_allowed"] != 0
        or definition["economic_paths_allowed"] != 0
        or definition["document_requests_allowed"] != 0
        or definition["source_writes_allowed"] is not False
    ):
        raise ValueError("Offline metadata-only scope differs")
    return definition, implementation


def run(definition_path, implementation_path, repo=REPO, output_root=HERE):
    repo, output_root = Path(repo).resolve(), Path(output_root).resolve()
    definition_path, implementation_path = (
        Path(definition_path).resolve(),
        Path(implementation_path).resolve(),
    )
    output_root.relative_to(repo)
    attempt = output_root / "attempts" / uuid4().hex
    attempt.mkdir(parents=True, exist_ok=False)
    started = {
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "definition_path": str(definition_path),
        "expected_definition_sha256": DEFINITION_SHA256,
        "implementation_path": str(implementation_path),
        "audit_sha256": sha(__file__),
    }
    write(attempt / "attempt.json", started)
    try:
        definition, implementation = validate_execution(definition_path, implementation_path, repo)
        identities = dict(definition["inputs"])
        for name, digest in implementation["files"].items():
            if name in identities and identities[name] != digest:
                raise ValueError("Source/implementation binding conflict: " + name)
            identities[name] = digest
        identities[definition_path.relative_to(repo).as_posix()] = DEFINITION_SHA256
        identities[implementation_path.relative_to(repo).as_posix()] = sha(implementation_path)
        identities[(HERE / "clarification.json").relative_to(repo).as_posix()] = (
            CLARIFICATION_SHA256
        )
        source_root = resolve(repo, definition["source_root"])
        with study_locks(repo, source_root):
            verify_inputs(repo, identities)
            if (source_root / "STOP.json").exists():
                raise ValueError("Unresolved source STOP requires reconciliation")
            completion = read(source_root / "completion.json")
            if completion["status"] not in (
                "captured",
                "captured_with_coverage_review_needed",
                "incomplete",
            ):
                raise ValueError("Source has no terminal completion")
            if (
                completion["registered_originals"] != 4057
                or completion["processed_originals"] != 4057
                or sum(completion["counts"].values()) != 4057
                or completion["incomplete_discoveries"]
            ):
                raise ValueError("Source terminal denominators differ")
            originals, metadata, request = reconstruct_discovery(
                definition, repo, load_parser(repo)
            )
            by_cik = defaultdict(list)
            for group in metadata:
                by_cik[group["cik"]].append(group)
            events, pair_counts = [], Counter()
            with (attempt / "metadata-records.jsonl").open("x", encoding="utf-8") as stream:
                for group in metadata:
                    stream.write(canonical(group) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            with (attempt / "pairs.jsonl").open("x", encoding="utf-8") as stream:
                for issuer, row, group in originals:
                    manifest_path = (
                        source_root
                        / "filings"
                        / issuer["symbol"]
                        / (row["accessionNumber"] + ".json")
                    )
                    manifest = read(manifest_path)
                    if manifest["issuer"] != issuer or canonical(
                        manifest["registry_row"]
                    ) != canonical(row):
                        raise ValueError("Original manifest registry identity mismatch")
                    event, pairs = evaluate_event(
                        issuer, row, group, manifest, by_cik[issuer["cik"]], request
                    )
                    event["manifest_path"] = manifest_path.relative_to(repo).as_posix()
                    event["manifest_sha256"] = identities[event["manifest_path"]]
                    events.append(event)
                    for pair in pairs:
                        stream.write(canonical(pair) + "\n")
                        pair_counts[pair["timing"]] += 1
                stream.flush()
                os.fsync(stream.fileno())
            denominators = issuer_year_denominators(definition, events)
            write(attempt / "events.json", events)
            write(attempt / "issuer-year-denominators.json", denominators)
            report = {
                "schema": 1,
                "status": "complete",
                "definition_sha256": DEFINITION_SHA256,
                "implementation_sha256": sha(implementation_path),
                "clarification_sha256": CLARIFICATION_SHA256,
                "requested_issuers": len(definition["membership"]),
                "requested_originals": len(events),
                "original_discovery_sources": len(definition["discovery_sources"]),
                "metadata_groups": len(metadata),
                "conflicting_metadata_groups": sum(
                    group["conflicting_metadata"] for group in metadata
                ),
                "metadata_raw_occurrences": sum(
                    len(variant["origins"]) for group in metadata for variant in group["variants"]
                ),
                "event_status_counts": dict(Counter(event["status"] for event in events)),
                "manifest_status_counts": dict(
                    Counter(str(event["manifest_annotation"]["status"]) for event in events)
                ),
                "q_api_clock_status_counts": dict(
                    Counter(event["api_clock"]["status"] for event in events)
                ),
                "k_item_status_counts": dict(
                    Counter(group["items"]["status"] for group in metadata)
                ),
                "k_api_clock_status_counts": dict(
                    Counter(group["api_clock"]["status"] for group in metadata)
                ),
                "pair_timing_counts": dict(pair_counts),
                "original_preceding_candidate_pairs": sum(
                    len(event["preceding_candidate_ids"]) for event in events
                ),
                "events_with_preceding_candidates": sum(
                    bool(event["preceding_candidate_ids"]) for event in events
                ),
                "events_with_multiple_preceding_candidates": sum(
                    len(event["preceding_candidate_ids"]) > 1 for event in events
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
                "issuer_year_rows": len(denominators),
                "network_requests": 0,
                "documents_requested": 0,
                "financial_facts_extracted": False,
                "prices_or_returns_read": False,
                "economic_paths": 0,
                "fiscal_period_verified": False,
                "disclosed_components_verified": False,
                "limitations": definition["reused_source_limitations"],
                "outside_pair_retention": (
                    "All groups/origins retained once; exhaustive per-Q timing counts preserve "
                    "outside-window evidence without Cartesian serialization."
                ),
            }
            write(attempt / "report.json", report)
            lines = [
                "# Cached disclosure timing audit",
                "",
                "Metadata candidates only. No new financial facts, backdated S/Q, prices, "
                "outcomes or network requests.",
                "",
                f"- Requested: {len(events):,} original10-Q events across "
                f"{len(definition['membership'])} fixed issuers.",
                f"- Original discovery roots/history: {len(definition['discovery_sources'])}.",
                "- Events with a preceding original8-K Item2.02 candidate: "
                f"{report['events_with_preceding_candidates']:,}.",
                f"- Preceding candidate pairs: {report['original_preceding_candidate_pairs']:,}; "
                f"events with multiple: {report['events_with_multiple_preceding_candidates']:,}.",
                "- Same-clock, later, missing/malformed, amendments, failures and source-boundary "
                "limitations remain visible in the saved records.",
                "",
                "An earlier API timestamp or Item2.02 tag does not verify the same fiscal period, "
                "disclosed components, public dissemination or an earlier tradable signal.",
                "No observed candidate is not evidence that no earlier earnings disclosure exists.",
                "",
                "Original failed10-Q captures remain in all requested denominators. "
                "Original manifest clocks are annotations, never silently requalified.",
                "",
                "## Source limitations",
                "",
            ]
            lines.extend("- " + value for value in report["limitations"])
            with (attempt / "report.md").open("x", encoding="utf-8") as stream:
                stream.write("\n".join(lines) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            verify_inputs(repo, identities)
            if (source_root / "STOP.json").exists():
                raise ValueError("Source STOP appeared during audit")
            write(attempt / "input-identities.json", identities)
            names = (
                "events.json",
                "metadata-records.jsonl",
                "pairs.jsonl",
                "issuer-year-denominators.json",
                "report.json",
                "report.md",
                "input-identities.json",
            )
            write(
                attempt / "completion.json",
                {
                    "status": "complete",
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "definition_sha256": DEFINITION_SHA256,
                    "implementation_sha256": sha(implementation_path),
                    "clarification_sha256": CLARIFICATION_SHA256,
                    "outputs": {
                        name: {
                            "sha256": sha(attempt / name),
                            "bytes": (attempt / name).stat().st_size,
                        }
                        for name in names
                    },
                },
            )
        print(json.dumps({"attempt": str(attempt), "status": "complete"}), flush=True)
        return attempt
    except Exception as error:
        write(
            attempt / "failure.json",
            {
                "status": "failed",
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "error": type(error).__name__ + ": " + str(error),
                "traceback": traceback.format_exc(),
            },
        )
        raise


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--definition", required=True, type=Path)
    cli.add_argument("--implementation", required=True, type=Path)
    args = cli.parse_args()
    run(args.definition, args.implementation)

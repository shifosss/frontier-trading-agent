"""Source-only 8-K Item 2.02 timing audit for the fixed 100-issuer original 10-Q corpus.

Reads only retained SEC submissions metadata, the frozen 10-Q manifests, the retained
XNYS calendar and (optionally) the terminal qualification events. No network, prices,
returns, models, S/Q values or exhibit content. A matched 8-K is a timing candidate,
never evidence of what it disclosed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sqlite3
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEFINITION = ROOT / "definition.json"
FREEZE = ROOT / "freeze.json"


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse the frozen submissions-table parser and the frozen 10-Q event clock unchanged.
base = _module(
    REPO / ".qualification/filing-source20260928/capture.py", "timing_audit_submissions_parser"
)
features = _module(
    REPO / ".qualification/filing-features20260928/features.py", "timing_audit_event_clock"
)

STATUSES = [
    "issuer_unavailable",
    "q_metadata_unavailable",
    "q_session_unavailable",
    "window_coverage_incomplete",
    "ambiguous_metadata",
    "no_candidate",
    "single_prior",
    "single_same_session",
    "single_after",
    "multiple",
]


class AuditError(Exception):
    """Identity/definition failure: the whole attempt stops."""


class IssuerUnavailable(Exception):
    """Source/provenance failure: the issuer's 10-Qs stay in the denominator as unavailable."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def day(value):
    return date.fromisoformat(value)


# ---------------------------------------------------------------- identities


def manifest_paths(repo, definition):
    return sorted((repo / definition["filings"]["root"]).glob("*/*.json"))


def manifest_digest(repo, paths):
    lines = "".join(f"{p.relative_to(repo).as_posix()}\t{sha(p.read_bytes())}\n" for p in paths)
    return sha(lines.encode())


def check_inputs(repo, definition):
    """Return a list of missing/mismatched bound inputs; empty means all identities match."""
    problems = []
    for rel, digest in {**definition["inputs"], **definition["code"]}.items():
        path = repo / rel
        if not path.is_file():
            problems.append({"path": rel, "problem": "missing", "expected_sha256": digest})
        elif sha(path.read_bytes()) != digest:
            problems.append({"path": rel, "problem": "sha256_mismatch", "expected_sha256": digest})
    paths = manifest_paths(repo, definition)
    expected = definition["filings"]
    if len(paths) != expected["count"] or manifest_digest(repo, paths) != expected["digest_sha256"]:
        problems.append(
            {
                "path": expected["root"],
                "problem": "manifest_set_or_digest_mismatch",
                "observed_count": len(paths),
            }
        )
    return problems


def verify_definition(definition_path, freeze_path, repo):
    raw = Path(definition_path).read_bytes()
    frozen = load(freeze_path)
    if sha(raw) != frozen["definition_sha256"]:
        raise AuditError("Definition bytes differ from the frozen declaration")
    definition = json.loads(raw)
    if definition.get("schema") != 1 or definition.get("study") != ROOT.name:
        raise AuditError("Unexpected definition schema/study")
    problems = check_inputs(repo, definition)
    if problems:
        raise AuditError("Bound inputs are missing or changed: " + json.dumps(problems[:20]))
    return definition, sha(raw)


# ---------------------------------------------------------------- provenance


def resolve_source(meta, source_root, repo, reuse):
    """Locate one retained raw submissions source with the capture's own path rule and verify it."""
    if meta.get("status") != 200:
        raise IssuerUnavailable("discovery source was not HTTP200: " + str(meta.get("url")))
    digest, size, rel = meta.get("sha256"), meta.get("bytes"), meta.get("path")
    if not digest or not rel:
        raise IssuerUnavailable("discovery source lacks sha256/path: " + str(meta.get("url")))
    if meta.get("reused"):
        declared = reuse.get(meta.get("url"))
        if not declared or (declared["sha256"], declared["path"]) != (digest, rel):
            raise AuditError(
                "Reused source differs from the frozen request reuse catalog: "
                + str(meta.get("url"))
            )
    path = (repo if meta.get("reused") else source_root) / rel
    if not path.is_file():
        raise IssuerUnavailable("retained raw source not present: " + path.as_posix())
    data = path.read_bytes()
    if sha(data) != digest or (size is not None and len(data) != size):
        raise AuditError(
            "Retained raw source bytes do not match recorded identity: " + path.as_posix()
        )
    return path, data


def reconstruct_issuer(issuer, discovery, request, source_root, repo):
    """Re-parse root/history bytes, keep every row occurrence with its source and row index."""
    if not discovery.get("complete"):
        raise IssuerUnavailable("discovery incomplete: " + str(discovery.get("error")))
    sources = discovery.get("sources") or []
    if not sources:
        raise IssuerUnavailable("discovery has no sources")
    reuse = {r["url"]: r for r in request["reuse"]}
    occurrences, identities, coverage = [], [], []
    root_body = None
    for index, meta in enumerate(sources):
        path, data = resolve_source(meta, source_root, repo, reuse)
        body = json.loads(data)
        if index == 0:
            expected = "https://data.sec.gov/submissions/CIK" + issuer["cik"] + ".json"
            if meta.get("url") != expected or str(body.get("cik")).zfill(10) != issuer["cik"]:
                raise IssuerUnavailable("root source is not this CIK")
            root_body, table = body, body["filings"]["recent"]
        else:
            table = body
        try:
            rows = base.table_rows(table)
        except base.CaptureError as exc:
            raise IssuerUnavailable("submissions table invalid: " + str(exc)) from exc
        identities.append(
            {
                "index": index,
                "url": meta["url"],
                "sha256": meta["sha256"],
                "resolved_path": path.as_posix(),
                "rows": len(rows),
            }
        )
        occurrences += [
            {"row": row, "source_index": index, "row_index": i} for i, row in enumerate(rows)
        ]
        if index == 0 and rows:
            coverage.append((min(r["filingDate"] for r in rows), date.max.isoformat()))
    declared = root_body["filings"].get("files") or []
    try:
        selected = base.history_files(root_body, request)
    except base.CaptureError as exc:
        raise IssuerUnavailable("history range declaration invalid: " + str(exc)) from exc
    fetched = [m["url"] for m in sources[1:]]
    if fetched != ["https://data.sec.gov/submissions/" + f["name"] for f in selected]:
        raise IssuerUnavailable("fetched history pages differ from the declared overlapping pages")
    coverage += [(f["filingFrom"], f["filingTo"]) for f in selected]
    if not declared:
        coverage = [(date.min.isoformat(), date.max.isoformat())]
    if [o["row"] for o in occurrences] != discovery.get("rows"):
        raise IssuerUnavailable("re-parsed occurrences differ from saved discovery rows")
    return {"occurrences": occurrences, "sources": identities, "coverage": sorted(coverage)}


def canonicalize(occurrences):
    """One row per accession when every occurrence is identical; otherwise a retained conflict."""
    grouped = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence["row"]["accessionNumber"], []).append(occurrence)
    canonical = {}
    for accession, group in grouped.items():
        variants = []
        for occurrence in group:
            if occurrence["row"] not in variants:
                variants.append(occurrence["row"])
        canonical[accession] = {
            "row": variants[0],
            "occurrences": len(group),
            "conflict": len(variants) > 1,
            "variants": variants if len(variants) > 1 else [],
            "provenance": [(o["source_index"], o["row_index"]) for o in group],
        }
    return canonical


def covered(coverage, start, end):
    """True when every date in [start, end] lies inside the union of covered filing ranges."""
    cursor = start
    for lo, hi in coverage:
        if day(lo) <= cursor <= day(hi):
            cursor = day(hi) + timedelta(days=1) if day(hi) < date.max else date.max
            if cursor > end:
                return True
    return cursor > end


# ---------------------------------------------------------------- classification


def items_tokens(value):
    if not isinstance(value, str) or not value.strip():
        return None
    return {token.strip() for token in value.split(",") if token.strip()}


def entry_session(acceptance, filing_date, calendar):
    try:
        clock = features.event_clock(acceptance, filing_date, calendar)
    except (TypeError, ValueError):
        return None, "clock_invalid"
    return clock["entry_session"], clock["execution_status"]


def classify(q_row, canonical, coverage, calendar, positions, rules):
    """Classify one original 10-Q against same-CIK in-window 8-K Item 2.02 metadata."""
    result = {
        "status": None,
        "reasons": [],
        "candidates": [],
        "amendments": [],
        "items_unknown": [],
        "conflicts": [],
        "q_entry_session": None,
        "late_10q_beyond_window": None,
    }
    accession = q_row.get("accessionNumber")
    entry = canonical.get(accession)
    if entry is None or entry["conflict"] or entry["row"] != q_row:
        result.update(
            status="q_metadata_unavailable",
            reasons=["10-Q row absent/conflicting/changed in re-parsed sources"],
        )
        return result
    try:
        report = day(q_row["reportDate"])
        day(q_row["filingDate"])
    except (KeyError, TypeError, ValueError):
        result.update(
            status="q_metadata_unavailable",
            reasons=["10-Q reportDate/filingDate missing or invalid"],
        )
        return result
    q_session, q_clock = entry_session(
        q_row.get("acceptanceDateTime"), q_row["filingDate"], calendar
    )
    if q_session is None:
        result.update(status="q_session_unavailable", reasons=["10-Q clock: " + q_clock])
        return result
    result["q_entry_session"] = q_session
    end = report + timedelta(days=rules["window_days_after_report_date"])
    result["late_10q_beyond_window"] = day(q_row["filingDate"]) > end
    if not covered(coverage, report + timedelta(days=1), end):
        result.update(
            status="window_coverage_incomplete",
            reasons=["window outside retained submissions ranges"],
        )
        return result
    forms = {rules["candidate_form"], rules["amendment_form"]}
    for other_accession, other in sorted(
        canonical.items(), key=lambda x: (x[1]["row"]["filingDate"], x[0])
    ):
        row = other["row"]
        if not any(
            v.get("form") in forms and report < day(v["filingDate"]) <= end
            for v in other["variants"] or [row]
        ):
            continue
        if other["conflict"]:
            result["conflicts"].append(other_accession)
            continue
        tokens = items_tokens(row.get("items"))
        if tokens is None:
            if row["form"] == rules["candidate_form"]:
                result["items_unknown"].append(other_accession)
            continue
        if rules["item_token"] not in tokens:
            continue
        if row["form"] == rules["amendment_form"]:
            result["amendments"].append(other_accession)
            continue
        k_session, k_clock = entry_session(
            row.get("acceptanceDateTime"), row["filingDate"], calendar
        )
        candidate = {
            "accession": other_accession,
            "filingDate": row["filingDate"],
            "reportDate": row.get("reportDate"),
            "acceptanceDateTime": row.get("acceptanceDateTime"),
            "items": row.get("items"),
            "primaryDocument": row.get("primaryDocument"),
            "primaryDocDescription": row.get("primaryDocDescription"),
            "occurrences": other["occurrences"],
            "entry_session": k_session,
            "timing": None,
            "lead_sessions": None,
            "lead_hours": None,
        }
        if k_session is None:
            candidate["timing"] = "clock_unavailable:" + k_clock
        else:
            lead = positions[q_session] - positions[k_session]
            candidate.update(
                timing="prior" if lead > 0 else "same_session" if lead == 0 else "after",
                lead_sessions=lead,
                lead_hours=round(
                    (
                        datetime.fromisoformat(q_row["acceptanceDateTime"])
                        - datetime.fromisoformat(row["acceptanceDateTime"])
                    ).total_seconds()
                    / 3600,
                    4,
                ),
            )
        result["candidates"].append(candidate)
    candidates = result["candidates"]
    unclocked = [c for c in candidates if c["entry_session"] is None]
    if result["conflicts"] or result["items_unknown"] or unclocked:
        result["status"] = "ambiguous_metadata"
        result["reasons"] = [
            r
            for r, bad in [
                ("conflicting accession metadata in window", result["conflicts"]),
                ("8-K without items metadata in window", result["items_unknown"]),
                ("candidate clock unavailable", unclocked),
            ]
            if bad
        ]
    elif not candidates:
        result["status"] = "no_candidate"
    elif len(candidates) == 1:
        result["status"] = "single_" + candidates[0]["timing"]
    else:
        result["status"] = "multiple"
    return result


# ---------------------------------------------------------------- summaries


def quantiles(values):
    if not values:
        return None
    values = sorted(values)

    def q(p):
        return values[min(len(values) - 1, int(p * (len(values) - 1) + 0.5))]

    return {
        "n": len(values),
        "min": values[0],
        "p25": q(0.25),
        "median": q(0.5),
        "p75": q(0.75),
        "p90": q(0.9),
        "max": values[-1],
    }


def stratum_summary(rows, interpretation):
    # Lower bound: unambiguous prior-session candidates. Upper bound: every row not definitively
    # without one (unavailable, uncovered and ambiguous rows all count as possible priors).
    n = len(rows)
    counts = Counter(r["status"] for r in rows)
    clean_prior = sum(
        r["status"] in ("single_prior", "multiple") and r["n_prior"] > 0 for r in rows
    )
    definitely_none = sum(
        r["status"] in ("no_candidate", "single_same_session", "single_after")
        or (r["status"] == "multiple" and r["n_prior"] == 0)
        for r in rows
    )
    leads = [
        r["earliest_prior_lead_sessions"]
        for r in rows
        if r["earliest_prior_lead_sessions"] is not None
        and r["status"] in ("single_prior", "multiple")
    ]
    low = clean_prior / n if n else None
    high = (n - definitely_none) / n if n else None
    if n == 0:
        verdict = "no_denominator"
    elif low >= interpretation["supported_if_lower_share_at_least"]:
        verdict = "supported_at_metadata_level"
    elif high < interpretation["not_supported_if_upper_share_below"]:
        verdict = "not_supported_at_metadata_level"
    else:
        verdict = "inconclusive"
    return {
        "denominator": n,
        "status_counts": {s: counts.get(s, 0) for s in STATUSES},
        "with_prior_candidate_lower": clean_prior,
        "with_prior_candidate_upper": n - definitely_none,
        "prior_share_lower": low,
        "prior_share_upper": high,
        "late_10q_beyond_window": sum(bool(r["late_10q_beyond_window"]) for r in rows),
        "earliest_prior_lead_sessions": quantiles(leads),
        "lead_at_least_5_sessions": sum(x >= 5 for x in leads),
        "verdict": verdict,
    }


def flatten(issuer, manifest, result, qualified):
    row = manifest["registry_row"]
    candidates = result["candidates"]
    prior = [c for c in candidates if c["timing"] == "prior"]
    return {
        "symbol": issuer["symbol"],
        "cik": issuer["cik"],
        "accession": row.get("accessionNumber"),
        "report_date": row.get("reportDate"),
        "filing_date": row.get("filingDate"),
        "acceptance": row.get("acceptanceDateTime"),
        "capture_status": manifest.get("status"),
        "strategy_source_qualified": qualified,
        "status": result["status"],
        "reasons": result["reasons"],
        "q_entry_session": result["q_entry_session"],
        "late_10q_beyond_window": result["late_10q_beyond_window"],
        "n_candidates": len(candidates),
        "n_prior": len(prior),
        "n_same_session": sum(c["timing"] == "same_session" for c in candidates),
        "n_after": sum(c["timing"] == "after" for c in candidates),
        "earliest_prior_lead_sessions": max((c["lead_sessions"] for c in prior), default=None),
        "candidates": candidates,
        "amendments": result["amendments"],
        "items_unknown": result["items_unknown"],
        "conflicts": result["conflicts"],
    }


# ---------------------------------------------------------------- run


@contextmanager
def locks(source_root, root):
    """Own exclusive lock plus a read transaction on the capture lock, like the collector."""
    lock = source_root / "capture.lock.sqlite"
    if not lock.is_file():
        raise AuditError("Source worker lock is missing: " + lock.as_posix())
    own = sqlite3.connect(root / "audit.lock.sqlite", timeout=0)
    reader = None
    try:
        try:
            own.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            raise AuditError("Another timing audit holds the lock") from exc
        try:
            reader = sqlite3.connect(lock.resolve().as_uri() + "?mode=ro", uri=True, timeout=0)
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.OperationalError as exc:
            raise AuditError("A source capture worker holds the capture lock") from exc
        yield "read_guard_held"
    finally:
        if reader:
            reader.rollback()
            reader.close()
        own.rollback()
        own.close()


def audit(definition, repo):
    """Pure computation over bound inputs; returns per-issuer, per-10-Q and summary records."""
    paths = definition["paths"]
    source_root = repo / paths["source_root"]
    request = load(repo / paths["source_request"])
    calendar_doc = load(repo / paths["calendar"])
    calendar = calendar_doc["sessions"] if isinstance(calendar_doc, dict) else calendar_doc
    positions = {row["session"]: i for i, row in enumerate(calendar)}
    events = load(repo / paths["qualification_events"])
    events = events["events"] if isinstance(events, dict) else events
    qualified = {e["accession"] for e in events if e.get("strategy_source_status") == "qualified"}
    if len(qualified) != definition["denominators"]["strategy_source_qualified"]:
        raise AuditError("Qualified event count differs from the declared denominator")
    manifests = {}
    for path in manifest_paths(repo, definition):
        manifest = load(path)
        manifests.setdefault(manifest["issuer"]["cik"], []).append(manifest)
    if set(manifests) - {i["cik"] for i in request["issuers"]}:
        raise AuditError("A 10-Q manifest belongs to an issuer outside the frozen request")
    rules = definition["matching"]
    issuers, rows = [], []
    for issuer in request["issuers"]:
        own = sorted(
            manifests.get(issuer["cik"], []), key=lambda m: m["registry_row"]["accessionNumber"]
        )
        record = {
            "issuer": issuer,
            "registered_originals": len(own),
            "status": "reconstructed",
            "error": None,
        }
        try:
            discovery = load(source_root / "issuers" / issuer["symbol"] / "discovery.json")
            if sorted(r["accessionNumber"] for r in discovery.get("original_accessions", [])) != [
                m["registry_row"]["accessionNumber"] for m in own
            ]:
                raise IssuerUnavailable("registered 10-Q set differs from discovery originals")
            rebuilt = reconstruct_issuer(issuer, discovery, request, source_root, repo)
            canonical = canonicalize(rebuilt["occurrences"])
            form_counts = Counter(o["row"].get("form") for o in rebuilt["occurrences"])
            item_rows = [
                c["row"]
                for c in canonical.values()
                if c["row"].get("form") == rules["candidate_form"]
                and rules["item_token"] in (items_tokens(c["row"].get("items")) or ())
            ]
            record.update(
                sources=rebuilt["sources"],
                coverage=rebuilt["coverage"],
                occurrences=len(rebuilt["occurrences"]),
                unique_accessions=len(canonical),
                duplicate_occurrences=len(rebuilt["occurrences"]) - len(canonical),
                conflicting_accessions=sorted(a for a, c in canonical.items() if c["conflict"]),
                raw_8k_occurrences=form_counts.get(rules["candidate_form"], 0),
                unique_item_2_02_8k=len(item_rows),
                empty_primary_document_8k=sum(
                    not c["row"].get("primaryDocument")
                    for c in canonical.values()
                    if c["row"].get("form") == rules["candidate_form"]
                ),
            )
        except IssuerUnavailable as exc:
            record.update(status="unavailable", error=str(exc))
            canonical = None
        issuers.append(record)
        for manifest in own:
            # The 10-Q clock comes from its frozen manifest, so it exists even when sources do not.
            q_row = manifest["registry_row"]
            q_session = entry_session(
                q_row.get("acceptanceDateTime"), q_row.get("filingDate"), calendar
            )[0]
            if canonical is None:
                result = {
                    "status": "issuer_unavailable",
                    "reasons": [record["error"]],
                    "candidates": [],
                    "amendments": [],
                    "items_unknown": [],
                    "conflicts": [],
                    "q_entry_session": None,
                    "late_10q_beyond_window": None,
                }
            else:
                result = classify(
                    manifest["registry_row"],
                    canonical,
                    record["coverage"],
                    calendar,
                    positions,
                    rules,
                )
            if result["q_entry_session"] not in (None, q_session):
                raise AuditError("Classification and manifest 10-Q clocks differ")
            result["q_entry_session"] = q_session
            accession = q_row["accessionNumber"]
            rows.append(flatten(issuer, manifest, result, accession in qualified))
    if len(rows) != definition["denominators"]["registered_originals"] or not qualified <= {
        r["accession"] for r in rows
    }:
        raise AuditError("Audit rows do not cover the declared original/qualified denominators")
    # The reused 10-Q clock must reproduce every saved entry session exactly, issuer status aside.
    by_accession = {r["accession"]: r for r in rows}
    for event in events:
        session = by_accession.get(event["accession"], {}).get("q_entry_session")
        if event.get("entry_session") and session != event["entry_session"]:
            raise AuditError("Recomputed 10-Q entry session differs: " + event["accession"])
    interpretation = definition["interpretation"]
    strata = {
        "all_registered_originals": rows,
        "captured_originals": [r for r in rows if r["capture_status"] == "captured"],
        "strategy_source_qualified": [r for r in rows if r["strategy_source_qualified"]],
    }
    for year in sorted({r["filing_date"][:4] for r in rows if r["filing_date"]}):
        strata["filed_" + year] = [r for r in rows if (r["filing_date"] or "").startswith(year)]
    summary = {name: stratum_summary(group, interpretation) for name, group in strata.items()}
    primary = interpretation["primary_stratum"]
    available = [i for i in issuers if i["status"] == "reconstructed"]
    return (
        issuers,
        rows,
        {
            "primary_stratum": primary,
            "primary_verdict": summary[primary]["verdict"],
            "strata": summary,
            "issuers_unavailable": len(issuers) - len(available),
            "issuers_without_item_2_02_8k": sorted(
                i["issuer"]["symbol"] for i in available if not i["unique_item_2_02_8k"]
            ),
            "raw_8k_occurrences": sum(i["raw_8k_occurrences"] for i in available),
            "unique_item_2_02_8k": sum(i["unique_item_2_02_8k"] for i in available),
        },
    )


CSV_FIELDS = [
    "symbol",
    "cik",
    "accession",
    "report_date",
    "filing_date",
    "acceptance",
    "capture_status",
    "strategy_source_qualified",
    "status",
    "q_entry_session",
    "n_candidates",
    "n_prior",
    "n_same_session",
    "n_after",
    "earliest_prior_lead_sessions",
    "late_10q_beyond_window",
]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return sha(path.read_bytes())


def run(definition_path=DEFINITION, freeze_path=FREEZE, repo=REPO, output_root=ROOT):
    definition, definition_sha = verify_definition(definition_path, freeze_path, repo)
    with locks(repo / definition["paths"]["source_root"], output_root) as guard:
        attempt = output_root / "attempts" / uuid.uuid4().hex
        attempt.mkdir(parents=True, exist_ok=False)
        meta = {
            "attempt": attempt.name,
            "definition_sha256": definition_sha,
            "started_at_utc": now(),
            "network_requests": 0,
            "prices_or_returns_read": False,
            "status": "running",
        }
        write_json(attempt / "attempt.json", meta)
        try:
            issuers, rows, summary = audit(definition, repo)
            if check_inputs(repo, definition):
                raise AuditError("Bound inputs changed during the audit")
            files = {
                "issuers.json": write_json(attempt / "issuers.json", issuers),
                "events.json": write_json(attempt / "events.json", rows),
            }
            with (attempt / "events.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            files["events.csv"] = sha((attempt / "events.csv").read_bytes())
            summary.update(source_lock=guard, network_requests=0, prices_or_returns_read=False)
            files["summary.json"] = write_json(attempt / "summary.json", summary)
            meta.update(status="complete", finished_at_utc=now(), files=files)
            write_json(attempt / "attempt.json", meta)
            return attempt
        except Exception as exc:
            meta.update(
                status="failed", finished_at_utc=now(), error=type(exc).__name__ + ": " + str(exc)
            )
            write_json(attempt / "attempt.json", meta)
            write_json(attempt / "failure.json", meta)
            raise


def preflight(definition_path=DEFINITION, repo=REPO):
    """List missing/changed inputs, including raw sources named by discovery files. No writes."""
    definition = load(definition_path)
    problems = check_inputs(repo, definition)
    source_root = repo / definition["paths"]["source_root"]
    if not (source_root / "capture.lock.sqlite").is_file():
        problems.append(
            {
                "path": (source_root / "capture.lock.sqlite").relative_to(repo).as_posix(),
                "problem": "missing",
            }
        )
    reuse = {r["url"]: r for r in load(repo / definition["paths"]["source_request"])["reuse"]}
    for rel in definition["inputs"]:
        if rel.endswith("/discovery.json") and (repo / rel).is_file():
            for meta in load(repo / rel).get("sources", []):
                try:
                    resolve_source(meta, source_root, repo, reuse)
                except (IssuerUnavailable, AuditError) as exc:
                    problems.append(
                        {"path": meta.get("path"), "problem": str(exc), "url": meta.get("url")}
                    )
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight", action="store_true", help="check bound inputs only; no audit output"
    )
    args = parser.parse_args()
    if args.preflight:
        found = preflight()
        print(json.dumps({"ready": not found, "problems": found}, indent=1))
    else:
        print(json.dumps({"attempt": str(run())}))

"""Source-only 8-K Item 2.02 timing audit for the fixed 100-issuer original 10-Q corpus.

Reads only retained SEC submissions metadata, the frozen 10-Q manifests, the retained
XNYS calendar and (optionally) the terminal qualification events. No network, prices,
returns, models, S/Q values or exhibit content. A matched 8-K is a timing candidate,
never evidence of what it disclosed.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import importlib.resources
import importlib.util
import io
import json
import os
import platform
import re
import sqlite3
import sys
import uuid
import zoneinfo
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEFINITION = ROOT / "definition.json"
FREEZE = ROOT / "freeze.json"
# Reused frozen modules; their bytes must match before they are executed.
FROZEN_MODULES = {
    ".qualification/filing-source20260928/capture.py": (
        "962bccbf962d6aff53d3102156f3ad1f50765b66a5373124aa6b9ab0a62c84bb"
    ),
    ".qualification/filing-features20260928/features.py": (
        "991260b80547c03c873c0d5bf62c57d86bf3fc1f5c0df0c192a7b4cc1fcc372f"
    ),
}
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


def load_verified_module(path, digest, name):
    """Execute exactly the verified bytes of a reused module, or refuse without executing."""
    data = Path(path).read_bytes()
    if sha(data) != digest:
        raise AuditError("Reused module bytes changed; not executed: " + Path(path).as_posix())
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def load_verified_definitions(path, digest, names, namespace):
    """Execute only the named top-level definitions of verified bytes, not the module's imports."""
    data = Path(path).read_bytes()
    if sha(data) != digest:
        raise AuditError("Reused module bytes changed; not executed: " + Path(path).as_posix())
    tree = ast.parse(data, filename=str(path))
    nodes = [
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names
    ]
    if sorted(n.name for n in nodes) != sorted(names):
        raise AuditError("Reused definitions missing or duplicated in " + Path(path).as_posix())
    namespace = dict(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return type("VerifiedDefinitions", (), {name: namespace[name] for name in names})


# Reuse the frozen submissions parser and 10-Q event clock unchanged. capture.py imports the
# project package at top level, so only its four needed definitions are executed, with the
# stdlib names they use. features.py imports only the standard library and runs whole.
# They are loaded only for a real audit, after its identity checks, never for --preflight.
_CAPTURE, _FEATURES = FROZEN_MODULES
base = features = None


def use_locked_tzdata():
    """Resolve time zones only from the uv.lock-pinned tzdata package, never system TZif files."""
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()


def tz_identity():
    """The tzdata package version and the exact America/New_York TZif bytes ZoneInfo will use."""
    try:
        version = importlib.metadata.version("tzdata")
        data = (
            importlib.resources.files("tzdata.zoneinfo").joinpath("America/New_York").read_bytes()
        )
    except (importlib.metadata.PackageNotFoundError, ModuleNotFoundError, FileNotFoundError):
        return {"tzdata_package": None, "new_york_tzif_sha256": None}
    return {"tzdata_package": version, "new_york_tzif_sha256": sha(data)}


def load_frozen(repo=REPO):
    global base, features
    use_locked_tzdata()
    if base is None:
        base = load_verified_definitions(
            repo / _CAPTURE,
            FROZEN_MODULES[_CAPTURE],
            ["CaptureError", "Halt", "table_rows", "history_files"],
            {"re": re, "datetime": datetime},
        )
        features = load_verified_module(
            repo / _FEATURES, FROZEN_MODULES[_FEATURES], "timing_audit_event_clock"
        )


def runtime_identity():
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "zoneinfo_tzpath": list(zoneinfo.TZPATH),
        **tz_identity(),
    }


# ---------------------------------------------------------------- identities


def manifest_paths(repo, definition):
    return sorted((repo / definition["filings"]["root"]).glob("*/*.json"))


def manifest_digest(repo, paths):
    lines = "".join(f"{p.relative_to(repo).as_posix()}\t{sha(p.read_bytes())}\n" for p in paths)
    return sha(lines.encode())


def input_state(repo, definition):
    """Observed SHA256 (or None when absent) for every bound global and per-issuer input."""
    bound = {**definition["inputs"], **definition["issuer_inputs"], **definition["code"]}
    return {
        rel: sha((repo / rel).read_bytes()) if (repo / rel).is_file() else None for rel in bound
    }


def check_inputs(repo, definition, state=None, allow_missing_issuer_inputs=True):
    """Problems with bound inputs. Absent per-issuer inputs only make that issuer unavailable."""
    state = input_state(repo, definition) if state is None else state
    problems = []
    for group in ("inputs", "code", "issuer_inputs"):
        for rel, digest in definition[group].items():
            observed = state[rel]
            if observed is None and group == "issuer_inputs" and allow_missing_issuer_inputs:
                continue
            if observed != digest:
                problem = "missing" if observed is None else "sha256_mismatch"
                problems.append({"path": rel, "problem": problem, "expected_sha256": digest})
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


def definition_problems(definition_path, freeze_path):
    """Read-only identity checks of the frozen declaration; empty means the declaration holds."""
    raw = Path(definition_path).read_bytes()
    frozen = load(freeze_path)
    definition = json.loads(raw)
    problems = []
    if sha(raw) != frozen["definition_sha256"]:
        problems.append("Definition bytes differ from the frozen declaration")
    if definition.get("schema") != 1 or definition.get("study") != ROOT.name:
        problems.append("Unexpected definition schema/study")
    if {a["record"] for a in definition.get("amendments", [])} != set(frozen.get("amendments", {})):
        problems.append("Amendment records differ between definition and freeze")
    for name, digest in frozen.get("amendments", {}).items():
        path = Path(definition_path).parent / name
        if not path.is_file() or sha(path.read_bytes()) != digest:
            problems.append("Amendment record missing or changed: " + name)
    declared = definition.get("runtime", {}).get("python")
    if "%d.%d" % sys.version_info[:2] != declared:
        problems.append("Python runtime differs from the declared " + str(declared))
    tz = definition.get("runtime", {}).get("tzdata")
    if tz_identity()["tzdata_package"] != tz:
        problems.append("tzdata package differs from the declared " + str(tz))
    if any(FROZEN_MODULES[rel] != definition.get("code", {}).get(rel) for rel in FROZEN_MODULES):
        problems.append("Reused module identities differ from the definition")
    return definition, sha(raw), problems


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
            "provenance": [
                {"source_index": o["source_index"], "row_index": o["row_index"]} for o in group
            ],
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


def window_end(report, next_report, rules):
    """Last filing date in the window: day 83, and strictly before the issuer's next 10-Q
    period end, so a later period's results release can never enter."""
    end = report + timedelta(days=rules["window_days_after_report_date"])
    return end if next_report is None else min(end, next_report - timedelta(days=1))


def next_report_dates(manifests):
    """Each frozen 10-Q reportDate mapped to the issuer's next later frozen reportDate."""
    dates = set()
    for manifest in manifests:
        try:
            dates.add(day(manifest["registry_row"]["reportDate"]))
        except (KeyError, TypeError, ValueError):
            continue
    ordered = sorted(dates)
    return {a: b for a, b in zip(ordered, ordered[1:])}


def classify(q_row, canonical, coverage, calendar, positions, rules, next_report=None):
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
    end = window_end(report, next_report, rules)
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
            result["conflicts"].append(
                {
                    "accession": other_accession,
                    "variants": other["variants"],
                    "provenance": other["provenance"],
                }
            )
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
        raise AuditError("Source worker lock is missing or not a file: " + lock.as_posix())
    own_path = root / "audit.lock.sqlite"
    if own_path.exists() and not own_path.is_file():
        raise AuditError("Audit lock is invalid: not a regular file")
    try:
        own = sqlite3.connect(own_path, timeout=0)
    except sqlite3.DatabaseError as exc:
        raise AuditError("Audit lock is invalid: " + str(exc)) from exc
    reader = None
    try:
        try:
            own.execute("BEGIN EXCLUSIVE")
            own.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as exc:
            raise AuditError("Another timing audit holds the lock, or it is invalid") from exc
        try:
            reader = sqlite3.connect(lock.resolve().as_uri() + "?mode=ro", uri=True, timeout=0)
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as exc:
            raise AuditError(
                "A source capture worker holds the capture lock, or it is invalid"
            ) from exc
        yield "read_guard_held"
    finally:
        for connection in (reader, own):
            if connection:
                try:
                    connection.rollback()
                finally:
                    connection.close()


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
            discovery_path = source_root / "issuers" / issuer["symbol"] / "discovery.json"
            if not discovery_path.is_file():
                raise IssuerUnavailable("retained discovery.json not present")
            discovery = load(discovery_path)
            if sorted(r["accessionNumber"] for r in discovery.get("original_accessions", [])) != [
                m["registry_row"]["accessionNumber"] for m in own
            ]:
                raise IssuerUnavailable("registered 10-Q set differs from discovery originals")
            rebuilt = reconstruct_issuer(issuer, discovery, request, source_root, repo)
            canonical = canonicalize(rebuilt["occurrences"])
            form_counts = Counter(o["row"].get("form") for o in rebuilt["occurrences"])
            # Conflicting accessions are never counted as one variant; they are listed instead.
            clean_8k = [
                c["row"]
                for c in canonical.values()
                if not c["conflict"] and c["row"].get("form") == rules["candidate_form"]
            ]
            item_rows = [
                r for r in clean_8k if rules["item_token"] in (items_tokens(r.get("items")) or ())
            ]
            family = {rules["candidate_form"], rules["amendment_form"]}
            record.update(
                sources=rebuilt["sources"],
                coverage=rebuilt["coverage"],
                occurrences=len(rebuilt["occurrences"]),
                unique_accessions=len(canonical),
                duplicate_occurrences=len(rebuilt["occurrences"]) - len(canonical),
                conflicting_accessions=sorted(a for a, c in canonical.items() if c["conflict"]),
                conflict_evidence={
                    a: {"variants": c["variants"], "provenance": c["provenance"]}
                    for a, c in sorted(canonical.items())
                    if c["conflict"]
                },
                raw_8k_occurrences=form_counts.get(rules["candidate_form"], 0),
                unique_item_2_02_8k=len(item_rows),
                empty_primary_document_8k=sum(not r.get("primaryDocument") for r in clean_8k),
                conflicting_8k_family_accessions=sorted(
                    a
                    for a, c in canonical.items()
                    if c["conflict"] and any(v.get("form") in family for v in c["variants"])
                ),
            )
        except IssuerUnavailable as exc:
            record.update(status="unavailable", error=str(exc))
            canonical = None
        issuers.append(record)
        following = next_report_dates(own)
        for manifest in own:
            # The 10-Q clock comes from its frozen manifest, so it exists even when sources do not.
            q_row = manifest["registry_row"]
            q_session = entry_session(
                q_row.get("acceptanceDateTime"), q_row.get("filingDate"), calendar
            )[0]
            try:
                report = day(q_row["reportDate"])
                late = day(q_row["filingDate"]) > window_end(report, following.get(report), rules)
            except (KeyError, TypeError, ValueError):
                report, late = None, None
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
                    following.get(report),
                )
            if result["q_entry_session"] not in (None, q_session) or result[
                "late_10q_beyond_window"
            ] not in (None, late):
                raise AuditError("Classification and manifest 10-Q clocks differ")
            result.update(q_entry_session=q_session, late_10q_beyond_window=late)
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


def write_atomic(path, data):
    """Write through a sibling temporary file and replace, so a crash never truncates a record."""
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return sha(data)


def write_json(path, value):
    return write_atomic(path, (json.dumps(value, indent=1) + "\n").encode("utf-8"))


def run(definition_path=DEFINITION, freeze_path=FREEZE, repo=REPO, output_root=ROOT):
    # The declaration lives in this study directory; every source input is read under the lock.
    definition, definition_sha, problems = definition_problems(definition_path, freeze_path)
    if problems:
        raise AuditError(problems[0])
    with locks(repo / definition["paths"]["source_root"], output_root) as guard:
        state = input_state(repo, definition)
        problems = check_inputs(repo, definition, state)
        if problems:
            raise AuditError("Bound inputs are missing or changed: " + json.dumps(problems[:20]))
        load_frozen(repo)
        attempt = output_root / "attempts" / uuid.uuid4().hex
        attempt.mkdir(parents=True, exist_ok=False)
        meta = {
            "attempt": attempt.name,
            "definition_sha256": definition_sha,
            "started_at_utc": now(),
            "network_requests": 0,
            "prices_or_returns_read": False,
            "runtime": runtime_identity(),
            "input_identities": state,
            "status": "running",
        }
        write_json(attempt / "attempt.json", meta)
        try:
            issuers, rows, summary = audit(definition, repo)
            if input_state(repo, definition) != state or check_inputs(repo, definition):
                raise AuditError("Bound inputs appeared, disappeared or changed during the audit")
            files = {
                "issuers.json": write_json(attempt / "issuers.json", issuers),
                "events.json": write_json(attempt / "events.json", rows),
            }
            table = io.StringIO(newline="")
            writer = csv.DictWriter(table, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            files["events.csv"] = write_atomic(
                attempt / "events.csv", table.getvalue().encode("utf-8")
            )
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


def lock_busy(path):
    """Read-only probe: a problem string when the SQLite lock file is held or not a database."""
    if not path.exists():
        return None
    if not path.is_file():
        return "not a valid SQLite lock file: not a regular file"
    try:
        probe = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0)
    except sqlite3.DatabaseError as exc:
        return "not a valid SQLite lock file: " + str(exc)
    try:
        probe.execute("BEGIN")
        probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return None
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc):
            return "held by another process"
        return "not a valid SQLite lock file: " + str(exc)
    except sqlite3.DatabaseError as exc:
        return "not a valid SQLite lock file: " + str(exc)
    finally:
        try:
            probe.rollback()
        finally:
            probe.close()


def preflight(definition_path=DEFINITION, repo=REPO, freeze_path=FREEZE, output_root=ROOT):
    """What a real run would meet, without writing: blocking problems stop the run, while
    issuer_unavailable lists absent per-issuer files the run keeps in every denominator."""
    definition, _, declaration = definition_problems(definition_path, freeze_path)
    blocking = [{"path": "definition", "problem": p} for p in declaration]
    blocking += check_inputs(repo, definition)
    state = input_state(repo, definition)
    unavailable = [
        {"path": rel, "problem": "missing"}
        for rel in definition["issuer_inputs"]
        if state[rel] is None
    ]
    source_root = repo / definition["paths"]["source_root"]
    capture_lock = source_root / "capture.lock.sqlite"
    rel_lock = capture_lock.relative_to(repo).as_posix()
    if not capture_lock.is_file():
        blocking.append({"path": rel_lock, "problem": "missing"})
    for path, rel in [
        (capture_lock, rel_lock),
        (output_root / "audit.lock.sqlite", "audit.lock.sqlite"),
    ]:
        busy = lock_busy(path)
        if busy:
            blocking.append({"path": rel, "problem": busy})
    request_rel = definition["paths"]["source_request"]
    if state.get(request_rel) != definition["inputs"].get(request_rel):
        return {"ready": False, "blocking": blocking, "issuer_unavailable": unavailable}
    reuse = {r["url"]: r for r in load(repo / request_rel)["reuse"]}
    for rel, digest in definition["issuer_inputs"].items():
        # Only discovery files whose bytes match their bound identity are parsed.
        if not rel.endswith("/discovery.json") or state[rel] != digest:
            continue
        for meta in load(repo / rel).get("sources", []):
            try:
                resolve_source(meta, source_root, repo, reuse)
            except IssuerUnavailable as exc:
                unavailable.append(
                    {"path": meta.get("path"), "problem": str(exc), "url": meta.get("url")}
                )
            except AuditError as exc:
                blocking.append(
                    {"path": meta.get("path"), "problem": str(exc), "url": meta.get("url")}
                )
    return {"ready": not blocking, "blocking": blocking, "issuer_unavailable": unavailable}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight", action="store_true", help="check bound inputs only; no audit output"
    )
    args = parser.parse_args()
    if args.preflight:
        print(json.dumps(preflight(), indent=1))
    else:
        print(json.dumps({"attempt": str(run())}))

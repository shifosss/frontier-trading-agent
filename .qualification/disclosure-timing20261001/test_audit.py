"""Offline synthetic checks for the 8-K Item 2.02 timing audit. No SEC, price or outcome data."""

import hashlib
import importlib.util
import json
import re
import socket
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
E = ".qualification/earnings-quality20260928"


def module():
    spec = importlib.util.spec_from_file_location("timing_audit_under_test", HERE / "audit.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = module()
FROZEN = json.loads((HERE / "definition.json").read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def row(acc, form, filed, accepted, report="", items="", primary="doc.htm"):
    return {
        "accessionNumber": acc,
        "filingDate": filed,
        "reportDate": report,
        "acceptanceDateTime": accepted,
        "form": form,
        "items": items,
        "primaryDocument": primary,
    }


def table(rows):
    keys = list(rows[0])
    return {k: [r[k] for r in rows] for k in keys}


def calendar():
    sessions, d = [], date(2019, 12, 2)
    while d <= date(2021, 3, 31):
        if d.weekday() < 5:
            s = d.isoformat()
            sessions.append(
                {"session": s, "open": s + "T14:30:00+00:00", "close": s + "T21:00:00+00:00"}
            )
        d += timedelta(days=1)
    return {"sessions": sessions}


def acc(cik, n):
    return f"{cik:010d}-20-{n:06d}"


# Issuer AAA (root only): single prior, same-session, after (+ 8-K/A and non-matching tokens).
AAA = [
    row(acc(1, 30), "8-K", "2020-11-05", "2020-11-05T21:10:00.000Z", "2020-11-05", "2.02,9.01"),
    row(acc(1, 29), "8-K/A", "2020-11-02", "2020-11-02T21:10:00.000Z", "2020-10-28", "2.02"),
    row(acc(1, 28), "10-Q", "2020-10-29", "2020-10-29T20:00:00.000Z", "2020-09-30"),
    row(acc(1, 27), "8-K", "2020-10-15", "2020-10-15T20:00:00.000Z", "2020-10-15", "12.02,5.02"),
    row(acc(1, 26), "8-K", "2020-09-30", "2020-09-30T20:00:00.000Z", "2020-09-30", "2.02"),
    row(acc(1, 20), "10-Q", "2020-07-30", "2020-07-30T11:00:00.000Z", "2020-06-30"),
    row(acc(1, 11), "8-K", "2020-06-23", "2020-06-23T20:05:00.000Z", "2020-06-23", "2.02"),
    row(acc(1, 19), "8-K", "2020-07-30", "2020-07-30T10:30:00.000Z", "2020-07-30", "2.02,9.01"),
    row(acc(1, 10), "10-Q", "2020-05-01", "2020-05-01T20:30:00.000Z", "2020-03-31"),
    row(acc(1, 8), "8-K", "2020-04-28", "2020-04-28T20:05:00.000Z", "2020-04-28", "2.02, 9.01"),
    row(acc(1, 7), "8-K", "2020-04-20", "2020-04-20T20:05:00.000Z", "2020-04-20", "5.02"),
]
# Issuer BBB (root + one history page): multiple, coverage gap, empty items, duplicate occurrence.
BBB_ROOT = [
    row(acc(2, 40), "10-Q", "2020-11-04", "2020-11-04T21:00:00.000Z", "2020-09-30"),
    row(acc(2, 39), "8-K", "2020-10-20", "2020-10-20T21:00:00.000Z", "2020-10-20", ""),
    row(acc(2, 31), "10-Q", "2020-08-05", "2020-08-05T21:00:00.000Z", "2020-06-30"),
    row(acc(2, 30), "8-K", "2020-07-28", "2020-07-28T21:00:00.000Z", "2020-07-28", "2.02"),
    row(acc(2, 29), "8-K", "2020-07-21", "2020-07-21T12:00:00.000Z", "2020-07-21", "2.02,7.01"),
    row(acc(2, 25), "8-K", "2020-06-25", "2020-06-25T21:00:00.000Z", "2020-06-25", "5.02"),
]
BBB_HISTORY = [
    row(acc(2, 20), "10-Q", "2020-05-06", "2020-05-06T21:00:00.000Z", "2020-03-31"),
    row(acc(2, 18), "8-K", "2020-04-30", "2020-04-30T21:00:00.000Z", "2020-04-30", "2.02"),
]
# Issuer CCC: retained history page is missing; its 10-Q stays in the denominator.
# Its 10-Q is also filed after reportDate + 83 days, so it carries the late flag.
CCC_ROOT = [row(acc(3, 10), "10-Q", "2020-09-25", "2020-09-25T21:00:00.000Z", "2020-06-30")]
CCC_HISTORY = [
    row(acc(3, 5), "8-K", "2020-04-30", "2020-04-30T21:00:00.000Z", "2020-04-30", "2.02")
]
# Issuer DDD: one 8-K accession appears twice with different items -> conflict.
DDD_ROOT = [
    row(acc(4, 10), "10-Q", "2020-08-06", "2020-08-06T21:00:00.000Z", "2020-06-30"),
    row(acc(4, 9), "8-K", "2020-07-20", "2020-07-20T21:00:00.000Z", "2020-07-20", "2.02"),
]
DDD_HISTORY = [
    row(acc(4, 9), "8-K", "2020-07-20", "2020-07-20T21:00:00.000Z", "2020-07-20", "8.01")
]

ISSUERS = [
    ("AAA", 1, AAA, None),
    ("BBB", 2, BBB_ROOT, ("2020-01-01", "2020-05-31", BBB_HISTORY)),
    ("CCC", 3, CCC_ROOT, ("2020-01-01", "2020-05-31", CCC_HISTORY)),
    ("DDD", 4, DDD_ROOT, ("2019-01-01", "2020-07-31", DDD_HISTORY)),
]
QUALIFIED = {acc(1, 10): "2020-05-04", acc(1, 20): "2020-07-31", acc(2, 31): "2020-08-06"}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else (json.dumps(value) + "\n").encode()
    path.write_bytes(data)
    return data


def build(tmp, drop_history_for=("CCC",), events_override=None):
    repo = tmp / "repo"
    source = repo / E / "source"
    issuers, reuse = [], []
    write(source / "capture.lock.sqlite", b"")
    for symbol, number, root_rows, history in ISSUERS:
        cik = f"{number:010d}"
        issuers.append({"symbol": symbol, "cik": cik})
        files = []
        if history:
            files = [
                {
                    "name": f"CIK{cik}-submissions-001.json",
                    "filingFrom": history[0],
                    "filingTo": history[1],
                }
            ]
        body = {
            "cik": str(number),
            "tickers": [symbol],
            "filings": {"recent": table(root_rows), "files": files},
        }
        raw = json.dumps(body).encode()
        rel = f".qualification/reused-profiles/raw/{sha(raw)}.bin"
        write(repo / rel, raw)
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        reuse.append({"url": url, "path": rel, "sha256": sha(raw), "bytes": len(raw)})
        sources = [dict(reuse[-1], reused=True, status=200)]
        rows = list(root_rows)
        if history:
            hist = json.dumps(table(history[2])).encode()
            if symbol not in drop_history_for:
                write(source / "raw" / (sha(hist) + ".bin"), hist)
            sources.append(
                {
                    "url": "https://data.sec.gov/submissions/" + files[0]["name"],
                    "status": 200,
                    "reused": False,
                    "sha256": sha(hist),
                    "bytes": len(hist),
                    "path": "raw/" + sha(hist) + ".bin",
                }
            )
            rows += history[2]
        originals = [r for r in rows if r["form"] == "10-Q"]
        write(
            source / "issuers" / symbol / "discovery.json",
            {
                "complete": True,
                "error": None,
                "sources": sources,
                "rows": rows,
                "original_accessions": originals,
            },
        )
        for q in originals:
            write(
                source / "filings" / symbol / (q["accessionNumber"] + ".json"),
                {"issuer": issuers[-1], "registry_row": q, "status": "captured"},
            )
    request = {
        "issuers": issuers,
        "filed_from": "2012-01-01",
        "filed_through": "2025-12-31",
        "max_history_pages_per_issuer": 8,
        "reuse": reuse,
    }
    write(source / "request.json", request)
    write(repo / FROZEN["paths"]["calendar"], calendar())
    events = events_override or [
        {"accession": a, "strategy_source_status": "qualified", "entry_session": s}
        for a, s in QUALIFIED.items()
    ]
    write(repo / FROZEN["paths"]["qualification_events"], events)
    skip = ("inputs", "issuer_inputs", "code", "filings", "denominators")
    definition = {k: v for k, v in FROZEN.items() if k not in skip}
    manifests = sorted((source / "filings").glob("*/*.json"))
    definition["filings"] = {
        "root": E + "/source/filings",
        "count": len(manifests),
        "digest_sha256": m.manifest_digest(repo, manifests),
    }
    definition["denominators"] = {
        "issuers": 4,
        "registered_originals": len(manifests),
        "strategy_source_qualified": len(QUALIFIED),
    }
    bound = [
        source / "request.json",
        repo / FROZEN["paths"]["calendar"],
        repo / FROZEN["paths"]["qualification_events"],
    ]
    issuer_bound = sorted((source / "issuers").glob("*/discovery.json"))
    issuer_bound += [repo / r["path"] for r in reuse]
    for rel in m.FROZEN_MODULES:
        write(repo / rel, (REPO / rel).read_bytes())

    def identities(paths):
        return {p.relative_to(repo).as_posix(): sha(p.read_bytes()) for p in paths}

    definition["inputs"] = identities(bound)
    definition["issuer_inputs"] = identities(issuer_bound)
    definition["code"] = dict(m.FROZEN_MODULES)
    study = tmp / "study"
    study.mkdir(parents=True)
    amendments = {}
    for record in FROZEN["amendments"]:
        amendments[record["record"]] = sha(
            write(study / record["record"], (HERE / record["record"]).read_bytes())
        )
    raw = write(study / "definition.json", definition)
    write(study / "freeze.json", {"definition_sha256": sha(raw), "amendments": amendments})
    return repo, study


def run(tmp, **kwargs):
    repo, study = build(tmp, **kwargs)
    attempt = m.run(study / "definition.json", study / "freeze.json", repo, study)
    events = {r["accession"]: r for r in json.loads((attempt / "events.json").read_text())}
    return attempt, events, json.loads((attempt / "summary.json").read_text())


def test_classifications_and_leads(tmp_path):
    attempt, events, summary = run(tmp_path)
    assert events[acc(1, 10)]["status"] == "single_prior"
    assert events[acc(1, 10)]["earliest_prior_lead_sessions"] == 3
    assert events[acc(1, 10)]["q_entry_session"] == "2020-05-04"
    assert events[acc(1, 20)]["status"] == "single_same_session"
    third = events[acc(1, 28)]
    assert third["status"] == "single_after" and third["amendments"] == [acc(1, 29)]
    assert events[acc(2, 31)]["status"] == "multiple" and events[acc(2, 31)]["n_prior"] == 2
    assert events[acc(2, 20)]["status"] == "window_coverage_incomplete"
    assert events[acc(2, 40)]["status"] == "ambiguous_metadata"
    assert events[acc(2, 40)]["items_unknown"] == [acc(2, 39)]
    assert events[acc(3, 10)]["status"] == "issuer_unavailable"
    assert events[acc(4, 10)]["status"] == "ambiguous_metadata"
    (conflict,) = events[acc(4, 10)]["conflicts"]
    assert conflict["accession"] == acc(4, 9)
    assert [v["items"] for v in conflict["variants"]] == ["2.02", "8.01"]
    assert [x["source_index"] for x in conflict["provenance"]] == [0, 1]
    assert len(events) == 8
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["status"] == "complete" and meta["network_requests"] == 0
    for name, digest in meta["files"].items():
        assert sha((attempt / name).read_bytes()) == digest


def test_bounds_and_verdict(tmp_path):
    _, _, summary = run(tmp_path)
    whole = summary["strata"]["all_registered_originals"]
    # Clean priors: AAA q1 and BBB multiple. Definitely none: same-session and after.
    assert whole["with_prior_candidate_lower"] == 2
    assert whole["with_prior_candidate_upper"] == 8 - 2
    primary = summary["strata"]["strategy_source_qualified"]
    assert primary["denominator"] == 3 and primary["with_prior_candidate_lower"] == 2
    assert primary["prior_share_upper"] == pytest.approx(2 / 3)
    assert summary["primary_stratum"] == "strategy_source_qualified"
    assert summary["primary_verdict"] == "supported_at_metadata_level"
    assert summary["issuers_unavailable"] == 1


def test_exact_item_token_and_window(tmp_path):
    _, events, _ = run(tmp_path)
    candidates = [c["accession"] for e in events.values() for c in e["candidates"]]
    assert acc(1, 27) not in candidates  # "12.02" is not Item 2.02
    assert acc(1, 26) not in candidates  # filed on the period end, outside the window
    assert acc(1, 7) not in candidates  # Item 5.02 only
    assert acc(1, 29) not in candidates  # 8-K/A is reported, never a candidate
    # reportDate + 84 days is the earliest possible next-quarter end, so it is outside the window.
    assert acc(1, 11) not in candidates
    assert events[acc(1, 10)]["status"] == "single_prior"


def test_coverage_union():
    assert m.covered(
        [("2020-01-01", "2020-05-31"), ("2020-06-01", "9999-12-31")],
        date(2020, 4, 1),
        date(2020, 6, 23),
    )
    assert not m.covered(
        [("2020-01-01", "2020-05-31"), ("2020-07-21", "9999-12-31")],
        date(2020, 4, 1),
        date(2020, 6, 23),
    )


def test_entry_session_must_match_completed_study(tmp_path):
    events = [
        {
            "accession": acc(1, 10),
            "strategy_source_status": "qualified",
            "entry_session": "2020-05-05",
        },
        {
            "accession": acc(1, 20),
            "strategy_source_status": "qualified",
            "entry_session": "2020-07-31",
        },
        {
            "accession": acc(2, 31),
            "strategy_source_status": "qualified",
            "entry_session": "2020-08-06",
        },
    ]
    repo, study = build(tmp_path, events_override=events)
    with pytest.raises(m.AuditError, match="entry session differs"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    (failed,) = (study / "attempts").iterdir()
    assert json.loads((failed / "failure.json").read_text())["status"] == "failed"


def test_unavailable_issuer_clock_is_still_checked(tmp_path):
    # CCC's sources are missing, but its 10-Q clock comes from the frozen manifest.
    saved = [
        {"accession": a, "strategy_source_status": "qualified", "entry_session": s}
        for a, s in QUALIFIED.items()
    ]
    right = saved + [
        {"accession": acc(3, 10), "strategy_source_status": "x", "entry_session": "2020-09-28"}
    ]
    repo, study = build(tmp_path / "right", events_override=right)
    attempt = m.run(study / "definition.json", study / "freeze.json", repo, study)
    rows = {r["accession"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows[acc(3, 10)]["status"] == "issuer_unavailable"
    assert rows[acc(3, 10)]["q_entry_session"] == "2020-09-28"
    assert rows[acc(3, 10)]["late_10q_beyond_window"] is True
    summary = json.loads((attempt / "summary.json").read_text())
    assert summary["strata"]["all_registered_originals"]["late_10q_beyond_window"] == 1
    wrong = saved + [
        {"accession": acc(3, 10), "strategy_source_status": "x", "entry_session": "2020-09-29"}
    ]
    repo, study = build(tmp_path / "wrong", events_override=wrong)
    with pytest.raises(m.AuditError, match="entry session differs"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)


def test_raw_corruption_stops_attempt(tmp_path):
    repo, study = build(tmp_path)
    raw = next((repo / E / "source/raw").glob("*.bin"))
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(m.AuditError, match="do not match recorded identity"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)


def test_changed_definition_or_input_refused(tmp_path):
    repo, study = build(tmp_path)
    (study / "definition.json").write_bytes((study / "definition.json").read_bytes() + b" ")
    with pytest.raises(m.AuditError, match="frozen declaration"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    repo, study = build(tmp_path / "second")
    discovery = repo / E / "source/issuers/AAA/discovery.json"
    discovery.write_bytes(discovery.read_bytes() + b" ")
    with pytest.raises(m.AuditError, match="missing or changed"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    assert not (study / "attempts").exists()


def test_missing_or_held_source_lock_refused(tmp_path):
    repo, study = build(tmp_path)
    lock = repo / E / "source/capture.lock.sqlite"
    writer = sqlite3.connect(lock, timeout=0)
    writer.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(m.AuditError, match="holds the capture lock"):
            m.run(study / "definition.json", study / "freeze.json", repo, study)
    finally:
        writer.rollback()
        writer.close()
    lock.unlink()
    with pytest.raises(m.AuditError, match="lock is missing"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    assert not (study / "attempts").exists()
    assert {"path": E + "/source/capture.lock.sqlite", "problem": "missing"} in m.preflight(
        study / "definition.json", repo, study / "freeze.json"
    )


def test_preflight_names_missing_retained_source(tmp_path):
    repo, study = build(tmp_path)
    problems = m.preflight(study / "definition.json", repo, study / "freeze.json")
    assert [p["url"] for p in problems] == [
        "https://data.sec.gov/submissions/CIK0000000003-submissions-001.json"
    ]


def test_no_network_and_append_only(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network use attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    repo, study = build(tmp_path)
    first = m.run(study / "definition.json", study / "freeze.json", repo, study)
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    second = m.run(study / "definition.json", study / "freeze.json", repo, study)
    assert first != second
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before


def test_frozen_declaration_identity():
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert sha((HERE / "definition.json").read_bytes()) == frozen["definition_sha256"]
    for name, digest in frozen.get("amendments", {}).items():
        assert sha((HERE / name).read_bytes()) == digest, name
    for rel, digest in FROZEN["code"].items():
        assert sha((REPO / rel).read_bytes()) == digest, rel
    assert FROZEN["denominators"] == {
        "issuers": 100,
        "registered_originals": 4057,
        "captured_originals": 3867,
        "strategy_source_qualified": 2010,
    }
    manifests = m.manifest_paths(REPO, FROZEN)
    assert len(manifests) == FROZEN["filings"]["count"] == 4057
    assert m.manifest_digest(REPO, manifests) == FROZEN["filings"]["digest_sha256"]
    assert sum(p.endswith("/discovery.json") for p in FROZEN["issuer_inputs"]) == 100
    assert len(FROZEN["issuer_inputs"]) == 200
    assert {"pyproject.toml", "uv.lock"} <= set(FROZEN["inputs"])
    assert all(FROZEN["code"][rel] == digest for rel, digest in m.FROZEN_MODULES.items())


def test_missing_issuer_discovery_keeps_denominator(tmp_path):
    repo, study = build(tmp_path)
    (repo / E / "source/issuers/DDD/discovery.json").unlink()
    attempt = m.run(study / "definition.json", study / "freeze.json", repo, study)
    rows = {r["accession"]: r for r in json.loads((attempt / "events.json").read_text())}
    assert rows[acc(4, 10)]["status"] == "issuer_unavailable"
    assert rows[acc(4, 10)]["reasons"] == ["retained discovery.json not present"]
    assert len(rows) == 8
    problems = m.preflight(study / "definition.json", repo, study / "freeze.json")
    missing = [p["path"] for p in problems if p["problem"] == "missing"]
    assert E + "/source/issuers/DDD/discovery.json" in missing


def test_conflicts_excluded_from_issuer_counts(tmp_path):
    attempt, _, _ = run(tmp_path)
    issuers = {i["issuer"]["symbol"]: i for i in json.loads((attempt / "issuers.json").read_text())}
    evidence = issuers["DDD"]["conflict_evidence"][acc(4, 9)]
    assert len(evidence["variants"]) == 2 and len(evidence["provenance"]) == 2
    assert issuers["DDD"]["unique_item_2_02_8k"] == 0
    assert issuers["DDD"]["conflicting_8k_family_accessions"] == [acc(4, 9)]
    assert issuers["AAA"]["unique_item_2_02_8k"] == 5


def test_changed_module_is_not_executed(tmp_path):
    marker = tmp_path / "executed"
    module = tmp_path / "module.py"
    module.write_text(f"open({str(marker)!r}, 'w').close()\n")
    with pytest.raises(m.AuditError, match="not executed"):
        m.load_verified_module(module, "0" * 64, "changed_module")
    assert not marker.exists()
    m.load_verified_module(module, sha(module.read_bytes()), "verified_module")
    assert marker.exists()


def test_amendment_records_and_runtime_checked(tmp_path):
    repo, study = build(tmp_path)
    record = study / FROZEN["amendments"][0]["record"]
    record.write_bytes(record.read_bytes() + b" ")
    with pytest.raises(m.AuditError, match="Amendment record"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    record.unlink()
    with pytest.raises(m.AuditError, match="Amendment record"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    repo, study = build(tmp_path / "runtime")
    definition = json.loads((study / "definition.json").read_text())
    definition["runtime"] = dict(definition["runtime"], python="3.12")
    raw = write(study / "definition.json", definition)
    freeze = json.loads((study / "freeze.json").read_text())
    write(study / "freeze.json", dict(freeze, definition_sha256=sha(raw)))
    with pytest.raises(m.AuditError, match="Python runtime"):
        m.run(study / "definition.json", study / "freeze.json", repo, study)
    assert not (study / "attempts").exists()


def test_attempt_records_runtime_and_input_identities(tmp_path):
    attempt, _, _ = run(tmp_path)
    meta = json.loads((attempt / "attempt.json").read_text())
    assert meta["runtime"]["python"].startswith("3.13")
    assert set(meta["runtime"]) >= {"tzdata_package", "zoneinfo_tzpath", "sqlite", "platform"}
    assert meta["input_identities"][E + "/source/issuers/AAA/discovery.json"]


def test_reused_definitions_run_without_module_imports(tmp_path):
    module = tmp_path / "frozen.py"
    module.write_text(
        "import module_that_does_not_exist\n"
        "raise SystemExit('top level must not run')\n"
        "class Oops(Exception): pass\n"
        "def pick(x):\n    return re.sub('a', 'b', x)\n"
    )
    digest = sha(module.read_bytes())
    loaded = m.load_verified_definitions(module, digest, ["Oops", "pick"], {"re": re})
    assert loaded.pick("aa") == "bb" and issubclass(loaded.Oops, Exception)
    with pytest.raises(m.AuditError, match="missing or duplicated"):
        m.load_verified_definitions(module, digest, ["absent"], {})
    with pytest.raises(m.AuditError, match="not executed"):
        m.load_verified_definitions(module, "0" * 64, ["pick"], {"re": re})


def test_loading_audit_does_not_import_the_project_package():
    # capture.py's top-level `from frontier.historical_lab import _save` is never executed.
    assert "frontier.historical_lab" not in sys.modules


def test_preflight_reports_definition_drift(tmp_path):
    repo, study = build(tmp_path)
    before = m.preflight(study / "definition.json", repo, study / "freeze.json")
    assert not [p for p in before if p["path"] == "definition"]
    definition = json.loads((study / "definition.json").read_text())
    definition["interpretation"]["supported_if_lower_share_at_least"] = 0.1
    write(study / "definition.json", definition)
    problems = m.preflight(study / "definition.json", repo, study / "freeze.json")
    drift = {"path": "definition", "problem": "Definition bytes differ from the frozen declaration"}
    assert drift in problems

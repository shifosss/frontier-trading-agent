"""Offline source qualification: preserve every original and explicit source overlay."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parser():
    spec = importlib.util.spec_from_file_location("frozen_filing_features", ROOT / "features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_inputs(identities):
    for name, expected in identities.items():
        path = Path(name)
        actual = sha(path) if path.is_file() else None
        if actual != expected:
            raise ValueError("Source input changed: " + name)


def collect_records(registry, baseline_root, overlay_roots, repo_root):
    baseline_root, repo_root = Path(baseline_root).resolve(), Path(repo_root).resolve()
    identities, overlays, originals = {}, {}, {}

    def remember(path, missing=False):
        path = Path(path).resolve()
        if not path.is_file() and not missing:
            raise ValueError("Required source missing: " + str(path))
        if str(path) not in identities:
            identities[str(path)] = sha(path) if path.is_file() else None
        return identities[str(path)]

    if not registry.get("complete"):
        raise ValueError("Original registry is not complete")
    for item in registry["issuers"]:
        if not item["discovery"].get("complete"):
            raise ValueError("Issuer discovery is not complete")
        for row in item["discovery"]["original_accessions"]:
            key = item["issuer"]["symbol"], row["accessionNumber"]
            if key in originals:
                raise ValueError("Duplicate original registry accession")
            originals[key] = item["issuer"], row

    for directory in map(Path, overlay_roots):
        directory = directory.resolve()
        completion_path = directory / "completion.json"
        if not completion_path.is_file():
            raise ValueError("Overlay has no terminal completion manifest")
        remember(completion_path)
        completion = read(completion_path)
        results = completion.get("results", [])
        declared = completion.get("declared_original_accessions")
        if not isinstance(declared, int) or declared <= 0 or len(results) != declared:
            raise ValueError("Overlay terminal denominator differs from declaration")
        for item in results:
            issuer, row = item["issuer"], item["registry_row"]
            key = issuer["symbol"], row["accessionNumber"]
            if key not in originals or originals[key] != (issuer, row):
                raise ValueError("Overlay is outside the original registry identity")
            if key in overlays:
                raise ValueError("Conflicting overlays for " + str(key))
            path = directory / "filings" / key[0] / (key[1] + ".json")
            digest = remember(path)
            manifest = read(path)
            if manifest.get("issuer") != issuer or manifest.get("registry_row") != row:
                raise ValueError("Overlay manifest identity differs from terminal record")
            if "status" in item and manifest.get("status") != item["status"]:
                raise ValueError("Overlay terminal status differs from saved record")
            overlays[key] = directory, path, digest, manifest

    model = parser()
    records = []
    for (symbol, accession), (issuer, row) in originals.items():
        path = baseline_root / "filings" / symbol / (accession + ".json")
        baseline_sha = remember(path, missing=True)
        baseline = read(path) if baseline_sha is not None else None
        if baseline and (baseline.get("issuer") != issuer or baseline.get("registry_row") != row):
            raise ValueError("Saved baseline registry identity differs")
        effective_root, effective_path, effective_sha, effective = baseline_root, path, baseline_sha, baseline
        if (symbol, accession) in overlays:
            effective_root, effective_path, effective_sha, effective = overlays[symbol, accession]
            claim = effective.get("supplement_of", {})
            claimed_path = (repo_root / claim.get("original_manifest_path", "")).resolve()
            if (baseline is None or baseline.get("status") == "captured" or claimed_path != path.resolve()
                    or claim.get("original_manifest_sha256") != baseline_sha
                    or claim.get("original_error") != baseline.get("error")
                    or not claim.get("recovery_class")):
                raise ValueError("Overlay does not bind its exact baseline failure")
        source_input = {
            "baseline_path": str(path), "baseline_sha256": baseline_sha,
            "baseline_status": baseline.get("status") if baseline else "manifest_missing",
            "baseline_error": baseline.get("error") if baseline else "manifest_missing",
            "effective_path": str(effective_path), "effective_sha256": effective_sha,
            "effective_status": effective.get("status") if effective else "manifest_missing",
            "supplement_of": effective.get("supplement_of") if effective else None,
        }
        unavailable = {"symbol": symbol, "cik": issuer["cik"], "accession": accession,
                       "report_date": row.get("reportDate"), "filing_date": row.get("filingDate"),
                       "registry_acceptance_utc": row.get("acceptanceDateTime"),
                       "status": "unavailable", "u": None}
        if effective is None:
            result = dict(unavailable, reasons=["manifest_missing"])
        else:
            for source in effective.get("sources", []) + effective.get("fact_sources", []):
                raw_path = (repo_root if source.get("reused") or source["path"].startswith(".qualification/") else effective_root) / source["path"]
                if remember(raw_path) != source["sha256"]:
                    raise ValueError("Raw source identity differs: " + str(raw_path))
            try:
                result = model.qualify_filing(effective, effective_root, repo_root)
            except Exception as error:
                result = dict(unavailable, reasons=["qualification_exception: " + type(error).__name__ + ": " + str(error)])
        records.append(dict(result, source_input=source_input))
    return records, identities


def run(definition_path):
    definition_path = Path(definition_path).resolve()
    definition = read(definition_path)
    if definition.get("schema") != 1:
        raise ValueError("Unknown qualification definition")
    baseline = (REPO / definition["baseline_root"]).resolve()
    overlays = [(REPO / p).resolve() for p in definition["overlay_roots"]]
    registry_path, calendar_path = ((REPO / definition[k]).resolve() for k in ("registry", "calendar"))
    inputs = {str((REPO / p).resolve()): digest for p, digest in definition["inputs"].items()}
    required = {registry_path, calendar_path, REPO / "src/frontier/historical_lab.py"}
    required.update(ROOT / name for name in ("features.py", "test_features.py", "extraction-definition.json",
                    "extraction-amendment1.json", "interface.md", "run_qualification.py", "test_qualification.py"))
    required.update(directory / name for directory in [baseline, *overlays]
                    for name in ("request.json", "implementation.json", "completion.json"))
    if not {str(p.resolve()) for p in required}.issubset(inputs):
        raise ValueError("Definition omits required source/code identities")
    inputs[str(definition_path)] = sha(definition_path)
    attempt = ROOT / "attempts" / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    started = {"started_at": datetime.now(timezone.utc).isoformat(), "definition_path": str(definition_path),
               "definition_sha256": inputs[str(definition_path)], "python": sys.version, "status": "running"}
    _save(attempt / "attempt.json", started)
    try:
        verify_inputs(inputs)
        registry = read(registry_path)
        calendar = read(calendar_path)
        sessions = calendar["sessions"] if isinstance(calendar, dict) else calendar
        records, discovered = collect_records(registry, baseline, overlays, REPO)
        for name, digest in discovered.items():
            if name in inputs and inputs[name] != digest:
                raise ValueError("Source input changed during collection: " + name)
            inputs[name] = digest
        expected = definition["expected_original_records"]
        if len(records) != expected or read(baseline / "completion.json")["original_accessions"] != expected:
            raise ValueError("Original source denominator differs from definition")
        full_events = parser().build_features(records, sessions)
        events = [{k: v for k, v in r.items() if k not in ("all_facts", "selected_facts")} for r in full_events]
        verify_inputs(inputs)
        _save(attempt / "records.json", records)
        _save(attempt / "events.json", events)
        _save(attempt / "source-inputs.json", {"definition_sha256": started["definition_sha256"], "files": inputs})
        summary = {"status": "complete", "original_records": len(records), "events": len(events),
                   "financial_status": dict(Counter(r["status"] for r in records)),
                   "feature_status": dict(Counter(r["feature_status"] for r in events)),
                   "execution_status": dict(Counter(r.get("execution_status", "unavailable") for r in events)),
                   "selected": sum(r.get("selected", False) for r in events), "price_returns_read": False,
                   "by_symbol": {s: {"records": sum(r["symbol"] == s for r in records),
                                     "feature_qualified": sum(r["symbol"] == s and r["feature_status"] == "qualified" for r in events)}
                                 for s in sorted({r["symbol"] for r in records})},
                   "definition_sha256": started["definition_sha256"],
                   "files": {name: sha(attempt / name) for name in ("records.json", "events.json", "source-inputs.json")}}
        verify_inputs(inputs)
        _save(attempt / "summary.json", summary)
        _save(attempt / "attempt.json", dict(started, status="complete", completed_at=datetime.now(timezone.utc).isoformat()))
        print(json.dumps({"attempt": str(attempt), **{k: summary[k] for k in ("original_records", "financial_status", "feature_status")}}), flush=True)
        return attempt
    except Exception as error:
        _save(attempt / "failure.json", {"error": type(error).__name__ + ": " + str(error)})
        _save(attempt / "attempt.json", dict(started, status="failed"))
        raise


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--definition", required=True, type=Path)
    run(cli.parse_args().definition)

"""Offline coverage and request-accounting checks for the bounded September refresh."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "capture-workspace"
verification = json.loads((ROOT / "verification.json").read_text("utf-8"))
assert verification["status"] == "completed"
run = WORKSPACE / "artifacts/historical-lab/runs" / verification["run_id"]
definition = json.loads((run / "capture-definition.json").read_text("utf-8"))
records = json.loads((run / "capture-index.json").read_text("utf-8"))
failures = json.loads((run / "capture-failures.json").read_text("utf-8"))
members = {item["symbol"]: item for item in definition["instruments"]}
record_symbols = [item["symbol"] for item in records]
failure_symbols = [item["symbol"] for item in failures]
assert len(record_symbols) == len(set(record_symbols))
assert len(failure_symbols) == len(set(failure_symbols))
assert set(record_symbols).isdisjoint(failure_symbols)
assert set(record_symbols) | set(failure_symbols) == set(members)
responses = [json.loads(line) for line in (ROOT / "http-responses.jsonl").read_text("utf-8").splitlines()]
response_symbols = [unquote(urlparse(item["url"]).path.rsplit("/", 1)[1]) for item in responses]
assert set(response_symbols) <= set(members)
assert set(members) - set(response_symbols) <= set(failure_symbols)
response_digests = {item["sha256"] for item in responses}
assert len(response_symbols) == len(set(response_symbols)), "Unexpected duplicate public requests"
for record in records:
    assert record["spec"] == members[record["symbol"]]
    assert 1 <= record["rows"] <= 10
    body = WORKSPACE / "data/historical/capture-workspace" / record["path"]
    assert hashlib.sha256(body.read_bytes()).hexdigest() == record["sha256"]
    assert record["sha256"] in response_digests
coverage = Counter()
for record in records:
    currency = record["spec"]["currency"]
    coverage[currency + ":usable"] += 1
    coverage[currency + ":rows"] += record["rows"]
    coverage[currency + (":full_10_sessions" if record["rows"] == 10 else ":partial_window")] += 1
    coverage[currency + (":current_at_cutoff" if record["last_session"] == "2026-09-25" else ":stale_at_cutoff")] += 1
reason_counts = Counter()
for item in failures:
    error = item["error"]
    reason_counts["HTTP 404" if "404 Not Found" in error else error] += 1
summary = {
    "run_id": verification["run_id"], "status": "verified", "members": len(members),
    "captured": len(records), "failed": len(failures), "coverage": dict(coverage),
    "failure_reasons": dict(reason_counts), "http_status_counts": dict(Counter(str(item["status_code"]) for item in responses)),
    "capture_observation_dates": dict(Counter(item["captured_at"][:10] for item in records)),
    "responses": len(responses), "duplicate_symbol_requests": 0,
    "failed_without_http_response": sorted(set(members) - set(response_symbols)),
    "membership_partition_exact": True, "record_raw_hashes_verified": True,
    "main_state_unchanged": verification["main_state_unchanged"],
    "scope": "Request accounting and bounded coverage only; not complete corporate-action, security-identity, liquidity or performance qualification."
}
(ROOT / "coverage-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))

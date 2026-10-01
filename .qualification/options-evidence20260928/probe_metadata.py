"""Three frozen, retrospective option-metadata GETs; no quotes or trading actions."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import time

import httpx
from frontier.historical_lab import _save
from frontier.paper_broker import _paper_credentials

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEFINITION_SHA = "10726a45ec026cb023e248b303908575496fc837afb838823e09b042a3d56766"
URL = "https://paper-api.alpaca.markets/v2/options/contracts"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_definition(root):
    path = root / "request-definition.json"
    if digest(path) != DEFINITION_SHA:
        raise ValueError("The reviewed request definition changed")
    definition = json.loads(path.read_text(encoding="utf-8"))
    for name, expected in definition["existing_input_sha256"].items():
        if digest(REPO / name) != expected:
            raise ValueError("An original probe/source input changed: " + name)
    probe = definition["metadata_probe"]
    if len(probe["requests"]) != 3 or any(r["method"] != "GET" or r["url"] != URL for r in probe["requests"]):
        raise ValueError("The metadata-only request scope differs")
    return definition


def inspect_contract(symbol, rows):
    candidates = [row for row in rows if row.get("symbol") == symbol]
    result = {"symbol": symbol, "status": "missing", "candidate_count": len(candidates),
              "retrieval_time_only": True}
    if len(candidates) != 1:
        result["status"] = "ambiguous" if candidates else "missing"
        return result
    row = candidates[0]
    expected = {"root_symbol": "SPY", "underlying_symbol": "SPY", "expiration_date": "2024-03-15",
                "type": "call" if symbol[9] == "C" else "put", "status": "inactive"}
    differences = [key for key, value in expected.items() if row.get(key) != value]
    try:
        if Decimal(str(row.get("strike_price"))) != Decimal(symbol[10:]) / 1000:
            differences.append("strike_price")
    except InvalidOperation:
        differences.append("strike_price")
    result.update(status="identity_mismatch" if differences else "matched", identity_mismatches=differences,
                  terms=row, unavailable_fields=[key for key in ("id", "size", "style", "deliverables")
                                                if row.get(key) is None or row.get(key) == []])
    # Preserve a supplied size; do not substitute the usual 100 when absent or malformed.
    try:
        size = Decimal(str(row.get("size")))
        result["size_positive_finite"] = size.is_finite() and size > 0
    except InvalidOperation:
        result["size_positive_finite"] = False
    return result


async def fetch(client, request, probe, root, headers):
    raw = bytearray()
    report = {"id": request["id"], "status": "failed", "started_at": now(),
              "url": str(httpx.Request("GET", URL, params=request["params"]).url),
              "http_status": None, "truncated": False}
    try:
        async with asyncio.timeout(probe["maximum_wall_seconds_per_call"]):
            async with client.stream("GET", URL, params=request["params"], headers=headers) as response:
                report["http_status"] = response.status_code
                report["response_headers"] = {k: v for k, v in response.headers.items()
                    if k in {"date", "content-type", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"}}
                async for block in response.aiter_bytes(chunk_size=8192):
                    remaining = probe["maximum_response_bytes_per_call"] - len(raw)
                    raw.extend(block[:remaining])
                    if len(block) > remaining:
                        report["truncated"] = True
                        break
    except (httpx.HTTPError, TimeoutError) as error:
        report.update(error_kind=type(error).__name__, error=str(error))
    report.update(received_at=now(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    name = "raw-" + request["id"] + "-" + report["sha256"] + ".json"
    (root / name).write_bytes(raw)
    report["raw"] = name
    report["raw_completeness"] = "complete_response" if not report["truncated"] and "error_kind" not in report else "bounded_or_interrupted_prefix"
    rows = None
    if report["http_status"] != 200:
        report.setdefault("error_kind", "http_failure")
    elif report["truncated"]:
        report["error_kind"] = "response_size_cap"
    elif "error_kind" not in report:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get("option_contracts"), list):
                raise ValueError("Expected an option_contracts array")
            rows = body["option_contracts"]
            if any(not isinstance(row, dict) or not isinstance(row.get("symbol"), str) for row in rows):
                raise ValueError("Contract record has no string symbol")
            tokens = {key: body.get(key) for key in ("page_token", "next_page_token")}
            report.update(status="captured", **tokens, page_limited=any(tokens.values()),
                          returned_records=len(rows), unexpected_symbols=sorted({row["symbol"] for row in rows} - set(request["expected_symbols"])))
        except (ValueError, TypeError) as error:
            report.update(error_kind="schema_failure", error=str(error))
            rows = None
    _save(root / (request["id"] + ".response.json"), report)
    return report, rows


async def run(root=ROOT, *, transport=None):
    """Mock transport is used only by offline tests; normal main uses the fixed HTTPS host."""
    root = Path(root)
    definition = load_definition(root)
    probe = definition["metadata_probe"]
    requests = probe["requests"]
    result = {"status": "started", "started_at": now(), "definition_sha256": DEFINITION_SHA,
              "code_sha256": digest(Path(__file__)), "requests": [{"id": r["id"], "status": "unattempted"} for r in requests],
              "contracts": [{"symbol": s, "status": "unattempted"} for s in definition["scope"]["symbols"]],
              "historical_quote_requests": 0, "historical_quotes_qualified": False,
              "asof_membership_qualified": False, "historical_deliverable_history_qualified": False,
              "network_requests": 0, "performance_qualified": False}
    with (root / "attempt.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    stopped = False
    try:
        key, secret = _paper_credentials()
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        last_start = None
        async with httpx.AsyncClient(timeout=probe["http_timeout_seconds"], follow_redirects=False, transport=transport) as client:
            for i, request in enumerate(requests):
                if last_start is not None:
                    await asyncio.sleep(max(0., probe["minimum_seconds_between_request_starts"] - (time.monotonic() - last_start)))
                last_start = time.monotonic()
                result["network_requests"] += 1
                report, rows = await fetch(client, request, probe, root, headers)
                result["requests"][i] = report
                for j, contract in enumerate(result["contracts"]):
                    if contract["symbol"] in request["expected_symbols"]:
                        result["contracts"][j] = inspect_contract(contract["symbol"], rows) if rows is not None else {
                            "symbol": contract["symbol"], "status": "unavailable_request_failure", "request_id": request["id"]}
                _save(root / "attempt.json", result)
                if report["status"] != "captured":
                    stopped = True
                    result["stopped_after_request"] = request["id"]
                    break
    except Exception as error:
        stopped = True
        result.update(error_kind=type(error).__name__, error=str(error))
    complete = all(row["status"] == "matched" for row in result["contracts"])
    complete = complete and not any(r.get("page_limited") or r.get("unexpected_symbols") for r in result["requests"])
    result.update(status="incomplete" if stopped else "complete" if complete else "complete_with_coverage_gaps", finished_at=now())
    _save(root / "summary.json", result)
    _save(root / "attempt.json", result)
    return result


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps({"status": result["status"], "network_requests": result["network_requests"],
                      "contracts": [{"symbol": c["symbol"], "status": c["status"]} for c in result["contracts"]],
                      "historical_quote_requests": 0}))

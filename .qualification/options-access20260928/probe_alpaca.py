"""Single declared read-only historical option request; preserve raw success/failure."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

import httpx
from frontier.historical_lab import _save
from frontier.paper_broker import _paper_credentials

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    request_bytes = (ROOT / "alpaca-request.json").read_bytes()
    request = json.loads(request_bytes)
    assert request["url"] == "https://data.alpaca.markets/v1beta1/options/bars"
    assert not (ROOT / "alpaca-attempt.json").exists(), "Retained attempt must be reviewed; do not retry"
    attempt = {"started_at": now(), "status": "started",
               "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
               "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    _save(ROOT / "alpaca-attempt.json", attempt)
    try:
        key, secret = _paper_credentials()
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        raw = bytearray()
        with httpx.Client(timeout=request["timeout_seconds"], follow_redirects=False) as client:
            with client.stream("GET", request["url"], params=request["params"], headers=headers) as response:
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw) > request["maximum_response_bytes"]:
                        break
                metadata = {"http_status": response.status_code, "url": str(response.url),
                            "received_at": now(), "bytes": len(raw),
                            "truncated": len(raw) > request["maximum_response_bytes"]}
        digest = hashlib.sha256(raw).hexdigest()
        filename = "alpaca-raw-" + digest + ".json"
        (ROOT / filename).write_bytes(raw)
        metadata.update(raw=filename, sha256=digest)
        _save(ROOT / "alpaca-response.json", metadata)
        body = json.loads(raw) if not metadata["truncated"] else {}
        bars = body.get("bars") or {}
        summary = {**metadata, "bar_counts": {symbol: len(rows) for symbol, rows in bars.items()},
                   "bar_fields": sorted({key for rows in bars.values() for row in rows for key in row}),
                   "next_page_token_present": bool(body.get("next_page_token")),
                   "source_message": body.get("message"), "performance_qualified": False}
        _save(ROOT / "alpaca-summary.json", summary)
        attempt.update(status="complete" if metadata["http_status"] == 200 and not metadata["truncated"] else "failed",
                       finished_at=now(), response=metadata)
        _save(ROOT / "alpaca-attempt.json", attempt)
        print(json.dumps(summary))
    except Exception as error:
        attempt.update(status="failed", finished_at=now(), error=type(error).__name__ + ": " + str(error))
        _save(ROOT / "alpaca-attempt.json", attempt)
        raise


if __name__ == "__main__":
    main()

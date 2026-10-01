"""One missing study member: bounded SIP daily source capture, no account calls."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import time

import httpx
from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent / "T-price-source"
URL = "https://data.alpaca.markets/v2/stocks/bars"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    request = json.loads((ROOT / "request.json").read_text())
    identity = json.loads((ROOT / "implementation.json").read_text())
    assert sha(Path(__file__).read_bytes()) == identity["capture_sha256"]
    assert sha((ROOT / "request.json").read_bytes()) == identity["request_sha256"]
    assert not (ROOT / "attempt.json").exists(), "Inspect retained attempt; never blindly repeat requests"
    _save(ROOT / "attempt.json", {"started_at": datetime.now(timezone.utc).isoformat(), "status": "started"})
    headers = {
        "APCA-API-KEY-ID": os.environ["FRONTIER_ALPACA_PAPER_KEY"],
        "APCA-API-SECRET-KEY": os.environ["FRONTIER_ALPACA_PAPER_SECRET"],
    }
    summaries = []
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for adjustment in request["adjustments"]:
                pages, tokens, token = [], set(), None
                for number in range(request["maximum_pages_per_adjustment"]):
                    params = {**request["params"], "adjustment": adjustment}
                    if token is not None:
                        params["page_token"] = token
                    time.sleep(request["minimum_request_interval_seconds"])
                    metadata = {"requested_at": datetime.now(timezone.utc).isoformat(), "url": URL, "params": params}
                    response = client.get(URL, params=params, headers=headers)
                    raw = response.content
                    name = f"{adjustment}-{number:02d}-{sha(raw)}.json"
                    (ROOT / name).write_bytes(raw)
                    metadata.update(status=response.status_code, raw=name, sha256=sha(raw), bytes=len(raw),
                                    received_at=datetime.now(timezone.utc).isoformat())
                    _save(ROOT / f"{adjustment}-{number:02d}.metadata.json", metadata)
                    pages.append(metadata)
                    if response.status_code != 200:
                        raise RuntimeError(f"Historical T source HTTP{response.status_code}; raw failure retained")
                    body = response.json()
                    token = body.get("next_page_token")
                    if token is None:
                        summaries.append({"adjustment": adjustment, "pages": pages})
                        break
                    if token in tokens:
                        raise RuntimeError("Repeated source page token")
                    tokens.add(token)
                else:
                    raise RuntimeError("Declared historical T page limit exhausted")
        _save(ROOT / "completion.json", {"status": "captured", "sources": summaries,
              "request_sha256": identity["request_sha256"], "features_qualified": False,
              "completed_at": datetime.now(timezone.utc).isoformat()})
        _save(ROOT / "attempt.json", {"status": "complete", "completed_at": datetime.now(timezone.utc).isoformat()})
        print(json.dumps({"status": "captured", "adjustments": len(summaries),
                          "pages": sum(len(s["pages"]) for s in summaries)}), flush=True)
    except Exception as error:
        _save(ROOT / "attempt.json", {"status": "failed", "error": type(error).__name__ + ": " + str(error),
                                     "failed_at": datetime.now(timezone.utc).isoformat()})
        raise


if __name__ == "__main__":
    main()

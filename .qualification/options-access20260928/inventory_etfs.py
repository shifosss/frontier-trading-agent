"""Inventory frozen USD ETF raw sources only; no signals, returns or downloads."""
from pathlib import Path
import hashlib
import json

from frontier.historical_lab import _save

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/capture-index.json"
LISTING = REPO / "data/research/universe/snapshots/20260918T201012673731Z-2da49ecfd9bb.json"


def main():
    index = {row["symbol"]: row for row in json.loads(INDEX.read_bytes())}
    listing = json.loads(LISTING.read_bytes())
    selected = [row for row in listing["instruments"] if row["currency"] == "USD" and row["asset_type"] == "etf"]
    rows = []
    for spec in selected:
        row = {"symbol": spec["symbol"], "listing": spec, "status": "unavailable"}
        try:
            record = index[spec["symbol"]]
            source = REPO / "data/historical/capture-workspace" / record["path"]
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != record["sha256"]:
                raise ValueError("Frozen raw identity mismatch")
            body = json.loads(raw)["chart"]["result"][0]
            meta = body["meta"]
            if meta["symbol"] != spec["symbol"] or meta["currency"] != "USD":
                raise ValueError("Source symbol/currency differs")
            row.update(status="available_identity_verified", source={**record, "path": source.relative_to(REPO).as_posix()},
                       source_instrument_type=meta.get("instrumentType"), timestamps=len(body["timestamp"]),
                       quote_fields=sorted(body["indicators"]["quote"][0]),
                       adjusted_close_supplied="adjclose" in body["indicators"],
                       action_types=sorted(body.get("events", {})))
        except (OSError, KeyError, ValueError, TypeError) as error:
            row["error"] = type(error).__name__ + ": " + str(error)
        rows.append(row)
    output = {"purpose": "Source availability inventory, not a new ETF backtest or complete action/price qualification",
              "listing_sha256": hashlib.sha256(LISTING.read_bytes()).hexdigest(),
              "index_sha256": hashlib.sha256(INDEX.read_bytes()).hexdigest(), "requested": len(rows),
              "available": sum(row["status"] == "available_identity_verified" for row in rows),
              "rows": rows, "network_requests": 0, "strategy_outcomes_read": False}
    _save(Path(__file__).parent / "etf-source-inventory.json", output)
    print(json.dumps({"requested": len(rows), "available": output["available"],
                      "symbols": [row["symbol"] for row in rows]}))


if __name__ == "__main__":
    main()

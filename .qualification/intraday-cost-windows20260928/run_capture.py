"""Reuse the verified quote capture/analysis with bounded transport and retained failures."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import httpx
from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_capture(path, value):
    _save(path, value)
    if isinstance(value, dict) and value.get("status_code") in (401, 403, 429):
        raise PermissionError("Access/rate response preserved; no further requests")


def complete_denominator(definition):
    """Retain missing windows after a stop; never substitute another date/name."""
    results = []
    for window in definition["windows"]:
        paths = sorted(ROOT.glob("cost-" + window["id"] + "-page-*.capture.json"),
                       key=lambda p: int(p.name.split("-page-")[1].split(".")[0]))
        attempts = [(p, json.loads(p.read_text())) for p in paths]
        row = {"window": window["id"], "pages": [p.name for p, meta in attempts if meta.get("raw_file")],
               "request_attempts": [p.name for p, _ in attempts], "complete": False}
        if paths:
            meta = json.loads(paths[-1].read_text())
            if meta.get("status_code") == 200:
                body = json.loads((ROOT / meta["raw_file"]).read_bytes())
                row["complete"] = not body.get("next_page_token")
            if not row["complete"]:
                row["error"] = meta.get("error", "Incomplete pagination or unsuccessful response")
        else:
            row["error"] = "Not attempted after stop"
        results.append(row)
    _save(ROOT / "cost-capture-summary.json", results)
    return results


def main():
    implementation = json.loads((ROOT / "implementation.json").read_text())
    for name, expected in implementation["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    definition = json.loads((ROOT / "cost-definition.json").read_text())
    assert definition["endpoint"] == "https://data.alpaca.markets/v2/stocks/quotes"
    assert not list(ROOT.glob("cost-*-page-*.capture.json")), "Inspect existing attempts before resumption"
    probe = load("fixed_quote_capture", "cost-probe.py")
    probe.dump = save_capture

    class PacedClient(httpx.Client):
        last_request = 0.0

        def get(self, *args, **kwargs):
            time.sleep(max(0, definition["minimum_request_interval_seconds"] - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            return super().get(*args, **kwargs)

    probe.httpx.Client = PacedClient
    error = None
    try:
        probe.capture()
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    summary = complete_denominator(definition)
    load("fixed_quote_analysis", "cost-analyze.py").main()
    result = {"at": datetime.now(timezone.utc).isoformat(), "error": error,
              "planned_windows": len(summary), "complete_windows": sum(x["complete"] for x in summary),
              "planned_cells": definition["expected_cells"], "source_definition_sha256": implementation["files"]["cost-definition.json"]}
    _save(ROOT / "completion.json", result)
    print(json.dumps(result), flush=True)
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

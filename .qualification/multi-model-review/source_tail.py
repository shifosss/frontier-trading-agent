"""Inspect the saved Canadian HGB5 profit tail without obtaining or changing data."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from frontier.historical_data import read_history

RUN = ROOT / "artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a"
OUT = Path(__file__).parent


def read(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


result = read(RUN / "cad-result.json")
row = next(r for r in result["portfolios"] if r["strategy"] == "hist_gradient_boosting" and r["horizon"] == 5 and r["budget"] == 2000 and r["cost_bps"] == 40)
records = {r["symbol"]: r for r in read(RUN / "capture-index.json")}
trades = sorted(row["trade_records"], key=lambda r: -r["net_pnl"])
prices = {}


def history(symbol):
    if symbol not in prices:
        frame = read_history(ROOT / "data/historical/capture-workspace", records[symbol])
        prices[symbol] = frame.set_index("session")
    return prices[symbol]


def describe(trade):
    frame = history(trade["symbol"])
    entry, exit_ = frame.loc[trade["entry_session"]], frame.loc[trade["exit_session"]]
    path = frame.loc[trade["entry_session"] : trade["exit_session"]]
    daily = path.adjusted_close.pct_change(fill_method=None)
    return {
        **trade,
        "nominal_entry_price": float(entry.close),
        "nominal_exit_price": float(exit_.close),
        "synthetic_exit_price": trade["exit_notional"] / trade["quantity"],
        "nominal_price_return": float(exit_.close / entry.close - 1),
        "adjusted_gross_return": float(exit_.adjusted_close / entry.adjusted_close - 1),
        "entry_adjustment_ratio": float(entry.adjusted_close / entry.close),
        "exit_adjustment_ratio": float(exit_.adjusted_close / exit_.close),
        "largest_close_return_within_trade": float(daily.max()),
        "smallest_close_return_within_trade": float(daily.min()),
    }


tpx_trades = [trade for trade in trades if trade["symbol"] == "TPX-B.TO"]
record = records["TPX-B.TO"]
raw_path = ROOT / "data/historical/capture-workspace" / record["path"]
raw = raw_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == record["sha256"]
chart = json.loads(raw)["chart"]["result"][0]
sessions = pd.to_datetime(chart["timestamp"], unit="s", utc=True).tz_convert("America/Toronto").strftime("%Y-%m-%d")
provider = pd.DataFrame({"session": sessions, "provider_close": chart["indicators"]["quote"][0]["close"], "provider_adjusted_close": chart["indicators"]["adjclose"][0]["adjclose"]}).set_index("session")
normalized = history("TPX-B.TO")
joined = normalized[["close", "adjusted_close", "volume"]].join(provider)
joined["adjustment_ratio"] = joined.adjusted_close / joined.close
joined["nominal_daily_return"] = joined.close.pct_change(fill_method=None)
joined["adjusted_daily_return"] = joined.adjusted_close.pct_change(fill_method=None)
joined["provider_to_nominal_split_factor"] = joined.close / joined.provider_close
events = []
for kind, values in chart.get("events", {}).items():
    for item in values.values():
        stamp = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert("America/Toronto")
        events.append({"kind": kind, "session": str(stamp.date()), **item})
windows = []
for trade in tpx_trades[:5]:
    first = str((pd.Timestamp(trade["signal_session"]) - pd.Timedelta(days=3)).date())
    last = str((pd.Timestamp(trade["exit_session"]) + pd.Timedelta(days=3)).date())
    rows = joined.loc[first:last].reset_index().replace([np.inf, -np.inf], np.nan)
    windows.append({"trade": describe(trade), "source_rows": json.loads(rows.to_json(orient="records")), "nearby_reported_events": [event for event in events if first <= event["session"] <= last]})
jumps = joined.loc[joined.adjusted_daily_return.abs().nlargest(10).index].sort_values("adjusted_daily_return", ascending=False).reset_index()
report = {
    "account": {key: row[key] for key in ("currency", "strategy", "horizon", "budget", "cost_bps", "status", "total_return")},
    "net_pnl_total": row["trade_metrics"]["net_pnl_total"],
    "profit_concentration": row["profit_concentration"],
    "largest_ten_trades": [describe(trade) for trade in trades[:10]],
    "tpx_source_spec": record["spec"],
    "tpx_raw_sha256": record["sha256"],
    "tpx_provider_metadata": {key: chart["meta"].get(key) for key in ("symbol", "shortName", "longName", "instrumentType", "currency", "exchangeName", "fullExchangeName", "firstTradeDate")},
    "tpx_all_reported_splits": [event for event in events if event["kind"] == "splits"],
    "tpx_top_five_trade_windows": windows,
    "tpx_largest_absolute_adjusted_daily_moves": json.loads(jumps.to_json(orient="records")),
    "limitations": "Only frozen provider records were inspected. Matching synthetic arithmetic does not independently establish complete corporate-action history or ticker/issuer continuity.",
}
with (OUT / "cad-hgb5-source-tail.json").open("w", encoding="utf-8") as handle:
    json.dump(report, handle, allow_nan=False, indent=2)
print(json.dumps({"net_pnl_total": report["net_pnl_total"], "largest_ten_trades": report["largest_ten_trades"], "tpx_provider_metadata": report["tpx_provider_metadata"], "tpx_all_reported_splits": report["tpx_all_reported_splits"], "tpx_trade_count": len(tpx_trades)}, allow_nan=False))

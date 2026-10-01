"""Independent ledger arithmetic over committed account manifests; no fitting or status reads."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def close(actual, expected, label):
    if not np.allclose(actual, expected, rtol=1e-10, atol=1e-6, equal_nan=False):
        raise AssertionError(f"{label}: maximum difference {np.max(np.abs(np.asarray(actual)-expected))}")


def fee(quantity, notional, side, profile):
    # Independently reconstruct the frozen scenario, not the production fee helper.
    friction = notional * (40 / 20000)
    if profile == "proportional":
        return friction
    assert profile == "moomoo_ca_us"
    amount, shares = Decimal(str(notional)), Decimal(quantity)
    rate = Decimal("0.0005") if amount < shares else Decimal("0.0049")
    platform = Decimal("0.0005") if amount < shares else Decimal("0.005")
    cent = Decimal("0.01")
    explicit = max(Decimal("0.99"), shares * rate).quantize(cent, rounding=ROUND_CEILING)
    explicit += max(Decimal("1"), shares * platform).quantize(cent, rounding=ROUND_CEILING)
    if side == "sell":
        explicit += max(cent, amount * Decimal("0.0000206")).quantize(cent, rounding=ROUND_CEILING)
    return float(explicit) + friction


def audit_account(account, market, forecast, boundaries):
    curve, trades = account["equity_curve"], account["trade_records"]
    dates = {d: i for i, d in enumerate(market["sessions"])}
    symbols = {s: i for i, s in enumerate(market["symbols"])}
    first, last = dates[curve[0]["session"]], dates[curve[-1]["session"]]
    assert [r["session"] for r in curve] == market["sessions"][first:last + 1]
    n = len(curve)
    cash_delta, marked, unsettled = np.zeros(n), np.zeros(n), np.zeros(n)
    held_count = np.zeros(n, dtype=int)
    aggregate_net = aggregate_fees = 0.0
    learned = account["policy"] != "static_setup_rank"
    head = {1: 0, 3: 1, 5: 2}[account["horizon"]]
    lots = defaultdict(list)
    crossed = {b: {"held_trades": 0, "pending_entries": 0} for b in boundaries}
    forecast_pairs = []
    for trade in trades:
        s, e, x = (dates[trade[k]] for k in ("signal_session", "entry_session", "exit_session"))
        j, q = symbols[trade["symbol"]], trade["quantity"]
        assert isinstance(q, int) and not isinstance(q, bool) and q > 0
        assert e == s + 1 and x == e + account["horizon"] and trade["holding_sessions"] == account["horizon"]
        assert int((market["dates"][x] - market["dates"][e]).astype(int)) == trade["holding_calendar_days"]
        assert trade["settlement_index"] == int(market["settlement_index"][x])
        entry = q * float(market["close"][e, j])
        exit_notional = entry * float(market["adjusted"][x, j]) / float(market["adjusted"][e, j])
        close(trade["entry_notional"], entry, "source entry notional")
        close(trade["exit_notional"], exit_notional, "source adjusted exit notional")
        buy_fee = fee(q, entry, "buy", account["cost_profile"])
        sell_fee = fee(q, trade["exit_notional"], "sell", account["cost_profile"])
        close(trade["entry_fee"], buy_fee, "buy fee")
        close(trade["exit_fee"], sell_fee, "sell fee")
        net = exit_notional - entry - buy_fee - sell_fee
        close(trade["net_pnl"], net, "net trade dollars")
        close(trade["net_return"], net / entry, "net trade return")
        aggregate_net += trade["net_pnl"]
        aggregate_fees += buy_fee + sell_fee
        cash_delta[e - first] -= entry + buy_fee
        proceeds = exit_notional - sell_fee
        cash_delta[x - first] += proceeds
        settlement = min(n, int(market["settlement_index"][x]) - first)
        if proceeds > 0:
            unsettled[x-first:settlement] += proceeds
        marks = entry * np.asarray(market["adjusted"][e:x, j]) / float(market["adjusted"][e, j])
        assert np.isfinite(marks).all() and (marks > 0).all()
        marked[e-first:x-first] += marks
        held_count[e-first:x-first] += 1
        lots[j].append((e, x))
        for boundary, counts in crossed.items():
            counts["held_trades"] += int(e < boundary <= x)
            counts["pending_entries"] += int(s < boundary <= e)
        if learned:
            conditional = trade["conditional"]
            reference, fill = conditional["reference_projection"], conditional["fill_projection"]
            expected = np.asarray(forecast[s, j, [head, head + 3]])
            assert np.array_equal([reference["mu"], reference["downside"]], expected)
            assert np.array_equal([fill["mu"], fill["downside"]], expected)
            assert q <= reference["quantity"] and fill["quantity"] == q
            for projection, date in ((reference, s), (fill, e)):
                close(projection["price"], market["close"][date, j], "projection source quote")
                notional = projection["quantity"] * projection["price"]
                close(projection["notional"], notional, "projection notional")
                exit_value = notional * (1 + projection["mu"])
                close(projection["projected_exit_notional"], exit_value, "projected exit")
                f_in = fee(projection["quantity"], notional, "buy", account["cost_profile"])
                f_out = fee(projection["quantity"], exit_value, "sell", account["cost_profile"])
                close(projection["entry_fee"], f_in, "projected buy fee")
                close(projection["exit_fee"], f_out, "projected sell fee")
                utility = notional * projection["mu"] - f_in - f_out - .5 * notional * projection["downside"]
                close(projection["utility"], utility, "entry utility")
                assert utility > 0
            forecast_pairs.append([s, j, head])
    for values in lots.values():
        values.sort()
        assert all(right[0] >= left[1] for left, right in zip(values, values[1:]))
    cash = 2000 + np.cumsum(cash_delta)
    nav = cash + marked
    settled = cash - unsettled
    for key, expected in (("cash", cash), ("equity", nav), ("unsettled_cash", unsettled), ("settled_cash", settled)):
        close([r[key] for r in curve], expected, "source-derived daily " + key)
        assert min(r[key] for r in curve) >= -1e-7
    assert held_count.max() <= 5
    close(nav[-1], cash[-1], "final account flat")
    close(account["ending_equity"], 2000 + aggregate_net, "flat NAV equals capital plus net dollars")
    close(aggregate_fees, account["fees"], "total fee ledger")
    assert len(trades) == account["trades"] == account["trade_metrics"]["completed_trades"]
    source_dd = float(np.max(1 - nav / np.maximum.accumulate(np.r_[2000, nav])[1:]))
    close(account["max_drawdown"], source_dd, "source-derived drawdown")
    return {
        "status": "passed", "policy": account["policy"], "horizon": account["horizon"],
        "cost_profile": account["cost_profile"], "trades": len(trades), "net_pnl": aggregate_net,
        "ending_equity": account["ending_equity"], "total_return": account["total_return"],
        "max_drawdown": account["max_drawdown"], "fees": aggregate_fees,
        "minimum_settled_cash": float(settled.min()), "maximum_positions": int(held_count.max()),
        "model_boundary_attribution": [
            {"session": market["sessions"][boundary], **counts} for boundary, counts in crossed.items()
        ],
        "exact_frozen_forecast_trade_checks": len(forecast_pairs),
        "forecast_row_subset_sha256": hashlib.sha256(json.dumps(forecast_pairs).encode()).hexdigest(),
    }


def main():
    # Snapshot only committed manifests. Never read a live status file or an unpublished account.
    paths = sorted((ROOT / "account-manifests").glob("*.json"))
    snapshot = [(path, path.read_bytes()) for path in paths]
    definition_path = ROOT / "definition.json"
    definition = read(definition_path)
    definition_sha = sha(definition_path)
    for name, expected in definition["files"].items():
        assert sha(REPO / name) == expected, name
    cache = ROOT / "preparation/market-features.joblib"
    assert sha(cache) == definition["preparation_cache_sha256"]
    forecast_manifest = read(ROOT / "forecast-manifest.json")
    forecast_path = ROOT / "corrected-forecasts.npy"
    assert sha(forecast_path) == forecast_manifest["sha256"]
    assert forecast_manifest["definition_sha256"] == definition_sha
    market, _ = joblib.load(cache, mmap_mode="r")
    forecast = np.load(forecast_path, mmap_mode="r")
    preflight = read(ROOT / "preparation/coverage-preflight.json")
    boundaries = [b["test_start"] for b in preflight["blocks"]][1:]
    records = []
    for path, raw_manifest in snapshot:
        manifest = json.loads(raw_manifest)
        account_path = ROOT / "accounts" / path.name
        raw = account_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["sha256"], path.name
        account = json.loads(raw)
        assert account["definition_sha256"] == manifest["definition_sha256"] == definition_sha
        assert account["forecast_identity"] == manifest["forecast_identity"] == forecast_manifest["sha256"]
        assert account["status"] == manifest["status"]
        if account["status"] == "complete":
            try:
                result = audit_account(account, market, forecast, boundaries)
            except Exception as error:
                result = {"status": "audit_failed", "error": f"{type(error).__name__}: {error}"}
        else:
            result = {"status": "retained_incomplete_account", "account_status": account["status"]}
        records.append({
            "account_path": account_path.relative_to(REPO).as_posix(),
            "account_sha256": manifest["sha256"],
            "manifest_path": path.relative_to(REPO).as_posix(),
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(), **result,
        })
    now = datetime.now(timezone.utc)
    result = {
        "reviewed_at": now.isoformat(), "snapshot_accounts": len(records), "planned_accounts": 18,
        "definition_sha256": definition_sha, "script_sha256": sha(Path(__file__)),
        "preparation_cache_sha256": definition["preparation_cache_sha256"],
        "forecast_identity": forecast_manifest["sha256"], "records": records,
        "qualification": [
            "Independent accounting reconstruction from committed trade records and verified preparation-cache prices.",
            "Fees independently reconstructed using Decimal component rounding; these are declared scenarios, not actual fills.",
            "All recorded learned trade forecasts checked exactly against the frozen signal-date forecast map.",
            "Source consistency is not action completeness, delisting coverage, point-in-time history or proof of profitability.",
            "Annual boundary attribution describes preserved positions/pending entries, not an account restart.",
            "No model fit, engine replay, source correction, broker operation or live status-file read.",
        ],
    }
    output = ROOT / ("independent-account-audit-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "accounts": len(records),
                      "audit_failures": sum(r["status"] == "audit_failed" for r in records),
                      "trades": sum(r.get("trades", 0) for r in records),
                      "records": [{k: r.get(k) for k in ("policy","horizon","cost_profile","status","ending_equity","max_drawdown","exact_frozen_forecast_trade_checks","error")} for r in records]}), flush=True)


if __name__ == "__main__":
    main()


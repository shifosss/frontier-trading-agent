"""Independent recorded-ledger audit; never calls strategy selection or simulation."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from functools import lru_cache
import hashlib
import importlib.util
import json
from math import floor, isclose, log
from pathlib import Path
from statistics import mean, median

from frontier.historical_settlement import build_settlement_indices

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
CAPTURE = ROOT.with_name("intraday-opening20260928")
STOCKS = ("AAPL", "MSFT", "F", "T", "HRL", "BANF")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def near(actual, expected, label):
    assert isclose(float(actual), float(expected), abs_tol=2e-6, rel_tol=2e-10), f"{label}: {actual} != {expected}"


def fee(quantity, notional, profile, side):
    friction = notional * .002
    if profile == "proportional":
        return friction
    assert profile == "moomoo_ca_us"
    q, n, cent = Decimal(quantity), Decimal(str(notional)), Decimal(".01")
    rate = Decimal(".0005") if n < q else Decimal(".0049")
    platform = Decimal(".0005") if n < q else Decimal(".005")
    value = max(Decimal(".99"), q*rate).quantize(cent, rounding=ROUND_CEILING)
    value += max(Decimal("1"), q*platform).quantize(cent, rounding=ROUND_CEILING)
    if side == "sell":
        value += max(cent, n*Decimal(".0000206")).quantize(cent, rounding=ROUND_CEILING)
    return float(value)+friction


def opening(bars, symbol):
    rows = bars.get(symbol, {})
    if any(i not in rows for i in range(60)):
        return None
    values = [rows[i] for i in range(60)]
    return {"open": float(values[0]["o"]), "close": float(values[-1]["c"]),
            "high": max(float(v["h"]) for v in values), "low": min(float(v["l"]) for v in values),
            "activity": sum(float(v["c"])*float(v["v"]) for v in values)}


class FrozenSources:
    """Reuse reviewed canonicalization; validate raw/audit identities on every loaded day."""
    def __init__(self, adapter, manifest, inputs):
        self.adapter, self.manifest, self.inputs = adapter, manifest, inputs
        self.sessions = manifest["sessions"]
        self.features = {}
        self.reviewed = set()

    @lru_cache(maxsize=24)
    def bars(self, index):
        session = self.sessions[index]
        values, audit = self.adapter.read_session(self.manifest["root"], session, self.manifest)
        assert audit["transport_complete"] and not audit["source_errors"]
        assert digest(audit) == self.inputs["audit_sha256"][session["session"]]
        self.reviewed.add(session["session"])
        for symbol in (*STOCKS, "SPY"):
            self.features[index, symbol] = opening(values, symbol)
        return values

    def hour(self, index, symbol):
        if (index, symbol) not in self.features:
            self.bars(index)
        return self.features[index, symbol]


def causal_features(source, index, symbol):
    current, spy = source.hour(index, symbol), source.hour(index, "SPY")
    assert current is not None and spy is not None and index >= 20
    past = [source.hour(i, symbol) for i in range(index-20, index)]
    assert all(value is not None for value in past)
    activity_median = median(value["activity"] for value in past)
    assert current["activity"] > activity_median
    span = current["high"]-current["low"]
    assert span > 0
    relative = log(current["close"]/current["open"])-log(spy["close"]/spy["open"])
    return {"reference_price": current["close"], "opening_range": span,
            "relative_return": relative, "location": (current["close"]-current["low"])/span,
            "activity": current["activity"], "prior_activity_median": activity_median}


def check_periods(report, initial):
    for frequency, label in (("weekly", lambda d: f"{d.isocalendar().year}-W{d.isocalendar().week:02}"),
                             ("monthly", lambda d: d.strftime("%Y-%m")), ("yearly", lambda d: str(d.year))):
        groups = {}
        for row in report["daily_equity"]:
            groups[label(datetime.fromisoformat(row["session"]))] = row
        assert len(groups) == len(report[frequency])
        before = initial
        for (period, row), saved in zip(groups.items(), report[frequency], strict=True):
            assert saved["period"] == period and saved["last_session"] == row["session"]
            near(saved["starting_equity"], before, frequency+" start")
            near(saved["ending_equity"], row["equity"], frequency+" end")
            near(saved["return_"], row["equity"]/before-1, frequency+" return")
            before = row["equity"]



def check_references(report, source, dates):
    matched_date_means = []
    eligible_total = matched_total = missing_entry_total = missing_exit_total = 0
    for reference in report["event_reference"]:
        index = dates[reference["session"]]
        bars = source.bars(index)
        symbols = reference["eligible_symbols"]
        assert len(symbols) == len(set(symbols)) and set(symbols) <= set(STOCKS)
        for symbol in symbols:
            causal_features(source, index, symbol)
        missing_entry = [symbol for symbol in symbols if 76 not in bars.get(symbol, {})]
        missing_exit = [symbol for symbol in symbols if 196 not in bars.get(symbol, {})]
        expected = {symbol: float(bars[symbol][196]["o"])/float(bars[symbol][76]["o"])-1
                    for symbol in symbols if symbol not in missing_entry and symbol not in missing_exit}
        assert reference["missing_entry"] == missing_entry and reference["missing_exit"] == missing_exit
        assert [row["symbol"] for row in reference["matched_events"]] == list(expected)
        for row in reference["matched_events"]:
            near(row["gross_return"], expected[row["symbol"]], "unfunded event return")
        assert reference["paired_events"] == len(expected)
        if expected:
            average = mean(expected.values()); matched_date_means.append(average)
            near(reference["equal_stock_mean_return"], average, "unfunded daily reference")
        else:
            assert reference["equal_stock_mean_return"] is None
        eligible_total += len(symbols); matched_total += len(expected)
        missing_entry_total += len(missing_entry); missing_exit_total += len(missing_exit)
    summary = report["event_reference_summary"]
    for key, value in (("eligible_events", eligible_total), ("matched_events", matched_total),
                       ("missing_entry", missing_entry_total), ("missing_exit", missing_exit_total),
                       ("observed_dates", len(report["event_reference"])), ("matched_dates", len(matched_date_means))):
        assert summary[key] == value
    if matched_date_means:
        near(summary["equal_date_gross_return"], mean(matched_date_means), "equal-date reference aggregation")
    else:
        assert summary["equal_date_gross_return"] is None


def audit_account(report, source, settlement_indices):
    if report["status"] == "failed":
        return {"audit_status": "retained_exception_without_ledger", "account_status": "failed", "error": report.get("error")}
    assert report["status"] in ("complete", "invalid")
    sessions = source.sessions
    dates = {s["session"]: i for i, s in enumerate(sessions)}
    initial, profile = report["initial_cash"], report["cost_profile"]
    assert initial == 2000 and profile in ("proportional", "moomoo_ca_us")
    grouped = {}
    for key in ("orders", "fills", "trades", "daily_equity", "event_reference"):
        values = defaultdict(list)
        for row in report[key]:
            values[row["session"]].append(row)
        grouped[key] = values
    points = defaultdict(list)
    for point in report["intraday_equity"]:
        points[datetime.fromisoformat(point["timestamp"]).date().isoformat()].append(point)
    assert list(points) == sorted(points)
    cash, receivables, positions = initial, [], {}
    peak, drawdown, exposure, seconds = initial, 0., 0., 0.
    stale_total, maximum_age, checked_marks = 0, 0., 0
    minimum_settled, completed_net, completed_fees = initial, 0., 0.
    for day, curve in points.items():
        index, session = dates[day], sessions[dates[day]]
        start, end = datetime.fromisoformat(session["open"]), datetime.fromisoformat(session["close"])
        assert not positions, "No overnight position may survive a valid previous session"
        cash += sum(amount for ready, amount in receivables if ready <= index)
        receivables = [(ready, amount) for ready, amount in receivables if ready > index]
        nav = cash+sum(amount for _, amount in receivables)
        orders, fills, trades = (grouped[k][day] for k in ("orders", "fills", "trades"))
        assert len(orders) <= 5 and len({o["symbol"] for o in orders}) == len(orders)
        assert [(-abs(o["relative_return"]), o["symbol"]) for o in orders] == sorted((-abs(o["relative_return"]), o["symbol"]) for o in orders)
        available = cash
        for order in orders:
            assert order["symbol"] in STOCKS
            features = causal_features(source, index, order["symbol"])
            for key, expected in features.items():
                assert isclose(float(order[key]), float(expected), abs_tol=1e-12, rel_tol=2e-10), "causal "+key
            r, location = features["relative_return"], features["location"]
            assert (r > 0 and location >= .75) if report["arm"] == "continuation" else (r < 0 and location <= .25)
            for key, minute in (("signal_time", 60), ("decision_time", 75), ("entry_time", 76)):
                assert datetime.fromisoformat(order[key]) == start+timedelta(minutes=minute)
            q, price = order["planned_quantity"], order["reference_price"]
            assert type(q) is int and 0 < q <= floor(.005*nav/features["opening_range"])
            budget = min(.2*nav, available)
            reserved = q*price+fee(q, q*price, profile, "buy")
            near(order["reserved_cash"], reserved, "reservation")
            assert reserved <= budget+1e-8
            if q+1 <= floor(.005*nav/features["opening_range"]):
                assert (q+1)*price+fee(q+1, (q+1)*price, profile, "buy") > budget-1e-8
            available -= reserved
        bars = source.bars(index)
        planned = {o["symbol"]: o for o in orders}
        assert [f["symbol"] for f in fills] == [o["symbol"] for o in orders[:len(fills)]]
        buy_cash, positive = cash, []
        for fill in fills:
            q, symbol = fill["quantity"], fill["symbol"]
            order = planned[symbol]
            assert type(q) is int and 0 <= q <= order["planned_quantity"]
            price = float(bars[symbol][76]["o"])
            near(fill["entry_price"], price, "raw entry open")
            near(fill["signal_to_entry_return"], price/order["reference_price"]-1, "execution gap")
            assert fill["cancelled_for_affordability"] == (q == 0)
            budget = min(buy_cash, order["reserved_cash"])
            spend = q*price+fee(q, q*price, profile, "buy") if q else 0.
            assert spend <= budget+1e-8
            if q < order["planned_quantity"]:
                assert (q+1)*price+fee(q+1, (q+1)*price, profile, "buy") > budget-1e-8
            buy_cash -= spend
            if q:
                positive.append(fill)
        entry_cursor = exit_cursor = 0
        previous = None
        observed_minutes = []
        for point in curve:
            time, phase = datetime.fromisoformat(point["timestamp"]), point["phase"]
            assert start <= time <= end
            if previous is not None:
                assert time >= previous[0]
                exposure += (time-previous[0]).total_seconds()*previous[1]
            if phase == "session_open":
                assert point is curve[0] and time == start
            elif phase == "entry_open":
                assert time == start+timedelta(minutes=76) and not positions
            elif phase == "entry_fill":
                assert time == start+timedelta(minutes=76)
                fill = positive[entry_cursor]; entry_cursor += 1
                symbol, q, price = fill["symbol"], fill["quantity"], fill["entry_price"]
                charge = fee(q, q*price, profile, "buy")
                cash -= q*price+charge
                positions[symbol] = {"quantity": q, "entry_price": price, "entry_notional": q*price,
                                     "entry_fee": charge, "mark": price, "mark_time": time}
            elif phase == "minute_close":
                offset = int((time-start).total_seconds()/60)-1
                assert time == start+timedelta(minutes=offset+1) and 76 <= offset < 196
                touched = False
                for symbol, position in positions.items():
                    if offset in bars.get(symbol, {}):
                        position.update(mark=float(bars[symbol][offset]["c"]), mark_time=time)
                        touched = True
                assert touched
                observed_minutes.append(offset)
            elif phase == "exit_open":
                assert time == start+timedelta(minutes=196)
                for symbol, position in positions.items():
                    position.update(mark=float(bars[symbol][196]["o"]), mark_time=time)
            elif phase == "exit_fill":
                assert time == start+timedelta(minutes=196)
                trade = trades[exit_cursor]; exit_cursor += 1
                position = positions.pop(trade["symbol"])
                q, price = position["quantity"], float(bars[trade["symbol"]][196]["o"])
                assert trade["quantity"] == q and type(q) is int
                assert datetime.fromisoformat(trade["entry_time"]) == start+timedelta(minutes=76)
                assert datetime.fromisoformat(trade["exit_time"]) == time and time < end
                sale = q*price; charge = fee(q, sale, profile, "sell")
                for key, expected in (("entry_price", position["entry_price"]), ("exit_price", price),
                                      ("entry_notional", position["entry_notional"]), ("exit_notional", sale),
                                      ("entry_fee", position["entry_fee"]), ("exit_fee", charge)):
                    near(trade[key], expected, key)
                net = sale-position["entry_notional"]-position["entry_fee"]-charge
                near(trade["net_pnl"], net, "trade net dollars")
                near(trade["gross_return"], sale/position["entry_notional"]-1, "trade gross return")
                assert trade["settlement_index"] == int(settlement_indices[index])
                cash -= max(0., charge-sale)
                receivables.append((int(settlement_indices[index]), max(0., sale-charge)))
                completed_net += net; completed_fees += position["entry_fee"]+charge
            elif phase == "session_close":
                assert time == end and not positions
                assert len(grouped["daily_equity"][day]) == 1
                for key in ("equity", "cash", "settled_cash", "unsettled_cash"):
                    near(grouped["daily_equity"][day][0][key], point[key], "daily "+key)
                seconds += session["minutes"]*60
            else:
                raise AssertionError("Unknown saved mark phase: "+phase)
            value = sum(p["quantity"]*p["mark"] for p in positions.values())
            unsettled = sum(amount for _, amount in receivables)
            equity = cash+unsettled+value
            for key, expected in (("equity", equity), ("cash", cash+unsettled), ("settled_cash", cash),
                                  ("unsettled_cash", unsettled), ("positions_value", value)):
                near(point[key], expected, "source-derived mark "+key)
            assert cash >= -1e-8 and len(positions) <= 5
            minimum_settled = min(minimum_settled, cash)
            ages = [(time-p["mark_time"]).total_seconds() for p in positions.values()]
            assert all(age >= 0 for age in ages)
            assert point["stale_positions"] == sum(age > 0 for age in ages)
            near(point["max_mark_age_seconds"], max(ages, default=0), "mark age")
            stale_total += point["stale_positions"]; maximum_age = max(maximum_age, max(ages, default=0))
            peak = max(peak, equity); drawdown = max(drawdown, 1-equity/peak)
            previous = time, value/equity if equity else 0.
            checked_marks += 1
        assert entry_cursor == len(positive) and exit_cursor == len(trades)
        entry_failure = report.get("failure") and report["failure"].get("session") == day and report["failure"]["reason"] == "missing_required_entry"
        expected_minutes = [] if entry_failure else sorted({m for f in positive for m in bars[f["symbol"]] if 76 <= m < 196})
        assert observed_minutes == expected_minutes, "Every observed held-minute boundary must be marked"
    assert report["completed_trades"] == len(report["trades"])
    near(report["fees_completed_trades"], completed_fees, "completed fees")
    near(report["partial_sampled_mark_max_drawdown"], drawdown, "sampled mark drawdown")
    assert report["stale_mark_observations"] == stale_total
    near(report["max_mark_age_seconds"], maximum_age, "maximum sampled mark age")
    ending = cash+sum(v for _, v in receivables)+sum(p["quantity"]*p["mark"] for p in positions.values())
    near(report["partial_marked_equity"], ending, "partial/complete NAV")
    assert len(report["remaining_receivables"]) == len(receivables)
    for saved, (ready, amount) in zip(report["remaining_receivables"], receivables, strict=True):
        assert saved["settlement_index"] == ready
        near(saved["amount"], amount, "remaining receivable")
    assert {p["symbol"] for p in report["open_positions"]} == set(positions)
    for saved in report["open_positions"]:
        for key, expected in positions[saved["symbol"]].items():
            if key == "mark_time":
                assert datetime.fromisoformat(saved[key]) == expected
            else:
                near(saved[key], expected, "unresolved position "+key)
    check_periods(report, initial)
    check_references(report, source, dates)
    valid = report["status"] == "complete"
    if valid:
        assert not positions
        assert list(points) == [row["session"] for row in report["daily_equity"]]
        assert list(points) == [row["session"] for row in report["event_reference"]]
        near(ending, initial+completed_net, "flat NAV from net PnL")
        near(report["ending_equity"], ending, "ending NAV")
        near(report["total_return"], ending/initial-1, "total return")
        near(report["sampled_mark_max_drawdown"], drawdown, "sampled drawdown")
        near(report["time_weighted_session_exposure"], exposure/seconds, "session exposure")
        if report["trades"]:
            near(report["net_expectancy_usd"], completed_net/len(report["trades"]), "net expectancy")
        else:
            assert report["net_expectancy_usd"] is None
    else:
        assert all(report[key] is None for key in ("ending_equity", "total_return", "sampled_mark_max_drawdown", "net_expectancy_usd", "time_weighted_session_exposure"))
        failure = report["failure"]
        index = dates[failure["session"]]; bars = source.bars(index)
        if failure["reason"] == "missing_required_entry":
            assert 76 not in bars.get(failure["symbol"], {})
        elif failure["reason"] == "missing_required_exit":
            assert set(failure["symbols"]) == {s for s in positions if 196 not in bars.get(s, {})}
        elif failure["reason"] == "exit_fee_cash_shortfall":
            p = positions[failure["symbol"]]
            assert fee(p["quantity"], p["quantity"]*p["mark"], profile, "sell")-p["quantity"]*p["mark"] > cash
        else:
            assert failure["reason"] == "required_timing_outside_session"
    stock_net = defaultdict(float)
    for trade in report["trades"]:
        stock_net[trade["symbol"]] += trade["net_pnl"]
    return {"audit_status": "passed_complete_ledger" if valid else "passed_invalid_prefix", "account_status": report["status"],
            "completed_trades": len(report["trades"]), "checked_orders": len(report["orders"]), "checked_marks": checked_marks,
            "recorded_net_pnl": completed_net, "economic_metrics_valid": valid,
            "ending_equity": ending if valid else None, "sampled_mark_max_drawdown": drawdown if valid else None,
            "fees_completed_trades": completed_fees, "minimum_settled_cash": minimum_settled,
            "sampled_exposure_fraction": exposure/seconds if seconds and valid else None,
            "stock_net_pnl": dict(stock_net),
            "active_years": sorted({t["session"][:4] for t in report["trades"]}),
            "positive_week_count": sum(p["return_"] > 0 for p in report["weekly"]) if valid else None,
            "positive_month_count": sum(p["return_"] > 0 for p in report["monthly"]) if valid else None,
            "positive_year_count": sum(p["return_"] > 0 for p in report["yearly"]) if valid else None,
            "positive_trade_dollars": sum(max(t["net_pnl"], 0) for t in report["trades"]),
            "negative_trade_dollars": sum(min(t["net_pnl"], 0) for t in report["trades"]),
            "top_five_positive_trade_dollars": sum(sorted((max(t["net_pnl"], 0) for t in report["trades"]), reverse=True)[:5]),
            "failure": report.get("failure")}


def main():
    if not (ROOT / "completed.json").exists():
        raise SystemExit("No completed intraday study manifest; audit did not run.")
    definition, request = read(ROOT / "definition.json"), read(ROOT / "request.json")
    definition_sha = sha(ROOT / "definition.json")
    assert sha(ROOT / "request.json") == definition["request_sha256"]
    for path, expected in definition["files"].items():
        assert sha(REPO / path) == expected, path
    completed = read(ROOT / "completed.json")
    assert completed["definition_sha256"] == definition_sha
    for path, expected in completed["files"].items():
        assert sha(ROOT / path) == expected, path
    summary_path = ROOT / completed["summary"]
    summary = read(summary_path); attempt = summary_path.parent
    assert summary["planned_accounts"] == 4 and len(summary["accounts"]) == 4
    assert {(a["arm"], a["cost_profile"]) for a in summary["accounts"]} == {(arm, cost) for arm in request["arms"] for cost in request["cost_profiles"]}
    inputs = read(attempt / "source-inputs.json")
    assert inputs["qualified"] and not inputs["failures"]
    assert summary["source_inputs_sha256"] == sha(attempt / "source-inputs.json")
    spec = importlib.util.spec_from_file_location("frozen_intraday_source_adapter", ROOT / "source_adapter.py")
    adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    manifest = adapter.load_manifest(CAPTURE, definition["source_request_sha256"])
    assert manifest["sessions"] == inputs["sessions"] and manifest["identities"] == inputs["source_identities"]
    source = FrozenSources(adapter, manifest, inputs)
    settlement = build_settlement_indices([s["session"] for s in manifest["sessions"]], "USD")
    records = []
    for item in summary["accounts"]:
        path = attempt / item["artifact"]
        assert sha(path) == item["sha256"]
        report = read(path)
        assert report["definition_sha256"] == definition_sha and report["source_inputs_sha256"] == summary["source_inputs_sha256"]
        print(json.dumps({"independent_account": path.name, "phase": "recorded_ledger_audit"}), flush=True)
        try:
            if report["status"] == "complete":
                expected_days = [s["session"] for s in manifest["sessions"] if request["first_signal"] <= s["session"] <= request["last_session"]]
                assert [row["session"] for row in report["daily_equity"]] == expected_days
                assert [row["session"] for row in report["event_reference"]] == expected_days
            result = audit_account(report, source, settlement)
        except Exception as error:
            result = {"audit_status": "audit_failed", "account_status": report["status"], "error": f"{type(error).__name__}: {error}"}
        records.append({"account": path.name, "account_sha256": sha(path), "arm": item["arm"], "cost_profile": item["cost_profile"], **result})
    assert sha(ROOT / "definition.json") == definition_sha
    for path, expected in definition["files"].items():
        assert sha(REPO / path) == expected, path
    now = datetime.now(timezone.utc)
    result = {"reviewed_at": now.isoformat(), "definition_sha256": definition_sha,
              "summary_sha256": sha(summary_path), "source_inputs_sha256": sha(attempt / "source-inputs.json"),
              "script_sha256": sha(Path(__file__)), "planned_accounts": 4, "accounts": records,
              "source_sessions_rechecked": len(source.reviewed),
              "limitations": ["Audits recorded selections, not a second policy or candidate-selection run.",
                              "Canonical source adapter and frozen historical settlement calendar are reused; cash/fee/valuation arithmetic is independent.",
                              "Invalid prefixes and exceptions remain in the four-path denominator; they are not qualified economic outcomes.",
                              "Observed minute marks, raw-price conventions, source revisions and six-survivor sampling do not prove executable fills or generalizable profitability."]}
    output = ROOT / ("independent-intraday-audit-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "accounts": len(records), "audit_failures": sum(r["audit_status"] == "audit_failed" for r in records)}), flush=True)


if __name__ == "__main__":
    main()

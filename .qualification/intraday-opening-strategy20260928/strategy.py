"""Four declared delayed-opening cash paths; pure historical inputs only."""
from collections import deque
from datetime import datetime, timedelta
from math import floor, isfinite, log
from statistics import mean, median

from frontier.execution_costs import get_cost_profile
from frontier.historical_settlement import SETTLEMENT_ASSUMPTION, build_settlement_indices


STOCKS = ("AAPL", "MSFT", "F", "T", "HRL", "BANF")
ENTRY_MINUTE, EXIT_MINUTE = 76, 196


def opening_features(daily_bars):
    """The adapter supplies validated unique bars; absent offsets stay absent."""
    result = {}
    for symbol in (*STOCKS, "SPY"):
        bars = daily_bars.get(symbol, {})
        if any(i not in bars for i in range(60)):
            result[symbol] = None
            continue
        rows = [bars[i] for i in range(60)]
        o, c = float(rows[0]["o"]), float(rows[-1]["c"])
        h, low = max(float(b["h"]) for b in rows), min(float(b["l"]) for b in rows)
        result[symbol] = {"open": o, "close": c, "high": h, "low": low,
                          "range": h-low, "activity": sum(float(b["c"])*float(b["v"]) for b in rows),
                          "relative_return": None, "location": (c-low)/(h-low) if h > low else None}
    benchmark = result["SPY"]
    if benchmark:
        benchmark_return = log(benchmark["close"]/benchmark["open"])
        for symbol in STOCKS:
            if result[symbol]:
                result[symbol]["relative_return"] = log(result[symbol]["close"]/result[symbol]["open"]) - benchmark_return
    return result


def eligible_events(features, previous_activity):
    result = []
    for symbol in STOCKS:
        value, previous = features[symbol], previous_activity[symbol]
        if value is None or value["relative_return"] is None or value["range"] <= 0:
            continue
        if len(previous) != 20 or any(x is None for x in previous):
            continue
        if value["activity"] > median(previous):
            result.append({"symbol": symbol, **value, "prior_activity_median": median(previous)})
    return result


def select_signals(features, previous_activity, arm):
    if arm not in ("continuation", "reversal"):
        raise ValueError("Unknown declared opening arm")
    events = eligible_events(features, previous_activity)
    selected = [event for event in events if (
        event["relative_return"] > 0 and event["location"] >= 0.75 if arm == "continuation" else
        event["relative_return"] < 0 and event["location"] <= 0.25
    )]
    return sorted(selected, key=lambda event: (-abs(event["relative_return"]), event["symbol"]))


def _reference(day, events, bars):
    values, missing_entry, missing_exit = [], [], []
    for event in events:
        symbol = event["symbol"]
        rows = bars.get(symbol, {})
        if ENTRY_MINUTE not in rows:
            missing_entry.append(symbol)
        if EXIT_MINUTE not in rows:
            missing_exit.append(symbol)
        if ENTRY_MINUTE in rows and EXIT_MINUTE in rows:
            values.append({"symbol": symbol, "gross_return": float(rows[EXIT_MINUTE]["o"])/float(rows[ENTRY_MINUTE]["o"])-1})
    return {"session": day, "eligible_symbols": [x["symbol"] for x in events], "matched_events": values,
            "missing_entry": missing_entry, "missing_exit": missing_exit, "paired_events": len(values),
            "equal_stock_mean_return": mean(x["gross_return"] for x in values) if values else None}


def _period_returns(curve, initial_cash, frequency):
    result, previous_equity = [], initial_cash
    for row in curve:
        day = datetime.fromisoformat(row["session"])
        year, week, _ = day.isocalendar()
        period = (f"{year}-W{week:02}" if frequency == "weekly" else
                  day.strftime("%Y-%m") if frequency == "monthly" else str(day.year))
        if not result or result[-1]["period"] != period:
            result.append({"period": period, "starting_equity": previous_equity})
        result[-1].update(last_session=row["session"], ending_equity=row["equity"],
                          return_=row["equity"]/result[-1]["starting_equity"]-1)
        previous_equity = row["equity"]
    return result


def simulate(sessions, daily_bars, *, arm, cost_profile, initial_cash=2000,
             first_signal="2017-01-03", last_session="2025-12-31"):
    """Simulate one continuous cash account over canonical minute-bar dictionaries.

    No market data or endpoint is accessed here. Source validation/provenance is
    owned by the isolated adapter. Only the six predeclared stocks can trade.
    """
    if arm not in ("continuation", "reversal") or cost_profile not in ("proportional", "moomoo_ca_us"):
        raise ValueError("Account is outside the four declared paths")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Initial cash must be positive and finite")
    costs = get_cost_profile(cost_profile, 40)
    settlements = build_settlement_indices([s["session"] for s in sessions], "USD")
    history = {s: deque(maxlen=20) for s in STOCKS}
    settled, receivables, positions = float(initial_cash), [], []
    orders, fills, trades, curve, daily, references, activity = [], [], [], [], [], [], []
    peak, drawdown, total_exposure_seconds, total_session_seconds = initial_cash, 0.0, 0.0, 0.0
    stale_observations, maximum_age, failure = 0, 0.0, None
    previous_mark = None

    def mark(time, phase):
        nonlocal peak, drawdown, stale_observations, maximum_age, previous_mark, total_exposure_seconds
        unsettled = sum(amount for _, amount in receivables)
        value = sum(p["quantity"]*p["mark"] for p in positions)
        equity = settled + unsettled + value
        ages = [(time-p["mark_time"]).total_seconds() for p in positions]
        stale = sum(age > 0 for age in ages)
        maximum_age = max(maximum_age, max(ages, default=0))
        stale_observations += stale
        if previous_mark is not None:
            total_exposure_seconds += (time-previous_mark[0]).total_seconds()*previous_mark[1]
        previous_mark = time, value/equity if equity > 0 else 0
        peak = max(peak, equity)
        drawdown = max(drawdown, 1-equity/peak)
        point = {"timestamp": time.isoformat(), "phase": phase, "equity": equity,
                 "settled_cash": settled, "unsettled_cash": unsettled, "cash": settled+unsettled,
                 "positions_value": value, "stale_positions": stale, "max_mark_age_seconds": max(ages, default=0)}
        curve.append(point)
        return point

    for index, (session, bars) in enumerate(zip(sessions, daily_bars, strict=True)):
        day = session["session"]
        if day > last_session:
            break
        features = opening_features(bars)
        events = eligible_events(features, history)
        selected = select_signals(features, history, arm)
        for symbol in STOCKS:
            history[symbol].append(features[symbol]["activity"] if features[symbol] else None)
        if day < first_signal:
            continue
        opening, closing = datetime.fromisoformat(session["open"]), datetime.fromisoformat(session["close"])
        entry_time, exit_time = (opening+timedelta(minutes=i) for i in (ENTRY_MINUTE, EXIT_MINUTE))
        if exit_time >= closing:
            failure = {"session": day, "reason": "required_timing_outside_session"}
            break
        settled += sum(amount for ready, amount in receivables if ready <= index)
        receivables = [(ready, amount) for ready, amount in receivables if ready > index]
        previous_mark = None
        initial = mark(opening, "session_open")
        nav, available, planned = initial["equity"], settled, []
        for candidate in selected:
            if len(planned) == 5:
                break
            quantity_limit = floor(0.005*nav/candidate["range"])
            quantity = costs.maximum_quantity(quantity_limit, candidate["close"], min(0.2*nav, available))
            if not quantity:
                continue
            reserved = quantity*candidate["close"] + costs.fee(quantity, quantity*candidate["close"], "buy")
            order = {"session": day, "symbol": candidate["symbol"], "signal_time": (opening+timedelta(minutes=60)).isoformat(),
                     "decision_time": (opening+timedelta(minutes=75)).isoformat(), "entry_time": entry_time.isoformat(),
                     "planned_quantity": quantity, "reserved_cash": reserved, "reference_price": candidate["close"],
                     "opening_range": candidate["range"], "relative_return": candidate["relative_return"],
                     "location": candidate["location"], "activity": candidate["activity"],
                     "prior_activity_median": candidate["prior_activity_median"]}
            planned.append(order)
            orders.append(order)
            available -= reserved
        activity.append({"session": day, "eligible_events": len(events), "signals": len(selected), "planned_orders": len(planned)})
        mark(entry_time, "entry_open")
        for order in planned:
            symbol = order["symbol"]
            if ENTRY_MINUTE not in bars.get(symbol, {}):
                failure = {"session": day, "timestamp": entry_time.isoformat(), "symbol": symbol, "reason": "missing_required_entry"}
                break
            price = float(bars[symbol][ENTRY_MINUTE]["o"])
            quantity = costs.maximum_quantity(order["planned_quantity"], price, min(settled, order["reserved_cash"]))
            fills.append({"session": day, "symbol": symbol, "quantity": quantity, "entry_price": price,
                          "signal_to_entry_return": price/order["reference_price"]-1,
                          "cancelled_for_affordability": quantity == 0})
            if not quantity:
                continue
            notional = quantity*price
            fee = costs.fee(quantity, notional, "buy")
            settled -= notional+fee
            positions.append({"symbol": symbol, "quantity": quantity, "entry_price": price,
                              "entry_notional": notional, "entry_fee": fee, "mark": price, "mark_time": entry_time})
            mark(entry_time, "entry_fill")
        if failure:
            references.append(_reference(day, events, bars))
            break
        # ponytail: six names and a two-hour hold need a simple minute loop, not an event framework.
        for minute in range(ENTRY_MINUTE, EXIT_MINUTE):
            boundary = opening+timedelta(minutes=minute+1)
            observed = False
            for position in positions:
                row = bars.get(position["symbol"], {}).get(minute)
                if row is not None:
                    position.update(mark=float(row["c"]), mark_time=boundary)
                    observed = True
            if observed:
                mark(boundary, "minute_close")
        missing = [p["symbol"] for p in positions if EXIT_MINUTE not in bars.get(p["symbol"], {})]
        if missing:
            failure = {"session": day, "timestamp": exit_time.isoformat(), "symbols": missing, "reason": "missing_required_exit"}
            references.append(_reference(day, events, bars))
            break
        for position in positions:
            position.update(mark=float(bars[position["symbol"]][EXIT_MINUTE]["o"]), mark_time=exit_time)
        mark(exit_time, "exit_open")
        for position in list(positions):
            sale = position["quantity"]*position["mark"]
            fee = costs.fee(position["quantity"], sale, "sell")
            cash_shortfall = max(0.0, fee-sale)
            if cash_shortfall > settled:
                failure = {"session": day, "timestamp": exit_time.isoformat(), "symbol": position["symbol"], "reason": "exit_fee_cash_shortfall"}
                break
            settled -= cash_shortfall
            receivables.append((int(settlements[index]), max(0.0, sale-fee)))
            trades.append({"session": day, "symbol": position["symbol"], "quantity": position["quantity"],
                           "entry_time": entry_time.isoformat(), "exit_time": exit_time.isoformat(),
                           "entry_price": position["entry_price"], "exit_price": position["mark"],
                           "entry_notional": position["entry_notional"], "exit_notional": sale,
                           "entry_fee": position["entry_fee"], "exit_fee": fee,
                           "gross_return": sale/position["entry_notional"]-1,
                           "net_pnl": sale-position["entry_notional"]-position["entry_fee"]-fee,
                           "settlement_index": int(settlements[index])})
            positions.remove(position)
            mark(exit_time, "exit_fill")
        references.append(_reference(day, events, bars))
        if failure:
            break
        ending = mark(closing, "session_close")
        daily.append({"session": day, **{k: ending[k] for k in ("equity", "cash", "settled_cash", "unsettled_cash")}})
        total_session_seconds += session["minutes"]*60
        if settled < -1e-8 or abs(ending["equity"]-(initial_cash+sum(t["net_pnl"] for t in trades))) > 1e-6:
            raise ArithmeticError("Intraday cash ledger did not reconcile")

    valid = failure is None
    ending_equity = settled + sum(amount for _, amount in receivables) + sum(p["quantity"]*p["mark"] for p in positions)
    matched_dates = [r["equal_stock_mean_return"] for r in references if r["equal_stock_mean_return"] is not None]
    fees = sum(t["entry_fee"]+t["exit_fee"] for t in trades)
    result = {"status": "complete" if valid else "invalid", "failure": failure, "arm": arm,
              "cost_profile": cost_profile, "cost_specification": costs.specification,
              "price_convention": "Raw same-session minute opens: entry quantity * 10:46 open and exit quantity * 12:46 open; no synthetic adjusted exit notional",
              "fill_convention": "Observed reference-price simulation with quantity-only affordability reduction; not guaranteed executable fills; inherited daily action caveat in shared cost metadata does not describe this price convention",
              "settlement_assumption": SETTLEMENT_ASSUMPTION, "initial_cash": initial_cash,
              "ending_equity": ending_equity if valid else None, "partial_marked_equity": ending_equity,
              "total_return": ending_equity/initial_cash-1 if valid else None,
              "sampled_mark_max_drawdown": drawdown if valid else None, "partial_sampled_mark_max_drawdown": drawdown,
              "completed_trades": len(trades), "fees_completed_trades": fees,
              "net_expectancy_usd": mean(t["net_pnl"] for t in trades) if trades and valid else None,
              "time_weighted_session_exposure": total_exposure_seconds/total_session_seconds if total_session_seconds and valid else None,
              "stale_mark_observations": stale_observations, "max_mark_age_seconds": maximum_age,
              "orders": orders, "fills": fills, "trades": trades, "intraday_equity": curve, "daily_equity": daily,
              "activity": activity, "event_reference": references,
              "event_reference_summary": {"eligible_events": sum(len(r["eligible_symbols"]) for r in references),
                                          "matched_events": sum(r["paired_events"] for r in references),
                                          "missing_entry": sum(len(r["missing_entry"]) for r in references),
                                          "missing_exit": sum(len(r["missing_exit"]) for r in references),
                                          "observed_dates": len(references), "matched_dates": len(matched_dates),
                                          "equal_date_gross_return": mean(matched_dates) if matched_dates else None},
              "weekly": _period_returns(daily, initial_cash, "weekly"),
              "monthly": _period_returns(daily, initial_cash, "monthly"),
              "yearly": _period_returns(daily, initial_cash, "yearly"),
              "open_positions": [{k: v.isoformat() if isinstance(v, datetime) else v for k, v in p.items()} for p in positions],
              "remaining_receivables": [{"settlement_index": ready, "amount": amount} for ready, amount in receivables]}
    return result

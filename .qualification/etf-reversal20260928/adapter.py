"""Short ETF accounts using the existing cash engine, fixed reservations and a halt."""
from collections import Counter

import numpy as np
from frontier.execution_costs import get_cost_profile
from frontier.short_horizon_study import _simulate_daily, _statistics, _summarize


def run_account(market, ranking, counts, *, arm, cost_profile, cost_bps, capital,
                first, last, halt_drawdown=.3):
    costs = get_cost_profile(cost_profile, cost_bps)
    # Account-local halt state must never alter the next account's frozen signals.
    active_counts = np.array(counts, copy=True)
    state, halt, peak = None, None, float(capital)
    intents, intent_map, daily_state = [], {}, []
    total = {key: np.full(last-first+1, np.nan)
             for key in ("equity", "cash", "settled_cash", "unsettled_cash")}
    total.update(status="complete", missing=[], fees=0., trades=0, trade_records=[],
                 audit_retained=True, tallies=_statistics(), traded_notional=0., net_pnl_total=0.)
    activity = Counter()
    for i in range(first, last+1):
        if state:
            for order in state["pending"]:
                intent = intent_map[(order["signal"], order["symbol_index"])]
                price = market["close"][i, order["symbol_index"]]
                if np.isfinite(price) and price > 0:
                    order["quantity"] = costs.maximum_quantity(
                        order["quantity"], float(price), intent["reserved_cash"])
                    intent["reservation_capped_quantity"] = int(order["quantity"])
                # Invalid fill prices must reach the engine's incomplete-account path.
        chunk = _simulate_daily(
            market, arm, 3, capital, cost_bps, i, last, state=state, audit=True,
            signal_ranking=ranking, signal_counts=active_counts, cost_model=costs,
            process_through=i)
        state = chunk["state"]
        for key in ("equity", "cash", "settled_cash", "unsettled_cash"):
            total[key][i-first] = chunk[key][0]
        for key in ("fees", "trades", "traded_notional", "net_pnl_total"):
            total[key] += chunk[key]
        for key in ("pnl", "returns", "holds", "days"):
            total["tallies"][key].extend(chunk["tallies"][key])
        for symbol, pnl in chunk["tallies"]["symbols"].items():
            total["tallies"]["symbols"][symbol] += pnl
        activity.update(chunk["activity"])
        for trade in chunk["trade_records"]:
            key = (market["sessions"].index(trade["signal_session"]),
                   market["symbols"].index(trade["symbol"]))
            intent = intent_map[key]
            trade.update(original_quantity=intent["original_quantity"],
                         reserved_cash=intent["reserved_cash"],
                         signal_available_at=intent["signal_available_at"],
                         original_exit_session=intent["original_exit_session"],
                         exit_advanced_by_halt=trade["exit_session"] != intent["original_exit_session"])
            assert trade["quantity"] <= intent["original_quantity"]
            assert trade["entry_notional"]+trade["entry_fee"] <= intent["reserved_cash"]+1e-7
            total["trade_records"].append(trade)
            intent.update(status="closed", exit_session=trade["exit_session"])
        for position in state["held"]:
            intent_map[(position["signal"], position["symbol_index"])].update(
                status="filled", filled_quantity=int(position["quantity"]))
        if chunk["status"] != "complete":
            total.update(status=chunk["status"], missing=chunk["missing"])
            break
        for order in state["pending"]:
            j, quantity = order["symbol_index"], int(order["quantity"])
            price = float(market["close"][i, j])
            intent = {"signal_session": market["sessions"][i], "symbol": market["symbols"][j],
                      "signal_available_at": market["signal_available_at"][i],
                      "planned_entry_session": market["sessions"][i+1],
                      "original_exit_session": market["sessions"][i+4],
                      "original_quantity": quantity, "reference_price": price,
                      "reserved_cash": quantity*price+costs.fee(quantity, quantity*price, "buy"),
                      "status": "planned"}
            intents.append(intent)
            intent_map[(i, j)] = intent
        nav = float(chunk["equity"][0])
        peak = max(peak, nav)
        drawdown = 1-nav/peak
        if halt is None and drawdown >= halt_drawdown:
            canceled = []
            for order in state["pending"]:
                intent = intent_map[(order["signal"], order["symbol_index"])]
                intent["status"] = "canceled_drawdown_halt"
                canceled.append({"signal_session": intent["signal_session"], "symbol": intent["symbol"]})
            state["pending"] = []  # Reservations were not cash debits; no refund is due.
            active_counts[i+1:] = 0
            advanced = []
            for position in state["held"]:
                previous = position["exit"]
                position["exit"] = min(previous, i+1)
                advanced.append({"symbol": market["symbols"][position["symbol_index"]],
                                 "previous_exit_index": previous, "new_exit_index": position["exit"]})
            halt = {"session": market["sessions"][i], "nav": nav, "peak": peak,
                    "observed_drawdown": drawdown, "canceled_intents": canceled,
                    "exit_instructions": advanced,
                    "timing": "Observed after close fills/marks; liquidate at next session close, with gap risk"}
        daily_state.append({"session": market["sessions"][i], "peak": peak, "drawdown": drawdown,
                            "halted": halt is not None, "held": [dict(p) for p in state["held"]],
                            "pending": [dict(p) for p in state["pending"]],
                            "receivables": [[int(due), float(amount)] for due, amount in state["receivables"]]})
    total.update(activity=dict(activity), state=state)
    result = _summarize(total, market["sessions"][first:last+1], capital)
    result.update(arm=arm, capital=capital, cost_profile=cost_profile, costs=costs.specification,
                  holding_sessions=3, intents=intents, daily_state=daily_state, final_state=state,
                  drawdown_halt=halt, maximum_acceptable_drawdown=halt_drawdown,
                  reservation_rule="Original fee-inclusive reservation; quantity can only decrease",
                  adjustment_convention="Existing adjusted-notional marks, not action-complete broker shares")
    for intent in intents:
        if intent["status"] == "planned" and result["status"] == "complete":
            intent["status"] = "no_fill"
    return result

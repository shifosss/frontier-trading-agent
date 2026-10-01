"""Morning filing decisions over the existing streaming daily cash ledger."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
from frontier.execution_costs import get_cost_profile
from frontier.short_horizon_study import _simulate_daily, _statistics, _summarize


def event_rankings(market, events, arm):
    if arm not in {"income_surprise", "filing_control"}:
        raise ValueError("Unknown predeclared event arm")
    symbols, sessions = market["symbols"], market["sessions"]
    ranking = np.zeros((len(sessions), len(symbols)), dtype=np.int32)
    counts = np.zeros(len(sessions), dtype=np.int32)
    by_row, lookup = {}, {}
    for event in events:
        if not "2017-01-01" <= event["filing_date"] <= "2025-12-31":
            continue
        if event["feature_status"] != "qualified" or event["execution_status"] != "qualified":
            continue
        score = Decimal(event["S"])
        assert score.is_finite() and event["selected"] == (score >= 1)
        if arm == "income_surprise" and not event["selected"]:
            continue
        decision = datetime.fromisoformat(event["decision_time"])
        floor = datetime.fromisoformat(event["availability_floor"])
        assert decision.tzinfo is not None and floor.tzinfo is not None and decision >= floor
        decision = decision.astimezone(ZoneInfo("America/New_York"))
        assert decision.hour == 9 and decision.minute == 0 and decision.second == 0
        entry = sessions.index(event["entry_session"])
        assert entry > 0 and sessions[entry+5] == event["exit_session"]
        assert decision.date().isoformat() == event["entry_session"]
        j = symbols.index(event["symbol"])
        row = entry-1
        key = (row, j)
        if key in lookup:
            raise ValueError("Multiple qualified events for one issuer at one decision need explicit resolution")
        lookup[key] = event
        by_row.setdefault(row, []).append((score, event["symbol"], j))
    for row, candidates in by_row.items():
        candidates.sort(key=(lambda x: (-x[0], x[1])) if arm == "income_surprise" else (lambda x: x[1]))
        ranking[row, :len(candidates)] = [c[2] for c in candidates]
        counts[row] = len(candidates)
    return ranking, counts, lookup


def run_account(market, events, *, arm, cost_profile, first, last, capital=2000, cost_bps=40):
    ranking, counts, lookup = event_rankings(market, events, arm)
    costs = get_cost_profile(cost_profile, cost_bps)
    state, intents, intent_map, daily_state = None, [], {}, []
    total = {k: np.full(last-first+1, np.nan) for k in ["equity", "cash", "settled_cash", "unsettled_cash"]}
    total.update(status="complete", missing=[], fees=0., trades=0, trade_records=[], audit_retained=True,
                 tallies=_statistics(), traded_notional=0., net_pnl_total=0., activity={})
    activity = Counter()
    for i in range(first, last+1):
        if state:
            # This occurs at the simulated fill, after the immutable morning decision.
            for order in state["pending"]:
                intent = intent_map[(order["signal"], order["symbol_index"])]
                price = market["close"][i, order["symbol_index"]]
                intent["fill_reference_price"] = float(price) if np.isfinite(price) else None
                if np.isfinite(price) and price > 0:
                    order["quantity"] = costs.maximum_quantity(order["quantity"], price, intent["reserved_cash"])
                    intent["reservation_capped_quantity"] = int(order["quantity"])
                # Missing/invalid prices deliberately reach the engine's failure path.
        chunk = _simulate_daily(market, arm, 5, capital, cost_bps, i, last, state=state,
                                audit=True, signal_ranking=ranking, signal_counts=counts,
                                cost_model=costs, process_through=i)
        state = chunk["state"]
        for key in ["equity", "cash", "settled_cash", "unsettled_cash"]:
            total[key][i-first] = chunk[key][0]
        for key in ["fees", "trades", "traded_notional", "net_pnl_total"]:
            total[key] += chunk[key]
        for key in ["pnl", "returns", "holds", "days"]:
            total["tallies"][key].extend(chunk["tallies"][key])
        for symbol, pnl in chunk["tallies"]["symbols"].items():
            total["tallies"]["symbols"][symbol] += pnl
        activity.update(chunk["activity"])
        for trade in chunk["trade_records"]:
            row = market["sessions"].index(trade.pop("signal_session"))
            j = market["symbols"].index(trade["symbol"])
            intent = intent_map[(row, j)]
            trade.update(prior_price_session=market["sessions"][row], decision_time=intent["decision_time"],
                         availability_floor=intent["availability_floor"], accession=intent["accession"],
                         original_quantity=intent["original_quantity"], reserved_cash=intent["reserved_cash"])
            assert trade["entry_notional"]+trade["entry_fee"] <= intent["reserved_cash"]+1e-7
            assert trade["quantity"] <= intent["original_quantity"]
            total["trade_records"].append(trade)
        daily_state.append({"session": market["sessions"][i], "held_positions": len(state["held"]),
                            "pending_orders": len(state["pending"]),
                            "receivables": [{"due_index": int(due), "amount": float(amount)} for due, amount in state["receivables"]]})
        for position in state["held"]:
            intent_map[(position["signal"], position["symbol_index"])]["filled_quantity"] = int(position["quantity"])
        if chunk["status"] != "complete":
            total["status"], total["missing"] = chunk["status"], chunk["missing"]
            break
        for order in state["pending"]:
            j = order["symbol_index"]
            event = lookup[(i, j)]
            quantity, price = int(order["quantity"]), float(market["close"][i, j])
            notional = quantity * price
            intent = {"accession": event["accession"], "symbol": event["symbol"],
                      "decision_time": event["decision_time"], "availability_floor": event["availability_floor"],
                      "prior_price_session": market["sessions"][i], "entry_session": event["entry_session"],
                      "exit_session": event["exit_session"], "S": event["S"], "original_quantity": quantity,
                      "reference_price": price, "reserved_cash": notional+costs.fee(quantity, notional, "buy")}
            intents.append(intent)
            intent_map[(i, j)] = intent
    total["activity"] = dict(activity)
    total["state"] = state
    result = _summarize(total, market["sessions"][first:last+1], capital)
    result.update(arm=arm, cost_profile=cost_profile, starting_capital=capital, holding_sessions=5,
                  intents=intents, daily_state=daily_state, final_state=state,
                  decision_clock="09:00ET using preceding completed session price inputs",
                  reservation_rule="Original fee-inclusive reservation; fill quantity can only decrease",
                  adjustment_convention="Existing adjusted-notional daily marks and exits; corporate-action completeness unqualified")
    return result

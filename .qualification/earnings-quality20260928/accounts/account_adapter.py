"""Frozen earnings-event recipes over the shared continuous cash ledger."""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import numpy as np

from frontier.conditional_policy import ConditionalPolicy
from frontier.execution_costs import get_cost_profile
from frontier.short_horizon_study import _simulate_daily, _statistics, _summarize

SPECIFICATION_SHA256 = "7e837043e034305fe3aa15aefd3d28d8389f63e923fc7ef0739d1883e8a30ffb"
RECIPES = ("filing_control", "income_surprise", "income_cash_confirmation",
           "ridge", "hist_gradient_boosting")
COST_PROFILES = {"proportional_40bps": "proportional",
                 "moomoo_ca_us_plus_40bps": "moomoo_ca_us"}
LEARNED = frozenset(RECIPES[3:])
NEW_YORK = ZoneInfo("America/New_York")


def _identity(event):
    identity = {key: deepcopy(event[key]) for key in
                ("event_id", "cik", "symbol", "accession", "filing_date", "acceptance_time",
                 "registry_acceptance_utc", "acceptance_et", "source_input", "source_sha256",
                 "industry_header_source", "decision_timestamp", "decision_time",
                 "availability_floor", "entry_session", "exit_session",
                 "planned_label_end_session", "S", "Q") if key in event}
    identity["prepared_event_sha256"] = sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return identity


def _decision(event):
    value = event.get("decision_timestamp") or event.get("decision_time")
    if not value:
        return None
    decision = datetime.fromisoformat(value)
    if decision.tzinfo is None:
        raise ValueError("Decision timestamp needs an explicit timezone")
    return decision.astimezone(NEW_YORK)


def _forecast_values(record):
    if record is None:
        return None, "missing_forecast"
    if record.get("status") != "predicted":
        return None, record.get("reason") or record.get("status") or "unavailable_forecast"
    values = record.get("corrected")
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return None, "invalid_forecast"
    try:
        mu, downside = map(float, values)
    except (TypeError, ValueError):
        return None, "invalid_forecast"
    if not all(map(isfinite, (mu, downside))) or mu <= -1 or downside < 0:
        return None, "invalid_forecast"
    return (mu, downside), None


def event_rankings(market, events, recipe, forecasts=None):
    """Retain all event dispositions; future prices never determine eligibility."""
    if recipe not in RECIPES:
        raise ValueError("Unknown predeclared earnings recipe")
    sessions, symbols = market["sessions"], market["symbols"]
    session_index = {value: i for i, value in enumerate(sessions)}
    symbol_index = {value: j for j, value in enumerate(symbols)}
    ranking = np.zeros((len(sessions), len(symbols)), dtype=np.int32)
    counts = np.zeros(len(sessions), dtype=np.int32)
    lookup, by_row, dispositions, seen_ids, shared_keys = {}, {}, [], set(), set()
    forecast_rows = forecasts if forecasts is not None else {}
    for event in events:
        identity = event["event_id"]
        if identity in seen_ids:
            raise ValueError("Duplicate original event identity")
        seen_ids.add(identity)
        disposition = dict(_identity(event), status="unavailable", reasons=[])
        dispositions.append(disposition)
        decision = _decision(event)
        if decision is None:
            disposition["reasons"] = ["missing_decision_timestamp", *event.get("model_input_reasons", [])]
            continue
        if not 2021 <= decision.year <= 2025:
            disposition.update(status="outside_entry_period", reasons=["decision_outside_2021_2025"])
            continue
        if event["model_input_status"] != "qualified":
            disposition["reasons"] = deepcopy(event.get("model_input_reasons", ["unqualified_model_inputs"]))
            continue
        if not all(event.get(key) == "qualified" for key in
                   ("feature_status", "joint_feature_status", "strategy_source_status", "execution_status")):
            raise ValueError("Qualified model inputs contradict preserved source qualification")
        inputs = event["model_inputs"]
        if len(inputs) != 5 or not all(isfinite(float(value)) for value in inputs):
            raise ValueError("Qualified model inputs need five finite values")
        score, cash_backing = Decimal(str(event["S"])), Decimal(str(event["Q"]))
        if not score.is_finite() or not cash_backing.is_finite():
            raise ValueError("Qualified financial values must remain finite")
        if float(score) != float(inputs[0]) or float(cash_backing) != float(inputs[1]):
            raise ValueError("Model input order differs from original S/Q")
        floor = datetime.fromisoformat(event["availability_floor"])
        if floor.tzinfo is None or decision < floor:
            raise ValueError("Decision precedes public availability")
        if (decision.hour, decision.minute, decision.second, decision.microsecond) != (9, 0, 0, 0):
            raise ValueError("Decision must be 09:00 New York")
        if event.get("decision_time") and datetime.fromisoformat(event["decision_time"]) != decision:
            raise ValueError("Preserved and prepared decision clocks disagree")
        entry = session_index[event["entry_session"]]
        row, j = entry - 1, symbol_index[event["symbol"]]
        label_end = entry + 5
        if (row < 0 or label_end >= len(sessions)
                or event["prior_price_index"] != row or event["entry_index"] != entry
                or event["planned_label_end_index"] != label_end
                or event["planned_label_end_session"] != sessions[label_end]
                or event.get("exit_session", sessions[label_end]) != sessions[label_end]
                or decision.date().isoformat() != sessions[entry]):
            raise ValueError("Prepared event indices or five-session clock disagree")
        key = row, j
        if key in shared_keys:
            raise ValueError("Unresolved same-issuer decision collision; preserve both original events")
        shared_keys.add(key)
        selected = recipe == "filing_control" or recipe in LEARNED or (
            score >= 1 and (recipe == "income_surprise" or cash_backing > 0))
        if not selected:
            disposition.update(status="rule_abstention", reasons=["declared_financial_rule"])
            continue
        if recipe in LEARNED:
            record = forecast_rows.get(identity)
            if record is not None and (
                    record.get("event_id") != identity or record.get("cik") != event["cik"]
                    or record.get("prepared_row_sha256") != disposition["prepared_event_sha256"]):
                raise ValueError("Forecast identity or prepared source row differs from the event")
            disposition["forecast"] = deepcopy(record)
            _, reason = _forecast_values(record)
            if reason:
                reasons = record.get("reasons") if record and record.get("status") != "predicted" else None
                disposition.update(status="forecast_abstention", reasons=deepcopy(reasons) or [reason])
                continue
        disposition.update(status="candidate", reasons=[])
        lookup[key] = event
        by_row.setdefault(row, []).append((score, event["symbol"], event["accession"], j))
    for row, candidates in by_row.items():
        if recipe in ("income_surprise", "income_cash_confirmation"):
            candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
        else:
            candidates.sort(key=lambda value: (value[1], value[2]))
        ranking[row, :len(candidates)] = [value[3] for value in candidates]
        counts[row] = len(candidates)
    return ranking, counts, lookup, dispositions


class _AuditedPolicy:
    """Collect full existing planner decisions without changing selection semantics."""
    def __init__(self, policy, lookup):
        self.policy, self.lookup, self.records = policy, lookup, []

    @property
    def specification(self):
        return self.policy.specification

    def plan_entries(self, **kwargs):
        kwargs["audit"] = True
        result = self.policy.plan_entries(**kwargs)
        row = kwargs["signal_index"]
        decisions = []
        for decision in result["decisions"]:
            event = self.lookup[(row, decision["symbol_index"])]
            decisions.append(dict(decision, event_id=event["event_id"], accession=event["accession"]))
        self.records.append({
            "phase": "full_selection", "prior_price_index": row,
            "nav": kwargs["nav"], "available_cash": kwargs["available_cash"],
            "held_symbols": list(kwargs["held_symbols"]), "slots": kwargs["slots"],
            "orders": [dict(order, event_id=self.lookup[(row, order["symbol_index"])]["event_id"],
                            accession=self.lookup[(row, order["symbol_index"])]["accession"])
                       for order in deepcopy(result["orders"])], "decisions": decisions,
            "remaining_cash": result["remaining_cash"],
            "rejection_counts": deepcopy(result["rejection_counts"]),
        })
        return result

    def check_fill(self, *args, **kwargs):
        return self.policy.check_fill(*args, **kwargs)


def _weekly_report(result):
    weeks = result.get("period_returns", {}).get("weekly", [])
    roles_by_week = {}
    for point in result.get("equity_curve", []):
        day = point["session"]
        year, week, _ = datetime.fromisoformat(day).isocalendar()
        role = ("initialization" if day < "2021-01-01" else
                "liquidation_tail" if day > "2025-12-31" else "entry_period")
        roles_by_week.setdefault(f"{year}-W{week:02}", set()).add(role)
    for row in weeks:
        roles = sorted(roles_by_week[row["period"]])
        row["interval_roles"] = roles
        row["interval_role"] = roles[0] if len(roles) == 1 else "mixed"
    if result["status"] != "complete":
        return {"status": "unavailable_for_incomplete_account", "count": None}
    values = [row["return"] for row in weeks]
    streak = longest = 0
    for value in values:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    return {
        "status": "complete", "count": len(values),
        "targets": {str(target): {"hits": sum(value >= target for value in values),
                                  "denominator": len(values),
                                  "fraction": sum(value >= target for value in values) / len(values)}
                    for target in (0.05, 0.10, 0.15)} if values else {},
        "median_return": float(np.median(values)) if values else None,
        "worst_return": min(values) if values else None,
        "longest_losing_streak": longest,
        "all_idle_and_losing_weeks_retained": True,
    }


def run_account(market, events, *, recipe, cost_profile, capital=10000,
                forecasts=None, forecast_identity=None, first=None, last=None):
    """Replay one frozen recipe; explicit first/last are labelled synthetic-test overrides."""
    definition = Path(__file__).resolve().parent.parent / "cohort/model-specification.json"
    if sha256(definition.read_bytes()).hexdigest() != SPECIFICATION_SHA256:
        raise ValueError("Frozen earnings specification changed")
    if capital not in (2000, 10000) or cost_profile not in COST_PROFILES:
        raise ValueError("Account balance/cost is outside the frozen comparison")
    if (first is None) != (last is None):
        raise ValueError("Test interval needs both bounds")
    test_interval = first is not None
    if not test_interval:
        first_entry = next(i for i, day in enumerate(market["sessions"]) if day >= "2021-01-01")
        first, last = first_entry - 1, market["sessions"].index("2026-01-16")
        if first < 0 or market["sessions"][first_entry][:4] != "2021":
            raise ValueError("Full entry-period initialization is missing")
    ranking, counts, lookup, dispositions = event_rankings(market, events, recipe, forecasts)
    policy = None
    if recipe in LEARNED:
        if not forecast_identity:
            raise ValueError("Bind one full cross-fold forecast artifact identity")
        policy = _AuditedPolicy(ConditionalPolicy(
            lambda row, j: _forecast_values(forecasts[lookup[(row, j)]["event_id"]])[0],
            "dollars", forecast_identity), lookup)
    elif forecasts is not None or forecast_identity is not None:
        raise ValueError("Control recipes do not consume learned forecasts")
    costs = get_cost_profile(COST_PROFILES[cost_profile], 40)
    state, intents, intent_map, daily_state = None, [], {}, []
    total = {key: np.full(last - first + 1, np.nan)
             for key in ("equity", "cash", "settled_cash", "unsettled_cash")}
    total.update(status="complete", missing=[], fees=0., trades=0, trade_records=[],
                 audit_retained=True, tallies=_statistics(), traded_notional=0.,
                 net_pnl_total=0., activity={}, policy_audit=[])
    if policy:
        total["conditional_policy"] = policy.specification
    activity = Counter()
    for i in range(first, last + 1):
        if state:
            for order in state["pending"]:
                intent = intent_map[(order["signal"], order["symbol_index"])]
                price = float(market["close"][i, order["symbol_index"]])
                intent["fill_reference_price"] = price if isfinite(price) else None
                if isfinite(price) and price > 0:
                    order["quantity"] = costs.maximum_quantity(
                        order["quantity"], price, intent["reserved_cash"])
                    intent["reservation_capped_quantity"] = int(order["quantity"])
                # A missing future price reaches the engine failure path, never an eligibility filter.
        chunk = _simulate_daily(
            market, recipe, 5, capital, 40, i, last, state=state, audit=True,
            signal_ranking=ranking, signal_counts=counts, cost_model=costs,
            process_through=i, entry_policy=policy)
        state = chunk["state"]
        for key in ("equity", "cash", "settled_cash", "unsettled_cash"):
            total[key][i - first] = chunk[key][0]
        for key in ("fees", "trades", "traded_notional", "net_pnl_total"):
            total[key] += chunk[key]
        for key in ("pnl", "returns", "holds", "days"):
            total["tallies"][key].extend(chunk["tallies"][key])
        for symbol, pnl in chunk["tallies"]["symbols"].items():
            total["tallies"]["symbols"][symbol] += pnl
        activity.update(chunk["activity"])
        for row in chunk.get("policy_audit", []):
            audit_row = deepcopy(row)
            if row["phase"] == "fill":
                key = (market["sessions"].index(row["signal_session"]),
                       market["symbols"].index(row["symbol"]))
                intent = intent_map[key]
                audit_row.update(event_id=intent["event_id"], accession=intent["accession"],
                                 reserved_cash=intent["reserved_cash"],
                                 original_quantity=intent["original_quantity"])
                intent["fill_check"] = deepcopy(audit_row)
            total["policy_audit"].append(audit_row)
        for trade in chunk["trade_records"]:
            row = market["sessions"].index(trade["signal_session"])
            j = market["symbols"].index(trade["symbol"])
            intent = intent_map[(row, j)]
            trade.update(_identity(lookup[(row, j)]),
                         prior_price_session=market["sessions"][row],
                         original_quantity=intent["original_quantity"],
                         reserved_cash=intent["reserved_cash"])
            if (trade["entry_notional"] + trade["entry_fee"] > intent["reserved_cash"] + 1e-7
                    or trade["quantity"] > intent["original_quantity"]):
                raise ArithmeticError("Original reservation or quantity was increased")
            total["trade_records"].append(trade)
        for position in state["held"]:
            intent_map[(position["signal"], position["symbol_index"])]["filled_quantity"] = int(position["quantity"])
        daily_state.append({"session": market["sessions"][i], "status": chunk["status"],
                            "held": deepcopy(state["held"]), "pending": deepcopy(state["pending"]),
                            "receivables": [{"due_index": int(due), "amount": float(amount)}
                                            for due, amount in state["receivables"]]})
        if chunk["status"] != "complete":
            total["status"], total["missing"] = chunk["status"], chunk["missing"]
            break
        for order in state["pending"]:
            j = order["symbol_index"]
            event = lookup[(i, j)]
            quantity, price = int(order["quantity"]), float(market["close"][i, j])
            notional = quantity * price
            intent = dict(_identity(event), prior_price_session=market["sessions"][i],
                          original_quantity=quantity, reference_price=price,
                          reserved_cash=notional + costs.fee(quantity, notional, "buy"))
            if policy:
                intent["reference_projection"] = deepcopy(order["projection"])
                intent["forecast"] = deepcopy(forecasts[event["event_id"]])
            intents.append(intent)
            intent_map[(i, j)] = intent
    if policy:
        total["policy_audit"].extend(policy.records)
    total["activity"], total["state"] = dict(activity), state
    result = _summarize(total, market["sessions"][first:last + 1], capital)
    result.update(recipe=recipe, cost_profile=cost_profile, costs=costs.specification,
                  starting_capital=capital, holding_sessions=5, intents=intents,
                  event_decisions=dispositions, daily_state=daily_state, final_state=state,
                  synthetic_interval_override=test_interval,
                  specification_sha256=SPECIFICATION_SHA256,
                  decision_clock="09:00ET using preceding completed session price inputs",
                  reservation_rule="Immutable original fee-inclusive reservation; quantity only decreases",
                  drawdown_interpretation="30% qualification limit; no automatic drawdown halt",
                  adjustment_convention="Adjusted-notional marks; action completeness unqualified")
    result["weekly_objective"] = _weekly_report(result)
    return result

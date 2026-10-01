"""Quantity-aware experimental selection; the existing engine owns cash and fills."""
from collections import Counter
from dataclasses import dataclass
from math import isfinite

from frontier.daily_policy import POLICY, plan_entries


def _projection(forecast, quantity, price, cost_bps, cost_model):
    try:
        mu, downside = (float(value) for value in forecast)
    except (TypeError, ValueError):
        return {"reason": "invalid_forecast"}
    if not all(map(isfinite, (mu, downside))) or mu <= -1 or downside < 0:
        return {"reason": "invalid_forecast"}
    if quantity <= 0:
        return {"reason": "zero_quantity"}
    notional = quantity * price
    sale = notional * (1 + mu)
    if not all(map(isfinite, (notional, sale))) or min(notional, sale) <= 0:
        return {"reason": "invalid_forecast"}
    half_cost = cost_bps / 20000
    entry_fee = (
        notional * half_cost if cost_model is None else cost_model.fee(quantity, notional, "buy")
    )
    exit_fee = sale * half_cost if cost_model is None else cost_model.fee(quantity, sale, "sell")
    penalty = POLICY["predicted_downside_penalty"] * notional * downside
    utility = notional * mu - entry_fee - exit_fee - penalty
    if not isfinite(utility):
        return {"reason": "invalid_forecast"}
    return {
        "reason": "eligible" if utility > 0 else "nonpositive_utility",
        "quantity": int(quantity),
        "price": float(price),
        "notional": float(notional),
        "mu": mu,
        "downside": downside,
        "projected_exit_notional": float(sale),
        "entry_fee": float(entry_fee),
        "exit_fee": float(exit_fee),
        "utility": float(utility),
        "utility_fraction": float(utility / notional),
    }


@dataclass(frozen=True)
class ConditionalPolicy:
    """forecast_at(signal index, symbol index) returns this horizon's frozen (mu, d)."""

    forecast_at: object
    ranking_mode: str
    forecast_identity: str

    def __post_init__(self):
        if self.ranking_mode not in ("fraction", "dollars"):
            raise ValueError("Conditional ranking must be fraction or dollars")
        if not self.forecast_identity:
            raise ValueError("Frozen forecast identity is required")

    @property
    def specification(self):
        return {
            "version": "conditional-quantity-v1",
            "ranking_mode": self.ranking_mode,
            "forecast_identity": self.forecast_identity,
            "downside_weight": POLICY["predicted_downside_penalty"],
            "fill_convention": "simulated contingent utility recheck; no fill-time reranking",
            "rejection_counts": "candidate/budget evaluations, not distinct rejected stocks",
        }

    def plan_entries(
        self, *, signal_index, symbols, ranking, prices, atrs, nav, available_cash,
        held_symbols=(), reserved_symbols=(), slots=None, cost_bps=40,
        correlation_allowed=None, audit=True, cost_model=None,
    ):
        held, reserved = set(held_symbols), set(reserved_symbols)
        if slots is None:
            slots = max(0, POLICY["maximum_positions"] - len(held | reserved))
        available = float(available_cash)
        candidates, seen, orders, decisions = {}, set(), [], []
        rejects = Counter()
        peers = [j for j, symbol in enumerate(symbols) if symbol in held | reserved]

        def record(j, reason, **details):
            if reason != "eligible":
                rejects[reason] += 1
            if audit or reason == "correlation":
                decisions.append(
                    {"symbol": symbols[j], "symbol_index": j, "reason": reason, **details}
                )

        for raw_index in ranking:
            j = int(raw_index)
            if j != raw_index or not 0 <= j < len(symbols):
                raise ValueError("Ranking contains an invalid symbol index")
            reason = (
                "duplicate" if j in seen
                else "held" if symbols[j] in held
                else "reserved" if symbols[j] in reserved
                else None
            )
            seen.add(j)
            if reason:
                record(j, reason)
            else:
                candidates[j] = self.forecast_at(signal_index, j)

        cached_budget, proposals = None, {}
        while candidates and len(orders) < slots:
            effective_budget = min(available, POLICY["position_budget_fraction"] * nav)
            if effective_budget != cached_budget:
                proposals = {}
                cached_budget = effective_budget
            eligible = []
            for j in sorted(candidates, key=lambda index: symbols[index]):
                if j not in proposals:
                    # Reuse the original sizing contract without its full-universe validation cost.
                    singleton = plan_entries(
                        symbols=[symbols[j]], ranking=[0], prices=[prices[j]], atrs=[atrs[j]],
                        nav=nav, available_cash=effective_budget, slots=1,
                        cost_bps=cost_bps, cost_model=cost_model,
                    )
                    if not singleton["orders"]:
                        reason = singleton["decisions"][0]["reason"]
                        proposals[j] = (None, {"reason": reason})
                        record(j, reason)
                    else:
                        order = {**singleton["orders"][0], "symbol_index": j}
                        projection = _projection(
                            candidates[j], order["quantity"], order["reference_price"],
                            cost_bps, cost_model,
                        )
                        proposals[j] = (order, projection)
                        details = {k: v for k, v in projection.items() if k != "reason"}
                        record(j, projection["reason"], **details)
                order, projection = proposals[j]
                if projection["reason"] != "eligible":
                    continue
                if correlation_allowed is not None and not correlation_allowed(j, peers):
                    record(j, "correlation")
                    continue
                score = projection[
                    "utility_fraction" if self.ranking_mode == "fraction" else "utility"
                ]
                eligible.append((score, symbols[j], j, order, projection))
            if not eligible:
                break
            _, _, j, order, projection = min(eligible, key=lambda row: (-row[0], row[1]))
            order = {**order, "projection": projection}
            orders.append(order)
            available -= order["reserved_cash"]
            peers.append(j)
            del candidates[j]
        return {
            "orders": orders, "decisions": decisions, "remaining_cash": available,
            "rejection_counts": dict(rejects),
        }

    def check_fill(self, order, quantity, price, cost_bps, cost_model):
        """Use the original forecast at the engine's affordable, never-increased quantity."""
        original = order["projection"]
        projection = _projection(
            (original["mu"], original["downside"]), quantity, price, cost_bps, cost_model
        )
        return {
            "accepted": projection["reason"] == "eligible",
            "reason": "filled" if projection["reason"] == "eligible" else projection["reason"],
            "projection": projection,
        }

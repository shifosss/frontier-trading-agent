"""Independent Decimal/cash review with synthetic rows, not an economic backtest."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
sys.path.insert(0, str(STUDY / "accounts"))
import account_adapter as account
from frontier.historical_settlement import build_settlement_indices

CALENDAR = json.loads((STUDY.parent / "post-filing-strategy20260928/calendar.json").read_text())["sessions"]
D = lambda value: Decimal(str(value))


def digest(row):
    return sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fixture(symbols=("AAA", "BBB", "CCC"), start="2024-05-20", end="2024-07-12"):
    sessions = [row["session"] for row in CALENDAR if start <= row["session"] <= end]
    prices = np.array([[25 + .15 * i + 2 * j for j in range(len(symbols))]
                       for i in range(len(sessions))])
    return {"symbols": list(symbols), "sessions": sessions,
            "dates": np.array(sessions, dtype="datetime64[D]"),
            "close": prices, "adjusted": prices.copy(), "atr": np.full_like(prices, .4),
            "settlement_index": build_settlement_indices(sessions, "USD")}


def event(market, j=0, entry=1):
    day = market["sessions"][entry]
    clock = datetime.fromisoformat(day + "T09:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
    identity = f"independent-{market['symbols'][j]}-{day}"
    return {"event_id": identity, "symbol": market["symbols"][j], "cik": str(j + 1).zfill(10),
            "accession": identity, "filing_date": market["sessions"][entry - 1],
            "decision_timestamp": clock.isoformat(), "decision_time": clock.isoformat(),
            "availability_floor": clock.replace(hour=1).isoformat(),
            "entry_session": day, "exit_session": market["sessions"][entry + 5],
            "planned_label_end_session": market["sessions"][entry + 5],
            "entry_index": entry, "prior_price_index": entry - 1, "planned_label_end_index": entry + 5,
            "S": "2", "Q": ".02", "model_inputs": [2., .02, 0., 1., 0.],
            "feature_status": "qualified", "joint_feature_status": "qualified",
            "strategy_source_status": "qualified", "execution_status": "qualified",
            "model_input_status": "qualified"}


def predictions(events, mu=.06, downside=.012):
    return {row["event_id"]: {"event_id": row["event_id"], "cik": row["cik"],
            "prepared_row_sha256": digest(row), "status": "predicted",
            "raw": [mu, downside], "uncalibrated": [mu, downside],
            "corrected": [mu, downside], "reasons": []} for row in events}


def run(market, events, recipe="ridge", profile="proportional_40bps", capital=10000, forecasts=None):
    kwargs = {"forecasts": predictions(events) if forecasts is None else forecasts,
              "forecast_identity": "independent-synthetic-five-fold-identity"} if recipe in account.LEARNED else {}
    return account.run_account(market, events, recipe=recipe, cost_profile=profile, capital=capital,
                               first=0, last=len(market["sessions"]) - 1, **kwargs)


def fee(quantity, notional, side, profile):
    """Declared current-tariff scenario, separately written Decimal arithmetic."""
    value = D(notional) * D(".002")
    if profile == "proportional_40bps" or quantity == 0:
        return value
    quantity = D(quantity)
    low = D(notional) / quantity < 1
    commission = max(D(".99"), quantity * D(".0005" if low else ".0049"))
    platform = max(D("1"), quantity * D(".0005" if low else ".005"))
    value += commission.quantize(D(".01"), rounding=ROUND_CEILING)
    value += platform.quantize(D(".01"), rounding=ROUND_CEILING)
    if side == "sell":
        value += max(D(".01"), D(notional) * D(".0000206")).quantize(D(".01"), rounding=ROUND_CEILING)
    return value


class IndependentAccountReview(unittest.TestCase):
    def assert_decimal_close(self, expected, actual):
        self.assertLessEqual(abs(expected - D(actual)), D(".00000001"))

    def verify_cash(self, m, result, capital, profile):
        self.assertEqual(result["status"], "complete")
        sessions = m["sessions"]
        trades = result["trade_records"]
        self.assertEqual(len(trades), 4)
        checked = []
        for trade in trades:
            entry, exit_ = sessions.index(trade["entry_session"]), sessions.index(trade["exit_session"])
            j = m["symbols"].index(trade["symbol"])
            q = trade["quantity"]
            notional = D(q) * D(m["close"][entry, j])
            proceeds_before_fee = notional * D(m["adjusted"][exit_, j]) / D(m["adjusted"][entry, j])
            buy, sell = fee(q, notional, "buy", profile), fee(q, proceeds_before_fee, "sell", profile)
            for name, expected in (("entry_notional", notional), ("exit_notional", proceeds_before_fee),
                                   ("entry_fee", buy), ("exit_fee", sell),
                                   ("gross_pnl", proceeds_before_fee - notional),
                                   ("net_pnl", proceeds_before_fee - sell - notional - buy)):
                self.assert_decimal_close(expected, trade[name])
            self.assertLessEqual(notional + buy, D(trade["reserved_cash"]) + D("0.00000001"))
            self.assertLessEqual(q, trade["original_quantity"])
            self.assertEqual(exit_ - entry, 5)
            due = exit_ + (1 if sessions[exit_] >= "2024-05-28" else 2)
            self.assertEqual(trade["settlement_index"], due)
            checked.append((entry, exit_, due, j, notional, buy, proceeds_before_fee - sell))
        cash = settled = D(capital)
        for i, actual in enumerate(result["equity_curve"]):
            for entry, exit_, due, j, notional, buy, proceeds in checked:
                if due == i:
                    settled += proceeds
                if exit_ == i:
                    cash += proceeds
                if entry == i:
                    cash -= notional + buy
                    settled -= notional + buy
            held = sum((notional * D(m["adjusted"][i, j]) / D(m["adjusted"][entry, j])
                        for entry, exit_, due, j, notional, buy, proceeds in checked
                        if entry <= i < exit_), D(0))
            unsettled = sum((proceeds for entry, exit_, due, j, notional, buy, proceeds in checked
                            if exit_ <= i < due), D(0))
            for name, expected in (("cash", cash), ("settled_cash", settled),
                                   ("unsettled_cash", unsettled), ("equity", cash + held)):
                self.assert_decimal_close(expected, actual[name])
            self.assertGreaterEqual(settled, 0)
            self.assertLessEqual(len(result["daily_state"][i]["held"]), 5)
        weekly = {}
        for row in result["equity_curve"]:
            year, week, _ = datetime.fromisoformat(row["session"]).isocalendar()
            weekly[f"{year}-W{week:02}"] = D(row["equity"])
        prior = D(capital)
        expected_returns = []
        for week, closing_nav in weekly.items():
            expected_returns.append((week, closing_nav / prior - 1))
            prior = closing_nav
        self.assertEqual(len(expected_returns), result["weekly_objective"]["count"])
        for actual, (week, value) in zip(result["period_returns"]["weekly"], expected_returns, strict=True):
            self.assertEqual(actual["period"], week)
            self.assert_decimal_close(value, actual["return"])
        for threshold, record in result["weekly_objective"]["targets"].items():
            self.assertEqual(record["denominator"], len(expected_returns))
            self.assertEqual(record["hits"], sum(value >= D(threshold) for _, value in expected_returns))

    def test_all_twenty_synthetic_accounts_reconcile_independently(self):
        m = fixture()
        events = [event(m, 0, 1), event(m, 1, 2), event(m, 2, 5), event(m, 0, 12)]
        for recipe in account.RECIPES:
            for capital in (10000, 2000):
                for profile in account.COST_PROFILES:
                    with self.subTest(recipe=recipe, capital=capital, profile=profile):
                        self.verify_cash(m, run(m, events, recipe, profile, capital), capital, profile)

    def test_sixth_candidate_is_not_substituted_after_first_fill_rejection(self):
        m = fixture(tuple("ABCDEF"))
        m["close"][:] = 100
        m["adjusted"][:] = 100
        m["atr"][:] = 1
        events = [event(m, j, 1) for j in range(6)]
        m["close"][1:, 0] = m["adjusted"][1:, 0] = 1000
        result = run(m, events, profile="moomoo_ca_us_plus_40bps",
                     forecasts=predictions(events, mu=.008, downside=0))
        self.assertEqual([row["symbol"] for row in result["intents"]], list("ABCDE"))
        self.assertEqual([row["symbol"] for row in result["trade_records"]], list("BCDE"))
        self.assertEqual(result["intents"][0]["fill_check"]["reason"], "nonpositive_utility")
        self.assertGreater(result["intents"][0]["reference_projection"]["utility"], 0)
        self.assertNotIn("F", [row["symbol"] for row in result["intents"]])

    def test_future_missing_price_does_not_change_causal_candidates(self):
        m = fixture()
        events = [event(m, 0, 1), event(m, 1, 2)]
        forecast = predictions(events)
        before = account.event_rankings(m, events, "ridge", forecast)
        m["close"][1, 0] = np.nan
        after = account.event_rankings(m, events, "ridge", forecast)
        np.testing.assert_array_equal(before[0], after[0])
        np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[3], after[3])
        result = run(m, events, forecasts=forecast)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["total_return"])
        self.assertEqual(len(result["event_decisions"]), 2)
        self.assertTrue(result["intents"])

    def test_nonpositive_utility_retains_all_events_and_stays_in_cash(self):
        m = fixture()
        events = [event(m, 0, 1), event(m, 1, 2)]
        result = run(m, events, forecasts=predictions(events, mu=0, downside=0))
        self.assertEqual(result["trades"], 0)
        self.assertEqual(len(result["event_decisions"]), 2)
        self.assertTrue(all(row["equity"] == 10000 for row in result["equity_curve"]))
        self.assertTrue(any(row.get("rejection_counts", {}).get("nonpositive_utility", 0) > 0
                            for row in result["policy_audit"]))

    def test_forecasts_cannot_cross_original_or_feature_identity(self):
        m = fixture()
        events = [event(m)]
        for key, value in (("event_id", "different-original"), ("cik", "9999999999"),
                           ("prepared_row_sha256", "0" * 64)):
            forecast = predictions(events)
            forecast[events[0]["event_id"]][key] = value
            with self.assertRaises(ValueError):
                run(m, events, forecasts=forecast)

    def test_year_boundary_keeps_existing_hold_despite_new_fold_abstention(self):
        m = fixture(("A", "B"), "2024-12-20", "2025-01-31")
        events = [event(m, 0, m["sessions"].index("2024-12-30")),
                  event(m, 1, m["sessions"].index("2025-01-02"))]
        forecast = predictions(events)
        forecast[events[1]["event_id"]].update(status="unavailable", reasons=["insufficient_calibration"])
        result = run(m, events, forecasts=forecast)
        self.assertEqual(result["trades"], 1)
        self.assertGreater(result["trade_records"][0]["exit_session"], "2025-01-01")
        self.assertEqual(result["event_decisions"][1]["reasons"], ["insufficient_calibration"])
        entry_new = m["sessions"].index("2025-01-02")
        self.assertEqual(len(result["daily_state"][entry_new]["held"]), 1)
        self.assertNotEqual(result["equity_curve"][entry_new]["equity"], 10000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

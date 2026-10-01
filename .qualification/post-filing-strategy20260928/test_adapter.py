"""Economic boundary tests; all prices and filing signals here are synthetic."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import unittest

import numpy as np
from frontier.execution_costs import get_cost_profile
from frontier.historical_settlement import build_settlement_indices
from frontier.short_horizon_study import _simulate_daily
from adapter import event_rankings, run_account

ROOT = Path(__file__).resolve().parent
CALENDAR = json.loads((ROOT / "calendar.json").read_text())["sessions"]


def market(symbols=("A",)):
    sessions = [r["session"] for r in CALENDAR if "2024-06-03" <= r["session"] <= "2024-07-19"]
    shape = (len(sessions), len(symbols))
    return {"symbols": list(symbols), "sessions": sessions, "dates": np.array(sessions, dtype="datetime64[D]"),
            "close": np.full(shape, 100.), "adjusted": np.full(shape, 100.), "atr": np.full(shape, 1.),
            "settlement_index": build_settlement_indices(sessions, "USD")}


def event(m, symbol="A", entry=1, score="2"):
    day = m["sessions"][entry]
    decision = datetime.fromisoformat(day+"T09:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
    return {"symbol": symbol, "accession": f"synthetic-{symbol}-{day}",
            "filing_date": m["sessions"][entry-1], "feature_status": "qualified", "execution_status": "qualified",
            "S": score, "selected": Decimal(score) >= 1,
            "decision_time": decision.isoformat(), "availability_floor": decision.replace(hour=1).isoformat(),
            "entry_session": day, "exit_session": m["sessions"][entry+5]}


def run(m, events, arm="income_surprise", profile="proportional"):
    return run_account(m, events, arm=arm, cost_profile=profile, first=0, last=len(m["sessions"])-1)


class ExecutionTests(unittest.TestCase):
    def test_morning_clock_and_exact_five_session_hold(self):
        m = market(); e = event(m); report = run(m, [e]); trade = report["trade_records"][0]
        self.assertEqual(report["status"], "complete")
        self.assertEqual(trade["entry_session"], m["sessions"][1])
        self.assertEqual(trade["exit_session"], m["sessions"][6])
        self.assertEqual(trade["holding_sessions"], 5)
        self.assertEqual(trade["decision_time"], e["decision_time"])
        self.assertEqual(trade["prior_price_session"], m["sessions"][0])
        self.assertNotIn("signal_session", trade)

    def test_price_rise_cannot_spend_other_order_cash(self):
        m = market(); m["close"][1:] = 125.; m["adjusted"][1:] = 125.
        report = run(m, [event(m)]); intent = report["intents"][0]; trade = report["trade_records"][0]
        self.assertEqual(intent["original_quantity"], 3)
        self.assertAlmostEqual(intent["reserved_cash"], 300.6)
        self.assertEqual(trade["quantity"], 2)
        self.assertAlmostEqual(trade["entry_notional"]+trade["entry_fee"], 250.5)

    def test_favorable_price_does_not_increase_quantity(self):
        m = market(); m["close"][1:] = 50.; m["adjusted"][1:] = 50.
        report = run(m, [event(m)])
        self.assertEqual(report["intents"][0]["original_quantity"], 3)
        self.assertEqual(report["trade_records"][0]["quantity"], 3)

    def test_missing_entry_invalidates_instead_of_abstaining(self):
        m = market(); m["close"][1, 0] = np.nan
        report = run(m, [event(m)])
        self.assertEqual(report["status"], "incomplete")
        self.assertIsNone(report["total_return"])
        self.assertIn(":entry", report["missing"][0])
        self.assertEqual(len(report["intents"]), 1)

    def test_missing_held_mark_retains_unresolved_position(self):
        m = market(); m["adjusted"][4, 0] = np.nan
        report = run(m, [event(m)])
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(report["final_state"]["held"]), 1)
        self.assertEqual(report["intents"][0]["filled_quantity"], 3)
        self.assertEqual(report["trade_records"], [])
        self.assertIsNone(report["ending_equity"])

    def test_information_after_decision_rejected(self):
        m = market(); e = event(m)
        e["availability_floor"] = (datetime.fromisoformat(e["decision_time"])+timedelta(minutes=1)).isoformat()
        with self.assertRaises(AssertionError): run(m, [e])

    def test_decision_nine_is_new_york_time(self):
        m = market(); e = event(m)
        e["decision_time"] = m["sessions"][1]+"T09:00:00+00:00"
        with self.assertRaises(AssertionError): run(m, [e])
        e["decision_time"] = m["sessions"][1]+"T13:00:00+00:00"
        self.assertEqual(run(m, [e])["trades"], 1)

    def test_control_keeps_qualified_subthreshold_events(self):
        m = market(); e = event(m, score="0.999999999999999999999")
        self.assertEqual(run(m, [e])["trades"], 0)
        self.assertEqual(run(m, [e], arm="filing_control")["trades"], 1)

    def test_unavailable_history_is_not_a_control_event(self):
        m = market(); e = event(m); e["feature_status"] = "unavailable"
        for arm in ["income_surprise", "filing_control"]:
            self.assertEqual(run(m, [e], arm=arm)["intents"], [])

    def test_original_decision_invariant_to_later_prices(self):
        m = market(); changed = deepcopy(m); changed["close"][1:] = 140.; changed["adjusted"][1:] = 140.
        a, b = run(m, [event(m)])["intents"][0], run(changed, [event(changed)])["intents"][0]
        for key in ["decision_time", "original_quantity", "reference_price", "reserved_cash"]:
            self.assertEqual(a[key], b[key])

    def test_sale_cash_waits_for_next_opening_settlement(self):
        m = market(("A", "B", "C", "D", "E", "F"))
        m["close"][:, :5] = 1.; m["adjusted"][:, :5] = 1.; m["atr"][:, :5] = .001
        events = [event(m, s) for s in m["symbols"][:5]]+[event(m, "F", 6), event(m, "F", 7)]
        report = run(m, events)
        ftrades = [t for t in report["trade_records"] if t["symbol"] == "F"]
        self.assertEqual(len(ftrades), 1)
        self.assertEqual(ftrades[0]["entry_session"], m["sessions"][7])
        self.assertLess(report["equity_curve"][6]["settled_cash"], 100)
        self.assertGreater(report["equity_curve"][6]["unsettled_cash"], 1900)

    def test_same_result_as_shared_engine_when_reservation_nonbinding(self):
        m = market(); events = [event(m), event(m, entry=12)]
        rank, counts, _ = event_rankings(m, events, "income_surprise")
        for profile in ["proportional", "moomoo_ca_us"]:
            old = _simulate_daily(m, "income_surprise", 5, 2000, 40, 0, len(m["sessions"])-1,
                                 audit=True, signal_ranking=rank, signal_counts=counts,
                                 cost_model=get_cost_profile(profile, 40))
            new = run(m, events, profile=profile)
            np.testing.assert_allclose([r["equity"] for r in new["equity_curve"]], old["equity"], rtol=0, atol=1e-10)
            self.assertEqual(new["trades"], old["trades"])


if __name__ == "__main__":
    unittest.main()

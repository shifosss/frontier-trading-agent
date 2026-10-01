"""Cash and timing fixtures with independent dollar expectations, no market data."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location("etf_account_adapter", Path(__file__).with_name("adapter.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(columns=1):
    days = [f"2024-01-{day:02d}" for day in range(2, 14)]
    close = np.full((len(days), columns), 100.)
    market = {"sessions": days, "dates": np.array(days, dtype="datetime64[D]"),
              "symbols": list("ABCDEF")[:columns], "close": close, "adjusted": close.copy(),
              "atr": np.full(close.shape, .5), "settlement_index": np.arange(len(days))+1,
              "signal_available_at": [day+"T21:01:00+00:00" for day in days]}
    ranking = np.tile(np.arange(columns), (len(days), 1)).astype(np.int32)
    counts = np.zeros(len(days), dtype=np.int32)
    counts[0] = columns
    return market, ranking, counts


def run(market, ranking, counts, **kwargs):
    return m.run_account(market, ranking, counts, arm="fixture", cost_profile="wealthsimple_usd",
                         cost_bps=kwargs.pop("cost_bps", 0), capital=2000, first=0,
                         last=len(market["sessions"])-1, **kwargs)


class AccountTests(unittest.TestCase):
    def test_unchanged_engine_agrees_when_reservations_do_not_bind(self):
        from frontier.execution_costs import get_cost_profile
        from frontier.short_horizon_study import _simulate_daily, _summarize
        market, ranking, counts = fixture(3)
        # Declining marks exercise nonzero P&L without increasing entry quantities.
        market["close"][2:] = market["adjusted"][2:] = 99.
        report = run(market, ranking, counts, cost_bps=10)
        direct = _simulate_daily(market, "fixture", 3, 2000, 10, 0, len(counts)-1,
                                 audit=True, signal_ranking=ranking, signal_counts=counts,
                                 cost_model=get_cost_profile("wealthsimple_usd", 10))
        expected = _summarize(direct, market["sessions"], 2000)
        for key in ("equity_curve", "ending_equity", "total_return", "max_drawdown",
                    "period_metrics", "period_returns", "activity"):
            self.assertEqual(report[key], expected[key])
        for key, value in expected["trade_metrics"].items():
            if value is None:
                self.assertIsNone(report["trade_metrics"][key])
            else:
                self.assertAlmostEqual(report["trade_metrics"][key], value, places=10)

    def test_next_close_three_sessions_and_final_settlement(self):
        market, ranking, counts = fixture()
        result = run(market, ranking, counts)
        trade = result["trade_records"][0]
        self.assertEqual((trade["signal_session"], trade["entry_session"], trade["exit_session"]),
                         tuple(market["sessions"][i] for i in (0, 1, 4)))
        self.assertEqual(trade["quantity"], 4)
        self.assertEqual(trade["holding_sessions"], 3)
        self.assertEqual(result["ending_equity"], 2000)
        self.assertEqual(result["final_state"]["settled_cash"], 2000)
        self.assertEqual(result["final_state"]["receivables"], [])

    def test_fixed_reservation_and_no_increase_when_price_falls(self):
        for price, expected in ((101., 3), (50., 4)):
            market, ranking, counts = fixture()
            market["close"][1:] = price
            market["adjusted"][1:] = price
            result = run(market, ranking, counts)
            trade = result["trade_records"][0]
            self.assertEqual(trade["original_quantity"], 4)
            self.assertEqual(trade["quantity"], expected)
            self.assertEqual(trade["reserved_cash"], 400)
            self.assertLessEqual(trade["entry_notional"]+trade["entry_fee"], 400)

    def test_fee_inclusive_reservation_and_independent_dollars(self):
        market, ranking, counts = fixture()
        result = run(market, ranking, counts, cost_bps=10)
        trade = result["trade_records"][0]
        self.assertEqual(trade["quantity"], 3)
        self.assertAlmostEqual(trade["reserved_cash"], 300.15)
        self.assertAlmostEqual(trade["entry_fee"], .15)
        self.assertAlmostEqual(trade["exit_fee"], .15)
        self.assertAlmostEqual(result["ending_equity"], 1999.70)

    def test_required_missing_fill_is_invalid_not_abstention(self):
        market, ranking, counts = fixture()
        market["close"][1, 0] = np.nan
        result = run(market, ranking, counts)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn(":entry", result["missing"][0])

    def test_halt_uses_next_close_and_retains_gap_overshoot(self):
        market, ranking, counts = fixture(5)
        counts[:] = 5
        market["close"][2:] = market["adjusted"][2:] = 50.
        market["close"][3:] = market["adjusted"][3:] = 30.
        original = counts.copy()
        result = run(market, ranking, counts)
        self.assertEqual(result["drawdown_halt"]["session"], market["sessions"][2])
        self.assertEqual(result["ending_equity"], 600)
        self.assertAlmostEqual(result["max_drawdown"], .7)
        self.assertEqual(len(result["trade_records"]), 5)
        self.assertTrue(all(t["exit_session"] == market["sessions"][3] for t in result["trade_records"]))
        self.assertTrue(all(t["exit_advanced_by_halt"] for t in result["trade_records"]))
        np.testing.assert_array_equal(counts, original)

    def test_halt_cancels_pending_without_cash_refund(self):
        market, ranking, counts = fixture(6)
        counts[0] = 4
        ranking[3] = [5, 0, 1, 2, 3, 4]
        counts[3] = 1
        market["close"][3:, :4] = market["adjusted"][3:, :4] = 50.
        result = run(market, ranking, counts)
        canceled = [x for x in result["intents"] if x["status"] == "canceled_drawdown_halt"]
        self.assertEqual([x["symbol"] for x in canceled], ["F"])
        self.assertEqual(result["ending_equity"], 1200)
        self.assertEqual(result["final_state"]["settled_cash"], 1200)
        self.assertEqual(len(result["trade_records"]), 4)


if __name__ == "__main__":
    unittest.main()

import hashlib
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("etf_signals", ROOT / "signals.py")
signals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signals)


def fixture(n=230):
    symbols = sorted(["DIA", "IWM", "QQQ", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "SPY"])
    k = np.arange(n)
    x = .001 * np.sin(k * .67) + .0005 * np.cos(k * .37)
    returns = np.column_stack([.0001 + 1.2*x + .0005*np.sin(k*1.11+j) for j in range(11)])
    returns[:, symbols.index("SPY")] = x
    adjusted = 100*np.exp(np.cumsum(returns, axis=0))
    return {"sessions": pd.bdate_range("2024-01-02", periods=n).strftime("%Y-%m-%d").tolist(),
            "symbols": symbols, "benchmark": symbols.index("SPY"), "adjusted": adjusted,
            "close": adjusted.copy(), "atr": np.ones_like(adjusted)}


class SignalsTest(unittest.TestCase):
    def test_exact_ols_and_two_session_exclusion(self):
        market = fixture()
        t, j = 205, 0
        original = signals.build_signals(market)
        prices = market["adjusted"]
        r = np.log(prices[1:] / prices[:-1])
        # Return array row k-1 belongs to session k: independent least-squares reference.
        x = r[t-62:t-2, market["benchmark"]]
        y = r[t-62:t-2, j]
        alpha, beta = np.linalg.lstsq(np.column_stack([np.ones(60), x]), y, rcond=None)[0]
        sigma = np.sqrt(np.sum((y-alpha-beta*x)**2)/58)
        expected = np.sum(r[t-2:t, j]-alpha-beta*r[t-2:t, market["benchmark"]])/(np.sqrt(2)*sigma)
        self.assertAlmostEqual(original["z"][t, j], expected, places=11)
        market["adjusted"][t-1:, j] *= .98
        market["adjusted"][t:, j] *= .98
        changed = signals.build_signals(market)
        for key in ["alpha", "beta", "sigma"]:
            self.assertEqual(original[key][t, j], changed[key][t, j])
        self.assertLess(changed["z"][t, j], -2)

    def test_future_prices_do_not_change_prior_signals(self):
        market = fixture()
        before = signals.build_signals(market)
        market["adjusted"][211:] *= np.arange(1, 20)[:, None]*10
        market["close"][211:] = np.nan
        market["atr"][211:] = 0
        after = signals.build_signals(market)
        for key in ["eligible", "z", "alpha", "beta", "sigma", "trend", "trend_known"]:
            np.testing.assert_array_equal(before[key][:211], after[key][:211])
        for arm in signals.ARMS:
            np.testing.assert_array_equal(before["ranking"][arm][:211], after["ranking"][arm][:211])
            np.testing.assert_array_equal(before["counts"][arm][:211], after["counts"][arm][:211])

    def test_control_same_count_and_frozen_hash_order(self):
        market = fixture()
        t = 205
        for symbol in ["DIA", "IWM"]:
            j = market["symbols"].index(symbol)
            market["adjusted"][t-1:, j] *= .96
        result = signals.build_signals(market)
        k = result["counts"]["residual_reversal"][t]
        self.assertEqual(k, 2)
        self.assertEqual(result["counts"]["matched_count_control"][t], k)
        candidates = [j for j, okay in enumerate(result["eligible"][t]) if okay]
        candidates.sort(key=lambda j: (hashlib.sha256((signals.CONTROL_SEED+market["sessions"][t]+":"+market["symbols"][j]).encode()).hexdigest(), market["symbols"][j]))
        np.testing.assert_array_equal(result["ranking"]["matched_count_control"][t, :k], candidates[:k])
        self.assertFalse(result["eligible"][:, market["benchmark"]].any())

    def test_missing_and_degenerate_inputs_are_unavailable(self):
        market = fixture()
        t, j = 205, 0
        market["adjusted"][t-62, j] = np.nan
        self.assertFalse(signals.build_signals(market)["eligible"][t, j])
        market = fixture()
        market["adjusted"][:, j] = market["adjusted"][:, market["benchmark"]]
        self.assertFalse(signals.build_signals(market)["eligible"][t, j])
        market["adjusted"][:, market["benchmark"]] = 100
        self.assertFalse(signals.build_signals(market)["eligible"].any())

    def test_trend_unknown_off_and_on_and_entry_scope(self):
        market = fixture()
        j, t = 0, 205
        market["adjusted"][t-1:, j] *= .96
        result = signals.build_signals(market)
        self.assertFalse(result["trend_known"][:199].any())
        self.assertTrue(result["trend_known"][t])
        expected = market["adjusted"][t, market["benchmark"]] > market["adjusted"][t-199:t+1, market["benchmark"]].mean()
        self.assertEqual(result["trend"][t], expected)
        self.assertEqual(result["counts"]["residual_reversal_trend"][t], result["counts"]["residual_reversal"][t] if expected else 0)
        market["sessions"][t+1] = "2026-01-02"
        stopped = signals.build_signals(market)
        self.assertTrue(stopped["eligible"][t, j])
        self.assertTrue(all(stopped["counts"][arm][t] == 0 for arm in signals.ARMS))


if __name__ == "__main__":
    unittest.main()

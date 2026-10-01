import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("etf_preparation", ROOT / "prepare_market.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


def fixture():
    sessions = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    stamps = [int(pd.Timestamp(s+"T14:30:00Z").timestamp()) for s in sessions]
    prices = [50., 51., 52., 53.]
    body = {"chart": {"error": None, "result": [{"meta": {"symbol": "DIA", "currency": "USD"},
        "timestamp": stamps, "indicators": {"quote": [{"close": prices, "high": [p+1 for p in prices],
        "low": [p-1 for p in prices], "volume": [100., 200., 300., 400.]}], "adjclose": [{"adjclose": prices}]},
        "events": {"splits": {"example": {"date": stamps[2], "numerator": 2, "denominator": 1}}}}]}}
    record = {"captured_at": "2024-01-06T00:00:00Z", "requested_as_of": "2024-01-06T00:00:00Z",
              "spec": {"symbol": "DIA", "currency": "USD", "calendar": "XNYS"}}
    return sessions, body, record


class PreparationTest(unittest.TestCase):
    def test_nominal_adjusted_source_mapping_and_missing_are_explicit(self):
        sessions, body, record = fixture()
        body["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None
        values, audit = prep.source_panel(body, record, sessions)
        np.testing.assert_array_equal(values["close"][[0, 2, 3]], [100., 52., 53.])
        np.testing.assert_array_equal(values["adjusted"][[0, 2, 3]], [50., 52., 53.])
        self.assertTrue(np.isnan(values["close"][1]))
        self.assertEqual(audit["missing_or_rejected_sessions"], [sessions[1]])
        self.assertEqual(audit["raw_invalid_rows"][0]["session"], sessions[1])
        self.assertEqual(audit["actions"], body["chart"]["result"][0]["events"])

    def test_duplicate_daily_rows_fail_without_canonical_choice(self):
        sessions, body, record = fixture()
        raw = body["chart"]["result"][0]
        raw["timestamp"][1] = raw["timestamp"][0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prep.source_panel(body, record, sessions)

    def test_atr_uses_only_prior_and_current_prices(self):
        n = 40
        close = 100+np.arange(n)*.2
        adjusted = close*.5
        atr = prep.normalized_atr(close, adjusted, close+2, close-1)
        self.assertTrue(np.isnan(atr[:14]).all())
        self.assertAlmostEqual(atr[14], 3)
        changed = close.copy()
        changed[25:] *= 8
        again = prep.normalized_atr(changed, changed*.5, changed+2, changed-1)
        np.testing.assert_array_equal(atr[:25], again[:25])


if __name__ == "__main__":
    unittest.main()

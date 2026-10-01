"""The new calibration treatment must retain the original account mechanics."""
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("shrinkage_runner", ROOT / "run_study.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_same_forecasts_reproduce_original_account_across_model_boundary(tmp_path):
    market = runpy.run_path("tests/test_short_horizon_study.py")["market"](n=11, count=3)
    ranking = np.tile([0, 1], (11, 1)); ranking[3] = [1, 0]
    counts = np.zeros(11, dtype=int); counts[[0, 3]] = 1
    forecast = np.full((11, 3, 6), np.nan)
    forecast[:3, 0] = [.1, .1, .1, 0, 0, 0]
    forecast[3:, 0] = [-.1, -.1, -.1, 0, 0, 0]
    forecast[3:, 1] = [.1, .1, .1, 0, 0, 0]
    request = {"holding_sessions": [1, 3, 5], "capital_usd": 2000, "round_trip_bps": 40}
    args = (market, ranking, counts, forecast, "same-forecasts", request, "definition", 0, 10)
    for profile in ("proportional", "moomoo_ca_us"):
        with patch.object(runner.source, "ROOT", tmp_path / "control"):
            original = runner.source.evaluate_account(*args, "conditional_net_dollars", 5, profile)
        with patch.object(runner, "ROOT", tmp_path / "new"):
            changed = runner.evaluate_account(*args, runner.POLICY, 5, profile)
            resumed = runner.evaluate_account(*args, runner.POLICY, 5, profile)
        assert resumed == json.loads(json.dumps(changed))
        assert original["status"] == changed["status"] == "complete"
        assert len(original["trade_records"]) == 2
        assert original["trade_records"] == changed["trade_records"]
        assert original["equity_curve"] == changed["equity_curve"]
        assert original["policy_audit"] == changed["policy_audit"]
        assert original["activity"] == changed["activity"]
        assert original["trade_records"][0]["entry_session"] < market["sessions"][3] < original["trade_records"][0]["exit_session"]

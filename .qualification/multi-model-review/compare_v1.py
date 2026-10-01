"""Read-only default-engine regression against Git HEAD, with actual output equality."""

import hashlib
import json
import runpy
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from frontier import historical_study as current_historical
from frontier import short_horizon_study as current_short

OUT = Path(__file__).resolve().parent
RTK = r"D:\安装包\rtk-x86_64-pc-windows-msvc\rtk.exe"
GIT = [RTK, "proxy", "git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT)]


def original(name):
    raw = subprocess.check_output(GIT + ["show", f"HEAD:src/frontier/{name}.py"], cwd=ROOT)
    module = types.ModuleType("head_" + name)
    module.__file__ = str(OUT / ("head_" + name + ".py"))
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module, hashlib.sha256(raw).hexdigest()


def equal(left, right, name):
    if isinstance(left, np.ndarray):
        np.testing.assert_array_equal(left, right, err_msg=name)
    elif isinstance(left, dict):
        assert left.keys() == right.keys(), (name, "keys")
        for key in left:
            equal(left[key], right[key], name + "." + str(key))
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right), (name, "length")
        for index, (a, b) in enumerate(zip(left, right)):
            equal(a, b, name + f"[{index}]")
    elif isinstance(left, float) and np.isnan(left):
        assert np.isnan(right), name
    else:
        assert left == right, (name, left, right)


def main():
    started = time.perf_counter()
    old_strategy, strategy_sha = original("strategy_study")
    old_historical, historical_sha = original("historical_study")
    old_short, short_sha = original("short_horizon_study")
    old_historical._market = old_strategy._market
    old_historical._prepare = old_strategy._prepare
    for name in ("_build_market", "_benchmark", "_metrics", "_notify"):
        setattr(old_short, name, getattr(old_historical, name))
    old_short._prepare = old_strategy._prepare
    helpers = runpy.run_path(str(ROOT / "tests/test_short_horizon_study.py"))
    histories = runpy.run_path(str(ROOT / "tests/test_historical_study.py"))
    cases = trades = 0
    for seed in range(3):
        rng = np.random.default_rng(seed)
        market = helpers["market"](n=120, count=7, lag=3)
        prices = 10 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, (120, 7)), axis=0))
        market["close"] = prices.copy()
        market["adjusted"] = prices.copy()
        market["atr"] = 0.02 * prices
        market["market_trend"] = np.arange(120) % 7 != 0
        for family in market["ranking"]:
            market["ranking"][family] = np.argsort(rng.random((120, 6)), axis=1)
            market["counts"][family][:] = rng.integers(0, 7, 120)
        for missing in (False, True):
            if missing:
                market["adjusted"][45, :6] = np.nan
            for strategy in current_short.FAMILIES:
                for horizon in (1, 3, 5):
                    for cost in (20, 100):
                        arguments = (market, strategy, horizon, 2000, cost, 0, 119)
                        old = old_short._simulate_daily(*arguments, audit=True)
                        new = current_short._simulate_daily(*arguments, audit=True)
                        equal(old, new, f"sim/{seed}/{missing}/{strategy}/{horizon}/{cost}")
                        trades += new["trades"]
                        cases += 1
    frame, universe, as_of = histories["_history"](1040)
    old_market = old_historical._build_market(frame, universe, pd.Timestamp(as_of), "USD", None)
    new_market = current_historical._build_market(frame, universe, pd.Timestamp(as_of), "USD", None)
    equal(old_market, new_market, "default-market-builder")
    old_public = old_short.evaluate_short_horizon(frame, universe, as_of=as_of, budgets=(500,))
    new_public = current_short.evaluate_short_horizon(frame, universe, as_of=as_of, budgets=(500,))
    equal(old_public, new_public, "public-short-study")
    report = {
        "git_head": subprocess.check_output(GIT + ["rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "head_sha256": {"strategy_study": strategy_sha, "historical_study": historical_sha, "short_horizon_study": short_sha},
        "current_sha256": {name: hashlib.sha256((ROOT / "src/frontier" / (name + ".py")).read_bytes()).hexdigest() for name in ("strategy_study", "historical_study", "short_horizon_study")},
        "deterministic_ledger_cases_exactly_equal": cases,
        "completed_trades_compared": trades,
        "default_market_builder_exactly_equal": True,
        "public_short_study_exactly_equal": True,
        "public_fixed_rows": len(new_public["portfolios"]),
        "public_rolling_rows": len(new_public["walk_forward"]),
        "seconds": time.perf_counter() - started,
        "scope": "Current default branches match complete Git HEAD output values; no source mutation or broker access.",
    }
    (OUT / "default-v1-equality.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

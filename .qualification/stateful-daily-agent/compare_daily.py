import importlib.util
import json
import runpy
import time
from pathlib import Path

import numpy as np
from frontier.short_horizon_study import _simulate_daily

base = Path(__file__).parent
spec = importlib.util.spec_from_file_location("baseline_daily", base / "baseline_short_horizon_study.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
market = runpy.run_path("tests/test_short_horizon_study.py")["market"]


def same(a, b, key="root"):
    if isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=key)
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), key
        for k in a:
            same(a[k], b[k], key + "." + str(k))
    elif isinstance(a, list):
        assert len(a) == len(b), key
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, key + "." + str(i))
    else:
        assert a == b, (key, a, b)

cases = trades = 0
old_time = new_time = 0
for seed in range(10):
    rng = np.random.default_rng(seed)
    data = market(n=160, count=15, lag=1 + seed % 3)
    returns = rng.normal(0.0002, 0.025, (160, 15))
    data["adjusted"] = 10 * np.cumprod(1 + returns, axis=0)
    data["close"] = data["adjusted"].copy()
    data["atr"] = data["close"] * rng.uniform(0.003, 0.05, (160, 15))
    scores = rng.normal(size=(160, 14))
    ranks = np.argsort(-scores, axis=1)
    counts = (scores > 0).sum(axis=1)
    for horizon in (1, 3, 5):
        for cost in (0, 20, 40, 100):
            for correlation in (None, 0.85):
                kwargs = dict(audit=True, signal_ranking=ranks, signal_counts=counts,
                              signal_known=np.ones(160, dtype=bool), correlation_limit=correlation)
                start = time.perf_counter()
                old = module._simulate_daily(data, "learned", horizon, 2000, cost, 0, 159, **kwargs)
                old_time += time.perf_counter() - start
                start = time.perf_counter()
                new = _simulate_daily(data, "learned", horizon, 2000, cost, 0, 159, **kwargs)
                new_time += time.perf_counter() - start
                same(old, new)
                cases += 1
                trades += new["trades"]
report = dict(cases=cases, trades=trades, comparison="exact all arrays, trades, fees, activities, cash state and metrics",
              baseline_seconds=old_time, shared_planner_seconds=new_time, passed=True)
(base / "daily-policy-differential.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))

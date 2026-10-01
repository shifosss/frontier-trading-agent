"""Frozen causal ETF residual signals; no forward labels or account evaluation."""
import hashlib

import numpy as np

ARMS = ("residual_reversal", "residual_reversal_trend", "matched_count_control")
CONTROL_SEED = "frontier-etf-reversal-control-v1:"
UNIVERSE = ("DIA", "IWM", "QQQ", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV")


def build_signals(market):
    sessions, symbols = market["sessions"], market["symbols"]
    prices = np.asarray(market["adjusted"], dtype=np.float64)
    n, m = prices.shape
    if set(symbols) != set(UNIVERSE) | {"SPY"} or len(symbols) != 11 or len(sessions) != n:
        raise ValueError("The frozen ETF universe or session dimension differs")
    benchmark = market["benchmark"]
    if symbols[benchmark] != "SPY":
        raise ValueError("The reference must be SPY")
    returns = np.full_like(prices, np.nan)
    valid = np.isfinite(prices) & (prices > 0)
    pairs = valid[1:] & valid[:-1]
    np.log(np.divide(prices[1:], prices[:-1], out=np.ones_like(prices[1:]), where=pairs),
           out=returns[1:], where=pairs)
    result = {key: np.full_like(prices, np.nan) for key in ["z", "alpha", "beta", "sigma"]}
    result.update(eligible=np.zeros((n, m), dtype=bool), trend=np.zeros(n, dtype=bool),
                  trend_known=np.zeros(n, dtype=bool),
                  ranking={arm: np.zeros((n, m), dtype=np.int32) for arm in ARMS},
                  counts={arm: np.zeros(n, dtype=np.int32) for arm in ARMS})
    machine = np.finfo(np.float64)
    for t in range(62, n):
        if t >= 199 and valid[t-199:t+1, benchmark].all():
            result["trend_known"][t] = True
            result["trend"][t] = prices[t, benchmark] > prices[t-199:t+1, benchmark].mean()
        if not valid[t-62:t+1, benchmark].all():
            continue
        x = returns[t-61:t-1, benchmark]
        dx = x-x.mean()
        denominator = float(dx @ dx)
        if not np.isfinite(denominator) or denominator <= 0:
            continue
        for j, symbol in enumerate(symbols):
            if symbol == "SPY" or not valid[t-62:t+1, j].all():
                continue
            if not np.isfinite([market["close"][t, j], market["atr"][t, j]]).all():
                continue
            if min(market["close"][t, j], market["atr"][t, j]) <= 0:
                continue
            y = returns[t-61:t-1, j]
            beta = float(dx @ (y-y.mean())/denominator)
            alpha = float(y.mean()-beta*x.mean())
            fitted = alpha+beta*x
            residual = y-fitted
            norm = float(np.linalg.norm(residual))
            floor = 64*machine.eps*max(float(np.linalg.norm(y)), float(np.linalg.norm(fitted)), machine.tiny)
            if not np.isfinite([alpha, beta, norm]).all() or norm <= floor:
                continue
            sigma = norm/np.sqrt(58)
            z = float(np.sum(returns[t-1:t+1, j]-alpha-beta*returns[t-1:t+1, benchmark])/(np.sqrt(2)*sigma))
            if not np.isfinite(z) or sigma <= 0:
                continue
            for key, value in [("alpha", alpha), ("beta", beta), ("sigma", sigma), ("z", z)]:
                result[key][t, j] = value
            result["eligible"][t, j] = True
        if t+1 >= n or not "2017-01-03" <= sessions[t+1] <= "2025-12-31":
            continue
        selected = [j for j in np.flatnonzero(result["eligible"][t]) if result["z"][t, j] <= -2]
        selected.sort(key=lambda j: (result["z"][t, j], symbols[j]))
        control = sorted(np.flatnonzero(result["eligible"][t]), key=lambda j: (
            hashlib.sha256((CONTROL_SEED+sessions[t]+":"+symbols[j]).encode()).hexdigest(), symbols[j]
        ))[:len(selected)]
        for arm, candidates in zip(ARMS, [selected, selected if result["trend"][t] else [], control]):
            result["counts"][arm][t] = len(candidates)
            result["ranking"][arm][t, :len(candidates)] = candidates
    return result

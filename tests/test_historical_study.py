import json

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from frontier.historical_study import (
    FAMILIES,
    _benchmark,
    _build_market,
    _choose,
    _metrics,
    _selection,
    _simulate,
    evaluate_historical,
)


def _market(n=60, prices=None):
    close = np.full((n, 6), 10.0) if prices is None else np.asarray(prices, dtype=float)
    return {
        "n": len(close),
        "symbols": ["AAA", "BBB", "CCC", "DDD", "EEE", "SPY"],
        "sessions": pd.bdate_range("2020-01-01", periods=len(close)).strftime("%Y-%m-%d").tolist(),
        "close": close,
        "adjusted": close.copy(),
        "atr": np.full(close.shape, 0.125),
        "ranking": {
            key: np.tile(np.arange(5), (len(close), 1))
            for key in FAMILIES
            if not key.endswith("_market_trend")
        },
        "counts": {
            key: np.full(len(close), 5) for key in FAMILIES if not key.endswith("_market_trend")
        },
        "benchmark": 5,
        "benchmark_symbol": "SPY",
        "market_trend": np.ones(len(close), dtype=bool),
        "market_trend_known": np.ones(len(close), dtype=bool),
    }


def test_cash_whole_shares_fees_and_t_plus_three_settlement():
    market = _market(n=30)
    result = _simulate(market, "momentum", 5, 1000, 100, 0, 29)
    batch = result["trade_batches"][0]
    assert batch["planned_quantities"] == [19] * 5
    assert batch["filled_quantities"] == [19] * 5
    assert batch["entry_notional"] == 950
    assert batch["fees"] == pytest.approx(9.5)
    assert batch["ending_cash"] == pytest.approx(990.5)
    assert result["cash"].min() >= 0
    positions = {session: i for i, session in enumerate(market["sessions"])}
    batches = result["trade_batches"]
    for previous, current in zip(batches, batches[1:]):
        assert positions[current["entry_session"]] - positions[previous["exit_session"]] == 3
    assert result["equity"][-1] == pytest.approx(1000 - result["fees"])
    assert result["equity"][-1] < batches[0]["ending_cash"]


def test_entry_gap_never_increases_quantity_and_split_mark_is_continuous():
    market = _market(n=7)
    market["close"][1:, :5] = 20
    market["adjusted"][1:, :5] = 10
    market["close"][3:, :5] = 10
    result = _simulate(market, "momentum", 5, 1000, 20, 0, 6)
    batch = result["trade_batches"][0]
    assert batch["planned_quantities"] == [19] * 5
    assert batch["filled_quantities"] == [9] * 5
    assert result["equity"][2] == result["equity"][3]
    assert result["equity"][-1] == pytest.approx(1000 - batch["fees"])


def test_missing_held_price_invalidates_whole_portfolio_and_keeps_failure():
    market = _market()
    market["adjusted"][4, 0] = np.nan
    result = _simulate(market, "momentum", 5, 1000, 20, 0, 59)
    metrics = _metrics(result, market["sessions"], 1000)
    assert result["status"] == "incomplete"
    assert any(value.startswith("AAA:") for value in metrics["missing"])
    assert metrics["total_return"] is None
    assert metrics["max_drawdown"] is None
    assert metrics["equity_curve"][-1]["equity"] is None
    json.dumps(metrics, allow_nan=False)


def test_account_losses_and_drawdown_include_daily_unrealized_path():
    market = _market(n=7)
    market["adjusted"][2:5, :5] = 5
    result = _simulate(market, "momentum", 5, 1000, 20, 0, 6)
    metrics = _metrics(result, market["sessions"], 1000)
    assert metrics["max_drawdown"] > 0.47
    assert -0.003 < metrics["total_return"] < 0
    assert metrics["yearly"][0]["max_drawdown"] == metrics["max_drawdown"]


def test_regime_filter_and_all_ranked_affordable_candidates():
    market = _market()
    market["market_trend"][0] = False
    market["close"][0, :4] = 5000
    selected, quantities = _selection(market, "momentum", 0, 500, 20)
    assert selected.tolist() == [4]
    assert quantities.tolist() == [9]
    assert not len(_selection(market, "momentum_market_trend", 0, 500, 20)[0])
    assert not len(_selection(market, "momentum", 0, 1, 20)[0])


def test_benchmark_uses_full_affordable_cash_and_both_fees():
    market = _market(n=7)
    result = _benchmark(market, 1000, 100, 0, 6)
    assert result["quantity"] == 99
    assert result["equity"][-1] == pytest.approx(990.1)
    assert result["fees"] == pytest.approx(9.9)
    market["adjusted"][4, 5] = np.nan
    assert _benchmark(market, 1000, 100, 0, 6)["status"] == "incomplete"


def test_training_selection_cannot_observe_later_test_prices():
    market = _market(n=1100)
    path = 10 * np.exp(np.arange(1100) * 0.001)
    market["close"][:] = path[:, None]
    market["adjusted"][:] = path[:, None]
    before, candidates = _choose(market, 10000, 200, 955)
    assert before["strategy"] != "cash"
    market["close"][956:] *= 0.01
    market["adjusted"][956:] *= 0.01
    after, changed_candidates = _choose(market, 10000, 200, 955)
    assert before == after
    assert candidates == changed_candidates


def test_cash_fallback_after_unprofitable_training():
    selected, candidates = _choose(_market(n=1000), 1000, 200, 955)
    assert selected["strategy"] == "cash"
    assert len(candidates) == 30
    assert not any(row["eligible"] for row in candidates)


def _history(count=1040):
    calendar = xcals.get_calendar("XNYS", start="2018-01-01", end="2025-12-31")
    sessions = calendar.sessions[:count]
    t = np.arange(count)
    frames, universe = [], []
    for symbol, kind, base in (("AAA", "stock", 10), ("BBB", "stock", 20), ("SPY", "etf", 250)):
        prices = base * np.exp(0.0007 * t) * (1 + 0.012 * np.sin(t * 0.4))
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "session": sessions.strftime("%Y-%m-%d"),
                    "available_at": [
                        calendar.session_close(day) + pd.Timedelta(minutes=1) for day in sessions
                    ],
                    "close": prices,
                    "adjusted_close": prices,
                    "high": prices * 1.01,
                    "low": prices * 0.99,
                    "volume": 2_000_000,
                }
            )
        )
        universe.append(
            {"symbol": symbol, "asset_type": kind, "currency": "USD", "calendar": "XNYS"}
        )
    return (
        pd.concat(frames, ignore_index=True),
        universe,
        calendar.session_close(sessions[-1]) + pd.Timedelta(minutes=2),
    )


def test_public_study_reports_all_attempts_and_frozen_walk_forward_folds():
    frame, universe, as_of = _history()
    progress = []
    result = evaluate_historical(
        frame, universe, as_of=as_of, budgets=(500,), progress=progress.append
    )
    json.dumps(result, allow_nan=False)
    assert len(result["methodology"]["attempts"]) == 30
    assert len(result["portfolios"]) == 90
    assert len(result["benchmarks"]) == 6
    assert len(result["walk_forward"]) == 3
    assert any(row["trades"] > 0 for row in result["portfolios"])
    assert progress[-1]["stage"] == "historical_walk_forward"
    for row in result["walk_forward"]:
        assert row["status"] == "complete"
        fold = row["folds"][0]
        assert fold["training_end"] < fold["test_start"]
        assert len(fold["selection_candidates"]) == 30
        assert fold["test_end"] == row["last_session"]


def test_chunked_features_preserve_stock_specific_warmup_and_future_cutoff(monkeypatch):
    frame, universe, as_of = _history(450)
    ipo = frame.loc[frame.symbol == "BBB"].tail(30).copy()
    ipo["symbol"] = "IPO"
    universe.append({"symbol": "IPO", "asset_type": "stock", "currency": "USD", "calendar": "XNYS"})
    frame = pd.concat([frame, ipo], ignore_index=True)
    monkeypatch.setattr("frontier.historical_study.CHUNK_SIZE", 1)
    market = _build_market(frame, universe, as_of, "USD", None)
    ipo_index = market["symbols"].index("IPO")
    for family, ranks in market["ranking"].items():
        assert ipo_index not in ranks[-1, : market["counts"][family][-1]]
    cutoff = pd.Timestamp(frame.loc[frame.symbol == "AAA", "available_at"].iloc[399])
    before = _build_market(frame, universe, cutoff, "USD", None)
    frame.loc[pd.to_datetime(frame.available_at) > cutoff, "adjusted_close"] *= 100
    after = _build_market(frame, universe, cutoff, "USD", None)
    for key in ("close", "adjusted", "atr"):
        np.testing.assert_equal(before[key], after[key])
    for family in before["ranking"]:
        np.testing.assert_equal(before["ranking"][family], after["ranking"][family])


def test_cash_settlement_is_preserved_across_walk_forward_boundary():
    market = _market(n=30)
    first = _simulate(market, "momentum", 5, 1000, 20, 0, 6)
    second = _simulate(
        market,
        "momentum",
        5,
        float(first["equity"][-1]),
        20,
        7,
        29,
        cash_ready=first["cash_ready"],
    )
    assert first["cash_ready"] == 9
    assert second["trade_batches"][0]["entry_session"] == market["sessions"][9]
    assert second["equity"][0] == first["equity"][-1]
    assert second["equity"][1] == first["equity"][-1]


def test_missing_future_marks_for_zero_fills_do_not_invalidate_cash():
    market = _market(n=7)
    market["close"][1:, :5] = 1000
    market["adjusted"][3:, :5] = np.nan
    result = _simulate(market, "momentum", 5, 1000, 20, 0, 6)
    assert result["status"] == "complete"
    assert result["trades"] == 0
    assert result["equity"][-1] == 1000
    assert result["trade_batches"][0]["filled_quantities"] == [0] * 5
    market["close"][1, 5] = 1000
    market["adjusted"][3, 5] = np.nan
    reference = _benchmark(market, 500, 20, 0, 6)
    assert reference["status"] == "complete"
    assert reference["quantity"] == 0
    assert reference["equity"][-1] == 500


def test_missing_market_filter_input_is_not_interpreted_as_bearish_cash():
    market = _market(n=7)
    market["market_trend"][0] = False
    market["market_trend_known"][0] = False
    filtered = _simulate(market, "momentum_market_trend", 5, 1000, 20, 0, 6)
    baseline = _simulate(market, "momentum", 5, 1000, 20, 0, 6)
    assert filtered["status"] == "incomplete"
    assert filtered["missing"] == ["SPY:2020-01-01:regime_200"]
    assert baseline["status"] == "complete"


def test_intermediate_momentum_requires_253_consecutive_sessions_and_skips_recent_month():
    frame, universe, as_of = _history(450)
    market = _build_market(frame, universe, as_of, "USD", None)
    assert market["counts"]["momentum_12_1"][251] == 0
    assert market["counts"]["momentum_12_1"][252] > 0
    # The skipped-month rule can qualify even after a recent large decline,
    # while the old 20/60 momentum condition rejects it.
    aaa = frame.symbol == "AAA"
    indices = frame.loc[aaa].index
    frame.loc[indices[-20:], ["close", "adjusted_close", "high", "low"]] *= 0.5
    market = _build_market(frame, universe, as_of, "USD", None)
    symbol = market["symbols"].index("AAA")

    def selected(family):
        return market["ranking"][family][-1, : market["counts"][family][-1]]

    assert symbol in selected("momentum_12_1")
    assert symbol not in selected("momentum")

"""Shared close-history signals and capped targets, without execution or scheduling."""

from collections.abc import Mapping

import pandas as pd

from frontier.domain import StrategyConfig


def target_for_history(
    history: pd.Series,
    config: StrategyConfig,
    group_counts: Mapping[str, int],
    exposure_group: str,
) -> tuple[bool, float, str]:
    """Evaluate one due rebalance using only the caller's already-available closes."""
    signal = False
    reason = "warmup"
    warm = config.family in {"cash", "passive"} or len(history) >= config.lookback
    if warm:
        closes = history.iloc[-config.lookback :]
        if config.family == "trend":
            signal = bool(closes.iloc[-1] > closes.mean())
            reason = "close above trailing mean"
        elif config.family == "reversion":
            signal = bool(closes.iloc[-1] < closes.iloc[0])
            reason = "negative trailing close return"
        elif config.family == "passive":
            signal = True
            reason = "equal capped allocation"
        else:
            reason = "cash benchmark"
    weight = min(config.max_weight, 1 / len(group_counts))
    weight /= group_counts[exposure_group]
    return signal, weight if signal else 0.0, reason

"""Historical cash-release dates at regime changes and clearing holidays."""

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from frontier.historical_settlement import build_settlement_indices


def _release_date(sale, currency):
    start, end = pd.Timestamp(sale), pd.Timestamp(sale) + pd.Timedelta(days=32)
    calendar = xcals.get_calendar("XNYS" if currency == "USD" else "XTSE", start=start, end=end)
    sessions = calendar.sessions.strftime("%Y-%m-%d").tolist()
    # Pass just the sale date: release indices must extend beyond the input range.
    release = build_settlement_indices([sale], currency)[0]
    return sessions[release]


@pytest.mark.parametrize("currency", ["USD", "CAD"])
@pytest.mark.parametrize(
    "sale, expected",
    [("2017-09-01", "2017-09-07"), ("2017-09-05", "2017-09-07")],
)
def test_t3_to_t2_uses_trade_date_and_labour_day(currency, sale, expected):
    assert _release_date(sale, currency) == expected


@pytest.mark.parametrize(
    "currency, sale, expected",
    [
        ("USD", "2024-05-24", "2024-05-29"),
        ("USD", "2024-05-28", "2024-05-29"),
        ("CAD", "2024-05-24", "2024-05-28"),
        ("CAD", "2024-05-27", "2024-05-28"),
        ("CAD", "2024-05-28", "2024-05-29"),
    ],
)
def test_t2_to_t1_distinguishes_canada_and_us(currency, sale, expected):
    assert _release_date(sale, currency) == expected


@pytest.mark.parametrize(
    "currency, sale, expected",
    [
        ("USD", "2026-10-09", "2026-10-13"),  # Columbus Day: exchange open.
        ("USD", "2026-11-10", "2026-11-12"),  # Veterans Day: exchange open.
        ("USD", "2026-04-02", "2026-04-06"),  # Good Friday: exchange closed.
        ("USD", "2026-06-18", "2026-06-22"),
        ("USD", "2021-06-17", "2021-06-21"),  # Juneteenth clearing still open.
        ("USD", "2022-06-16", "2022-06-21"),
        ("USD", "2023-11-08", "2023-11-10"),  # Saturday Veterans Day: Friday open.
        ("CAD", "2026-09-29", "2026-10-01"),
        ("CAD", "2026-11-10", "2026-11-12"),
        ("CAD", "2021-09-28", "2021-10-01"),
        ("CAD", "2021-09-29", "2021-10-04"),
        ("CAD", "2020-09-28", "2020-09-30"),  # No retroactive September holiday.
        ("CAD", "2023-09-28", "2023-10-03"),  # Saturday observed Monday.
        ("CAD", "2026-07-31", "2026-08-04"),  # Conservative Civic Holiday delay.
        ("CAD", "2026-02-13", "2026-02-17"),  # Conservative Family Day delay.
    ],
)
def test_bank_and_exchange_holidays(currency, sale, expected):
    assert _release_date(sale, currency) == expected


def test_full_array_keeps_unsettled_cash_beyond_last_session():
    dates = ["2017-08-28", "2017-08-29", "2017-08-30", "2017-08-31", "2017-09-01"]
    result = build_settlement_indices(dates, "USD")
    np.testing.assert_array_equal(result, [3, 4, 5, 6, 7])
    assert result[-1] > len(dates)


def test_rejects_missing_sessions_that_would_shift_settlement_indices():
    with pytest.raises(ValueError, match="consecutive"):
        build_settlement_indices(["2026-09-14", "2026-09-16"], "USD")


def test_empty_and_unsupported_currency():
    assert build_settlement_indices([], "CAD").size == 0
    with pytest.raises(ValueError, match="USD or CAD"):
        build_settlement_indices([], "EUR")

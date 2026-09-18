"""Conservative regular-way stock settlement for the daily historical study.

The trade date selects T+3, T+2 (2017-09-05), or T+1 (Canada 2024-05-27,
US 2024-05-28). We count days when BOTH banking and the local stock exchange
are open, then make proceeds available at that session's open. This is an
availability model, not a complete archive of DTC/CDS processing calendars:
CDS can settle CAD on Family Day/Civic Holiday despite closed exchanges, so
our intersection can delay cash. Broker-specific posting times are not modeled.

Primary sources, checked 2026-09-18:
- US T+2: https://www.sec.gov/rules/final/2017/34-80295.pdf
- Canadian T+2: https://lautorite.qc.ca/fileadmin/lautorite/reglementation/
  valeurs-mobilieres/24-101/2017-09-05/2017sept05-24-101-ig-vconsolidee-en.pdf
- T+1: https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq
  https://www.securities-administrators.ca/news/
  canadian-securities-regulators-announce-move-to-t1-settlement-cycle/
- Currency-specific CDS holidays: https://www.cds.ca/bulletins-and-resources/
  forms-and-documentation/holiday-processing-schedule
- No 2021 Juneteenth closure; Saturday holidays do not close Friday banks:
  https://www.dtcc.com/Globals/PDFs/2021/June/17/15471-21
- Canadian September 30 first applies in 2021:
  https://www.cdcc.ca/u_avis_en/138-21_en.pdf

This separate helper leaves the frozen, contemporary T+1 paper model unchanged.
"""

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    USColumbusDay,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    next_monday,
    sunday_to_monday,
)

SETTLEMENT_ASSUMPTION = (
    "Trade-date T+3/T+2/T+1; count local exchange and banking business days; "
    "cash available at settlement-session open. Conservative exchange intersection "
    "may delay actual clearing; historical broker posting times are not reconstructed."
)


class _USBankHolidays(AbstractHolidayCalendar):
    # Federal Reserve banks remain open on Fridays before Saturday holidays.
    # Exchange closures (including observed Friday holidays) apply separately.
    rules = [
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr,
        USPresidentsDay,
        USMemorialDay,
        Holiday(
            "Juneteenth", month=6, day=19, observance=sunday_to_monday,
            start_date="2022-01-01",
        ),
        Holiday("Independence Day", month=7, day=4, observance=sunday_to_monday),
        USLaborDay,
        USColumbusDay,
        Holiday("Veterans Day", month=11, day=11, observance=sunday_to_monday),
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=sunday_to_monday),
    ]


class _CanadianSettlementOnlyHolidays(AbstractHolidayCalendar):
    # Other recurring CAD banking closures already appear in the XTSE calendar.
    rules = [
        Holiday(
            "Truth and Reconciliation", month=9, day=30, observance=next_monday,
            start_date="2021-01-01",
        ),
        Holiday("Remembrance Day", month=11, day=11, observance=next_monday),
    ]


def build_settlement_indices(sessions: list[str], currency: str) -> np.ndarray:
    """Map each sale session to its first modeled spendable session index.

    Input must contain consecutive XNYS (USD) or XTSE (CAD) sessions from 2000
    onward. Indices continue beyond the supplied range, preserving unsettled cash
    at a fold/end boundary; they are never clamped to the final observed session.
    The caller must carry these indices and sale receivables across rule folds.
    """
    if currency not in {"USD", "CAD"}:
        raise ValueError("Historical stock settlement supports USD or CAD")
    if not sessions:
        return np.array([], dtype=np.int64)
    dates = pd.DatetimeIndex(sessions)
    if dates[0] < pd.Timestamp("2000-01-01"):
        raise ValueError("Historical stock settlement is modeled from 2000 onward")
    calendar = xcals.get_calendar(
        "XNYS" if currency == "USD" else "XTSE",
        start=dates[0], end=dates[-1] + pd.Timedelta(days=32),
    )
    extended = calendar.sessions
    if not dates.equals(extended[: len(dates)]):
        raise ValueError("Settlement dates must be consecutive local exchange sessions")
    bank_calendar = _USBankHolidays() if currency == "USD" else _CanadianSettlementOnlyHolidays()
    holidays = bank_calendar.holidays(extended[0], extended[-1])
    eligible = np.flatnonzero(~extended.isin(holidays))
    t1_start = pd.Timestamp("2024-05-28" if currency == "USD" else "2024-05-27")
    lag = np.where(dates >= t1_start, 1, np.where(dates >= "2017-09-05", 2, 3))
    first_after_sale = np.searchsorted(eligible, np.arange(len(dates)), side="right")
    return eligible[first_after_sale + lag - 1]

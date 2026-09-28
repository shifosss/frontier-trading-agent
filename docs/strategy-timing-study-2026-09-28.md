# Separately declared timing diagnostic — September 28, 2026

**Question:** does waiting until the next close discard useful reversal/continuation return, or avoid an adverse move? This diagnostic reuses the nine frozen strategy signals after the running 54-account experiment completes. It changes neither those signals nor any active account. No timing outcomes have been computed at declaration.

## Retained source feasibility

Yahoo raw `indicators.quote[0].open` is preserved even though `historical_data.normalize_history` currently omits open from its normalized frame. A return-independent schema sample checked SPY/AAPL/MSFT/AIXI plus 32 USD symbols chosen by a fixed SHA256 ranking: all 36 raw-source hashes matched and all 36 had timestamp-aligned open arrays. Of 78,414 rows in January2014–September2026, 78,413 had finite positive opens; one open was missing and three complete positive OHLC bars placed open outside the reported high/low range. Preserve those discrepancies. This is practical source feasibility, not full-universe coverage or confirmation of opening-auction fills. Evidence: `.qualification/strategy-timing20260928/open-availability-definition.json` and `open-availability-audit.json`.

## Exact paired design

Nine policies × 1/3/5-session holds × three timings gives **81 strategy summary cells**, plus nine same-timing SPY reference cells. These are event summaries, not account variants. The main question has **nine primary paired contrasts**, because its log-return timing difference is identical across holding horizons by construction.

For each signal date t from January4,2016, select at most five names using the existing stable score ranking and `plan_entries` with USD2,000 NAV and available cash, no existing holdings/reservations, the original five slots, 20% cap, two-ATR/0.5% risk sizing and 40bps proportional reference planning cost. Use the resulting same symbols across all three horizons and timings. This is isolated reference-size selection, not a persistent account. Require the known calendar t+1+5 to fall no later than September18,2026 for the common cohort window. Do not inspect future price availability when selecting. Retain missing outcomes without replacing names.

Let e=t+1 and x=e+h. Derive same-session adjusted open O* = provider open × provider adjusted close / provider close. The factor and both prices must come from the same raw response, symbol and session. Do not multiply provider open by adjusted-close/reconstructed-nominal-close; that would mix share units. Compare:

1. **Next open, common close exit:** log(C*_x/O*_e). This adds the entry session's intraday exposure to the existing holding path.
2. **Existing next close:** log(C*_x/C*_e).
3. **Next open, equal-clock open exit:** log(O*_x/O*_e), which excludes exit-day intraday exposure and maintains the same h-session opening-to-opening clock.

Report corresponding simple returns separately; use log returns for exact attribution. The critical identity is:

`next-open/common-close return − next-close return = log(C*_e/O*_e) = log(provider close_e/provider open_e)`.

Therefore the entry-delay difference cancels subsequent corporate-action adjustments exactly. A positive entry-day intraday return means next-close entry missed that move; a negative value means the delay avoided it. The equal-clock difference is entry-day intraday return minus exit-day intraday return. Also report log(O*_e/C*_t), the intervening overnight gap. That gap is not available to an agent deciding after close t, and must never be credited to its strategy.

## Timing, accounting and data limits

The existing historical convention makes the close-t signal available at exchange close plus one minute. The next regular-session open follows chronologically, including weekends and holidays, and is a plausible future execution target. This timestamp convention does not prove when the historical vendor actually published the complete bar or when an order could have participated in an opening auction. Yahoo's daily open is an observed vendor bar value, not a guaranteed auction price, fill, or available quantity. Actual open execution needs separately validated data readiness, broker order timing and slippage.

Raw open, high, low, close, adjusted close and timestamps must align; sessions must map uniquely to the exchange calendar. Required values and adjustment factors must be finite and positive. Open/close outside same-source high/low invalidate the affected outcome cell and remain explicit failures. No interpolation, substitute symbol or guessed action repair is allowed.

The adjusted-open construction maintains the provider's adjusted-close convention; it is not a dividend/cash-in-lieu/depositary-fee ledger. Known AIXI mixed units and other source discontinuities remain in cumulative outcomes. Cancellation makes the entry-day paired contrast less exposed to later unit changes, but it does not independently establish the quality or common within-bar units of raw open and close. Report action crossings separately without removing trades. Current-member survivorship and revised historical vintages remain.

No settled cash, changing NAV, overlapping positions, fills, fees, spreads, impact, taxes or FX are simulated. The 40bps planning input only preserves signal-time reference sizing. A favorable timing diagnostic motivates a later predeclared next-open cash replay; it cannot qualify a profitable trading strategy or authorize paper migration by itself.

## Reporting and decision

Retain every planned date-symbol event and its coverage status. Primary timing means use complete active dates where all selected entry-day open/close pairs are valid: equal stock weight within each date, then equal date weight. Report available-pair and per-event results secondarily with explicit denominators. No-signal dates are counted separately. Missing-data selection remains a limitation even with paired comparisons.

Report entry-day intraday, overnight gap, exit-day intraday, both identity residuals, all 81 horizon/timing cells, source failures and yearly/frozen-regime slices. Any bootstrap is exploratory: 2,000 circular moving-block samples of ten dates with seed1729, paired across policies/timings; observations overlap and the history has already been studied. The same common-exit timing edge repeated over three horizons is not three independent findings.

A nonpositive entry-day timing difference refutes the claim that next-close delay systematically consumed that tactic's entry-day return. A positive but unstable difference, especially one concentrated in a few erroneous bars, does not establish a usable edge. A consistently positive gross difference warrants a separately declared next-open execution comparison with actual gap-aware sizing and costs. Preserve unfavorable cases equally.

Exact declaration: `.qualification/strategy-timing20260928/request.json`. The future diagnostic must verify the completed strategy cache against its manifest and the original request/source/code identities. It must not alter the running strategy experiment or rebuild its signals.

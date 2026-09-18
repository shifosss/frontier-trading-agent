# Active-trading cadence and next experiment design

Clarified by the owner on September 18, 2026: the active sleeve is for individual-stock trading with hourly or daily decisions and, at the slowest, weekly activity. It is separate from the regular ETF allocation. The working default for new experiments is intraday or 1-5 trading-session positions, rather than the earlier 10-20-session swing holds.

The default historical lane now implements daily screening and independent 1/3/5-session positions with dated cash settlement; see [historical research](historical-research.md). Hourly stock research and the frozen paper-policy migration remain open. The older historical lane is retained as an explicit legacy comparison.

## Separate the three clocks

| Clock | Meaning | New research direction |
| --- | --- | --- |
| Decision cadence | How often fresh information can change an entry, exit or allocation | Every completed hourly bar or daily session; review existing positions on every eligible event |
| Holding period | Elapsed time from an actual entry to exit | Intraday: 1, 2 or 4 regular-session bars, with a session-close exit; daily: 1, 3 or 5 sessions |
| Historical test span | The dates containing many repeated short trades | Multiple years and market regimes, with individual-trade and weekly/monthly results visible |

Five years of repeated hourly trades is not a five-year holding. Long history remains useful for testing changes in volatility, liquidity and market direction. Aggregate five-year return alone is insufficient: the report must show how often the system trades, actual holding durations, whether profits recur and whether execution costs consume the expected gain. A 200-day feature lookback likewise does not imply a 200-day holding.

An hourly bar may be shorter at the exchange's final session boundary. Record actual elapsed time as well as bar count. Trading hours and sessions use each exchange's calendar; never turn an overnight gap or holiday into a fictitious tradable hour.

## Concrete next tests and reasons

1. **Daily short-hold lane first:** evaluate 1-, 3- and 5-session trades using the retained broad daily histories. These data are already available. Reuse existing rule families as comparisons, then add a small declared set of short-term reversal/continuation hypotheses. Do not assume long-horizon momentum is automatically suited to one-day trading.
2. **Screen every eligible session, including while idle.** Reconsider holdings and independently available slots each day. Do not force a trade when no opportunity survives costs and sizing. Do not skip the next several sessions merely because today's signal is empty.
3. **Use a portfolio event loop that permits independent position exits and entries.** The current all-at-once, nonoverlapping batches and blanket T+3 cash reuse are a legacy comparison, not a realistic claim of daily turnover. Reuse verified timing/accounting primitives. Model the applicable settlement regime and broker cash rules explicitly; unused settled cash can fund an entry while other sale proceeds are unsettled. Do not assume margin or replace historical settlement rules globally with today's rule.
4. **Label execution accurately.** A signal from today's close cannot fill at that same close. Existing historical one-session arithmetic is next-close to following-close, an overnight daily test. It cannot establish a same-day strategy. Next-open or intraday tests need actual open/bar data and gap/slippage handling; daily bars must not be interpolated into hourly observations.
5. **Add an hourly lane using verified stock data.** Compare 1-, 2- and 4-bar holds with daily/overnight effects separated. The only retained imported hourly dataset has 434 SPY bars from June 22 through September 17, 2026. It supports timing checks, not broad individual-stock profitability claims. Qualify existing free/authorized data access, adjustments, timestamps and source-specific volume before interpreting VWAP or liquidity signals. Ask before any new spending.
6. **Change trading cadence before retuning selection frequency.** Keep the existing 756-session training and 252-session rule-selection evaluation as the first controlled comparison, while reporting weekly/monthly outcomes and actually trading at the new short cadence. This isolates the effect of the cadence change. A later, separately declared adaptation experiment can use 252 prior sessions and 21-session test blocks, with training sub-blocks defined independently of evaluation length. Signal features may need additional pre-training warmup. Purge training outcomes that overlap the next test block; keep the selected rule fixed within each block while positions change at the declared cadence. Neither annual nor monthly parameter updates require positions to be held that long.

Record this new experiment definition before inspecting its outcomes. Previously viewed historical data are reused research, not a newly untouched holdout. Broader windows supply repeated opportunities and stress periods; useful sampling, execution realism and out-of-sample chronology matter more than maximizing a grid's size.

## Required readout

- Actual trades per session/week, average and maximum holding duration, time invested, unused/settled cash and reasons for inactivity.
- Net expectancy per completed trade, win rate with average win/loss, profit factor where defined, turnover, commissions, spread and slippage sensitivity.
- Weekly/monthly return distributions, profitable-period frequency, worst day/week/month, peak drawdown and recovery duration, consecutive losses and tail losses.
- Results by market regime, liquidity band and account size; concentration of profit in a few dates or names. Preserve failed/incomplete attempts.
- Matched-period cash and market references plus simpler strategy baselines. Annualized return remains context, not the sole ranking criterion. No future return or 30% loss cap is guaranteed by a passing historical filter.

## Legacy findings and remaining work

- The retained legacy historical engine uses 5/10/20-session holds, 756-session training and 252-session evaluation. Its no-position branch advances by `horizon + 3`, so merely changing the horizon tuple would still miss daily signals.
- The legacy training-score partition depends on the evaluation length. Changing evaluation to 21 sessions without changing that partition would create unequal training blocks. The new short-hold lane already declares training sub-blocks separately; any future monthly-selection experiment must keep that separation.
- The earlier cohort study caches ranks every five sessions. Replacing its shared horizons with 1/3/5 would request uncached ranks. The new versioned short-hold lane avoids mutating those archived semantics.
- The frozen paper operator decides entries weekly, checks exits daily and allows 20-session holds. Its five-minute worker interval is reconciliation polling, not a five-minute strategy. It remains a legacy paper execution baseline until a tested policy/state migration implements the new mandate.
- The scheduled Codex research follow-ups are development wakeups, not the strategy's market-event clock. Their current twice-daily schedule does not define the eventual hourly trading frequency.

## Completion criteria for the next implementation

Demonstrate a signal becoming eligible on the next idle day is considered; independent positions can exit without resetting other ages; unsettled proceeds cannot be spent early; no close-derived signal receives a same-close fill; the daily and hourly holding limits are measured from actual fills; and any monthly-selection experiment uses only prior completed outcomes. Run the declared short-hold experiments before proposing a paper-policy migration. Preserve the reserved ETFs, existing paper journal, historical artifacts and source identities throughout.

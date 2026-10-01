# Isolated earnings accounts interface

This adapter implements the frozen 20-account specification 7e837043e034305fe3aa15aefd3d28d8389f63e923fc7ef0739d1883e8a30ffb. No actual study account, original-cohort model fit, network access or paper-account change was performed during adapter qualification. Synthetic model fitting occurred only in isolated tests.

## Call contract

run_account(market, events, *, recipe, cost_profile, capital=10000, forecasts=None, forecast_identity=None, first=None, last=None)

- recipe: exactly filing_control, income_surprise, income_cash_confirmation, ridge, or hist_gradient_boosting.
- cost_profile: exactly proportional_40bps or moomoo_ca_us_plus_40bps, mapped to the existing shared cost object with 40 bps round-trip friction.
- capital: 10000 or 2000 only.
- market: existing shared daily engine contract: symbols, chronological official sessions, dates, raw execution close, adjusted marks, ATR, and historical settlement indices. No synthetic hourly observations.
- events: all retained prepared original events, not a future-label-filtered subset. Each carries immutable event_id, CIK (cik), symbol, accession, S/Q and original clocks/statuses, plus model_input_status, optional model_input_reasons, five finite ordered model_inputs, prior_price_index, entry_index, planned_label_end_index, and planned_label_end_session. Usable rows require preserved feature_status, joint_feature_status, strategy_source_status, and execution_status all qualified. Decision timestamp is decision_timestamp; preserved decision_time must agree if present. availability_floor, entry_session, and preserved exit_session remain bound.
- Learned forecasts: map event_id to full forecast row for ONE family spanning all five test years. Every supplied forecast must match event_id, cik and prepared_row_sha256 from the model adapter; mismatched or absent bindings refuse the account attempt. Usable rows have status="predicted" and corrected=[return_5, downside_5]. Preserve raw, uncalibrated, reasons, model attempt/year and any calibration identity in each row. Missing or unavailable rows abstain with retained reasons. Invalid return <= -1 or downside < 0 abstains.
- forecast_identity: immutable identity of that entire family/cross-fold forecast artifact, stable across all account chunks and years. It must not change at refit boundaries. Controls reject supplied forecasts.
- Default evaluation starts at the completed session immediately preceding the first 2021 official session, with no prior holdings, and ends 2026-01-16. New entries are confined by 09:00 ET decision year to 2021-2025. Explicit paired first/last bounds exist only for synthetic fixtures and label the output synthetic_interval_override=true. Actual comparisons must omit both.

event_rankings(market, events, recipe, forecasts=None) returns (ranking, counts, lookup, dispositions). This function only reads calendar/index/causal feature fields. No future prices or labels determine candidate eligibility. Same-symbol/same-decision qualified events are explicitly refused before recipe filtering, preserving the unresolved original-event collision rather than overwriting or choosing a favorable event. The root must check actual terminal clocks and record any unresolved collision as an attempt failure.

## Execution and evidence

The adapter calls frontier.short_horizon_study._simulate_daily one session at a time and retains one continuous state across years. It uses _summarize for unchanged cash, trade, exposure and period calculations. Learned arms delegate sizing, ranking and fill utility to ConditionalPolicy with dollar ranking. A thin audit wrapper requests full planner decisions; it does not reimplement or change utility.

Original fee-inclusive reservations and original quantities are recorded once. At the hypothetical close fill, quantity is capped against the original reservation and may only decrease; the engine still enforces NAV, settled cash, positions and frozen forecast utility. No reranking or replacements occur at fill. Independent five-session exits, held positions and pending settlements survive annual model changes or unavailable folds. Controls continue through unavailable learned folds. The 30% drawdown is a qualification criterion, not a newly invented trading halt.

The output retains every event disposition. Its prepared_event_sha256 binds the entire original prepared row as UTF-8 JSON with sorted keys, compact separators, allow_nan=False and default ensure_ascii=True; full prepared-event/source artifacts must remain bound by the enclosing experiment definition. It also explicitly preserves registry_acceptance_utc, acceptance_et, source_input, source_sha256 and industry_header_source where present. Every intent and trade retains the event identity, original clocks, S/Q, original reservation and quantity. Learned intents retain full forecast records and reference projections. policy_audit contains engine selection summaries, every conditional fill check, and full planner candidate/fee/utility/order decisions including event IDs. Selection detail records are appended after the engine audit rows and should be ordered by their explicit session/index fields when reviewing chronology. daily_state retains held/pending positions and receivables. Required future entry/mark gaps invalidate the account and preserve its ledger prefix and unresolved state.

period_returns.weekly retains all complete-account calendar weeks, including idle and losing weeks, with initialization/entry/tail membership. A week crossing the entry/tail boundary is labelled mixed with both roles. weekly_objective reports exact target-hit numerators/denominators/fractions, median/worst week and longest losing streak. Incomplete accounts do not acquire a profitable prefix summary or target-hit ratio. The enclosing study must retain all failures and supply remaining source/issuer/year/model diagnostic reporting.

## Qualification limits

Tests use synthetic event/features/forecasts and saved official session calendars, not economic model fits. Passing these tests establishes adapter behavior, not profitable forecasts, corporate-action completeness, broker fills or live readiness. Shared modules and all earlier frozen adapters remain unchanged. The final experiment definition must bind this adapter, the cost/engine/policy dependency identities, the terminal event artifact, complete forecast artifacts and all input sources before any actual account runs.


Independent cross-review identified a shifted-forecast mapping could attach an existing forecast to a different event. Mandatory event_id/CIK/full-prepared-row digest comparison now refuses that mismatch. Tests include wrong ID, wrong CIK, wrong row digest and missing binding. No actual historical account was exposed to the earlier implementation.

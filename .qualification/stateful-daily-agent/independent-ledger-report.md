# Independent real replay audit — 2026-09-28

The two declared one-year replays passed an independent arithmetic/source audit. Neither result qualifies the strategy for promotion. The proportional scenario lost money before and after costs; the current Moomoo tariff scenario made the small-order problem substantially worse.

| Frozen five-session account | Proportional 40 bps | Moomoo Canada US tariff + 40 bps |
|---|---:|---:|
| Starting USD | 2,000 | 2,000 |
| Ending USD | 1,873.880315 | 891.247569 |
| Return | -6.305984% | -55.437622% |
| Maximum drawdown | 17.394677% | 56.073995% |
| Completed trades | 248 | 247 |
| Total declared fees | 29.286518 | 1,008.026073 |
| Gross P&L before declared fees | -96.833167 | -100.726358 |
| Mean exposure | 7.147832% | 7.243996% |
| Median entry notional | 22.40 | 15.283 |
| Profitable weeks / observed weeks | 16 / 53 | 3 / 53 |
| Profitable months / observed months | 4 / 13 | 1 / 13 |

The period is 2025-09-17 through 2026-09-18, with entry at the next close and five-session holds. The first and last weekly/monthly periods can be partial. The same-window whole-share SPY reference bought three shares at the 2025-09-18 close, retained unused cash and charged entry/terminal-exit scenario costs: +15.750757% proportional and +15.549257% Moomoo. This benchmark is a declared reference, not a matched short-term strategy or a recommendation.

## What was independently checked

`independent_replay_audit.py` imports no Frontier production module and does not refit or reconstruct the model feature universe. It reads each journal under a SQLite read transaction, verifies SQLite integrity, immutable chunk payload hashes, prior-state hashes, exact cursors, policy/scope/model/source/code identities, and saved training/calibration target cutoffs. It reconstructs the US settlement-index digest with an independent explicit banking-holiday implementation plus the shared exchange-calendar dependency.

Both accounts contain 253 recorded sessions and 701,318 saved forecast rows. Every recorded score was independently recomputed from its six outputs. This verifies saved score arithmetic, not forecast quality or causal feature construction.

The audit independently reads and hashes raw JSON for executed and chunk-boundary pending names plus SPY: 182 sources for proportional and 184 for Moomoo. Reported provider split ratios reconstruct nominal entry prices; provider adjusted closes reconstruct synthetic exit proceeds and daily held marks. Every recorded trade, held boundary and pending reservation satisfies whole-entry-share sizing, positive-score next-close timing, five-session duration, five-position capacity, entry 20% budget, signal ATR budget and settlement funding checks.

Daily cash, settled cash, receivables, equity, fee totals, position states and reservations independently reconcile. Maximum absolute curve differences are floating arithmetic only: approximately 2.05e-12 USD proportional and 7.96e-13 USD Moomoo. Proportional friction was calculated directly. Moomoo commission, platform and sell SEC fee components were calculated independently using Decimal and the declared ceiling-to-cent convention. All weekly/monthly returns compound to the final account return. Drawdown includes starting capital.

The completed proportional journal has 15 chunks and Moomoo has 13. Both end flat with no pending orders. The original first proportional chunk remains unchanged; it had five held positions and five pending reservations. Parent-run exact resumed-versus-one-shot verification is a separate check and passed after canonical JSON comparison. Its first qualification checker reported a JSON list versus native tuple representation mismatch in state after all four curves matched; that unsuccessful checker attempt is preserved. The corrected check matched all curves, trades, final state and activity exactly, with fee aggregation differing by 1.066e-14 USD. Repeating the completed replay retained the same 15 chunks and 248 trades.

## What the economics show

Average modeled Moomoo round-trip cost is USD4.0811 on these very small orders. Median total fees are 26.4687% of an entry notional. Cash, sizing and different entries compound these fees over time, so subtracting one scenario's fees from the other's ending equity is not a valid corrected counterfactual. Both scenarios also have negative gross aggregate trade P&L. Lower transaction costs alone do not demonstrate a usable strategy edge.

## Limits and unfinished qualification

- Raw-provider price agreement is not corporate-action completeness, issuer identity or fill validation. Three proportional trades cross reported reverse splits: WNW, EZGO and PAVS. Moomoo has those three plus INLF. Original whole-share quantities and synthetic adjusted-value exits are not reconciled post-action broker quantities; fee brackets/per-share fees can be affected.
- Neither account executed AIXI. That does not eliminate the independently identified AIXI source-continuity defect from later calibration data or universe forecasts. See `docs/aixi-source-continuity.md`; this audit does not repair any source or portfolio.
- Price checks cover executed and chunk-boundary pending names. The audit does not assert complete all-symbol eligibility, optimal ranking or causal feature generation. Training/source/model construction has separate verification.
- These are current-member, current-adjusted-vintage, reused historical accounts, not untouched holdouts. The cost comparison is a current-tariff counterfactual; unverified charges, FX, subscriptions, taxes and actual slippage remain excluded.
- Atomic synthetic close fills do not establish broker partial-fill handling, reconciliation, actual execution or a daily paper migration. No production or paper account file was opened or changed by this audit.
- The published proportional summary independently matches all 53 weekly and 13 monthly returns, ending equity, return, drawdown, fees, completed trades, holding duration, aggregate P&L, win rate, mean exposure and drawdown duration. Moomoo has independent metrics but no separately published summary comparison in this audit.

## Evidence

- `independent_replay_audit.py` — reproducible independent audit.
- `independent-ledger-audit-35ec05080c68404ebd826ceb6b3ef015-1261.json` — complete proportional audit and exact metrics/periods/source hashes.
- `independent-ledger-audit-29af0cd2df57424094a6969268ade8e5-1261.json` — complete Moomoo audit.
- `independent-ledger-audit-35ec05080c68404ebd826ceb6b3ef015.json` — retained original partial 21-session snapshot.
- `independent-economic-diagnostics.json` — fee burden, gross outcomes and largest winning/losing trades, with all trades still retained in the journals.

## Additional review finding

A separate synthetic qualification replay confirms that cost inputs `40` and `40.0` compare equal as Python dictionaries but serialize differently in the engine state scope. API-default integer 40 followed by CLI-equivalent float 40.0 rejects resume; resuming with integer 40 succeeds. No real journal was altered. Preserve existing immutable identities, normalize numeric cost serialization for a separately versioned implementation, and add both API-to-CLI and CLI-to-API regression checks. `cost-type-resume-repro.json` and the retained synthetic journal record the failed invocation and successful control. This operational issue does not change the arithmetic of the two completed historical accounts.

The Moomoo audit also encountered 19 actual synthetic exits where the modeled fee exceeded sale proceeds; each shortfall reconciles as an immediate settled-cash debit. No negative settlement receivables or borrowing were used. These fees can cause a trade loss above 100% of a very small entry notional.

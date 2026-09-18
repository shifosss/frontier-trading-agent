# Execution ledger — Frontier Research

Updated September 18, 2026. The user delegated implementation, testing, and
validation. Routine work continues under that authorization; milestone progress
does not require another approval. New spending or broker authority remains a
separate decision.

## Delivered local workflow

| Area | Current evidence | Remaining boundary |
| --- | --- | --- |
| Engine | Actual Nautilus Trader 1.231.0 fills, one USD/CAD cash account, native fees, dated FX, calendar-aware next-opening timing, independent accounting tests. | Cash dividends with known payment dates are tested. Splits remain unsupported and rejected. Inferred opening quotes do not qualify market microstructure or broker execution. |
| Scanner | 41 declared instruments, five years of daily adjusted histories, fixed stock ranking, native cash sizing, saved cohorts and benchmark/cost comparisons. | Current-universe retrospective diagnostics, not a live strategy or account reconciliation. |
| Data and registry | Immutable manifests, source/content identities, retained CSV/Parquet inputs, point-in-time filtering, failed run persistence, evaluation-access records. | Historical availability is often inferred; access overlap is scoped to an immutable dataset identity, not all provider aliases or vintages. |
| Daily research | Retained 100-bar SPY and XIU sources; a separately identified June 22–September 17 window; cash/passive/trend/reversion and declared cost stress. | The full sample now replays on an enriched immutable dataset with dividend payment dates and prior FX. Canadian action coverage remains unknown; results remain exploratory. |
| US hourly data | 434 retained Longbridge SPY bars across 62 sessions, converted to official endpoints with partial final hours and cross-source comparisons preserved. | Canadian hourly coverage and a complete production data lane remain unqualified. |
| Model campaigns | Two actual two-call campaigns through the existing ChatGPT Codex login; typed templates, genuine replay feedback, recorded prompts/output/usage and all attempts. | No untouched holdout, alpha proof, open-ended generated code, broad autonomous research factory, or measured multi-agent advantage. |
| Workstation and CLI | React/FastAPI UI, local launcher, saved studies/campaigns, source helpers, reports, inspection and deterministic replay commands. | Local operation is not a continuously available deployment. |
| Frozen observation | Immutable completed-run configuration, compatible appended data, as-of decisions, duplicate protection, and historical/prospective classification. | No broker orders, inferred future fills, accumulated forward performance claim, or automatic strategy promotion. |

The runnable package is `frontier` under `src/frontier`; the original design's
`trading_agent` paths were planning placeholders. The broader roadmap is partially
implemented, not fully accepted.

## Accounting and evidence decisions

- Nautilus owns the execution ledger. A narrow internal venue mapping consolidates
  both currencies into one simulated account while outputs retain original listing
  identities and official calendars. This avoids duplicated starting capital.
- Signals use only bars and revisions available by the decision time. Close-based
  decisions wait for an eligible opening strictly after availability. Pending final
  intents remain unfilled, and positions are not liquidated for free.
- Funding remains in native currency. Fees and slippage are separate, and valuation
  uses available dated FX without assuming a 1.0 rate or inventing conversion trades.
- Cash-dividend entitlements and payments are separate: receivables contribute to NAV
  but cannot fund orders. Unsupported splits still block replay. Unknown action
  coverage requires explicit opt-in and leaves total return unavailable.
- Fixed and model-driven campaigns expose their full research intervals. Candidate
  configurations and costs are frozen; rejected, duplicate, and failed attempts count.
  Short historical returns do not authorize promotion or deployment.
- Existing ChatGPT access is a verified Codex CLI provider route, not an assumed API
  key. Tokens and runtime are recorded; a dollar charge is not inferred from usage.

## External access and deployment

Working Codex connectors and unattended standalone processes have different access
boundaries. Existing connectors supplied Alpha Vantage daily snapshots, Longbridge
SPY hourly observations, and Alpaca action evidence. The public Bank of Canada
helper has also fetched and reused a verified local capture.

The Longbridge standalone CLI reported an expired token on September 18. Manual
user authentication is required before its unattended history helper can operate.
No automatic login, credential extraction, broker account mutation, or order was
performed. A successful app connector call does not clear this standalone dependency.

A Codex weekday 17:15 Toronto heartbeat now refreshes the research scanner and
notifies only on meaningful changes or failures. No broker-paper service was
installed. An always-on host, restart recovery, forward outcome tracking, and broker
reconciliation remain additional work. LEAN was inspected at a pinned source revision; its local
build was blocked by the available SDK version and was not represented as execution.

## Reproduction and validation

[README](../README.md) contains the current quickstart and CLI examples.
[Validation](validation.md) records the final consolidated checks and their exact
scope; task reports describe the evidence produced at each implementation stage.
Do not add their intermediate test counts together or treat older artifact IDs as
proof against a later financial-code identity.

- [Ponytail full-mode quality review](code-quality-review.md)
- [Engine qualification](engine-qualification.md)
- [Data foundation](tasks/02-data-evidence-report.md)
- [Replay and fixed campaigns](tasks/03-replay-report.md)
- [Workstation](tasks/04-interface-report.md)
- [Model research and observations](tasks/05-research-report.md)
- [Existing source integration](tasks/06-sources-report.md)

Next priorities are complete action coverage/accounting, Canadian hourly data,
longer point-in-time history, nested chronological evaluation, advanced baselines,
and honest prospective outcome collection. The workstation can be useful while
those broader acceptance conditions remain open.

The [scanner study](scanner-study.md) records the actual repaired study and the
CAD600–800 funding scenarios. [Broker readiness](active-account-readiness.md) checks
Wealthsimple/moomoo fees, options permissions and Canadian taxable records against
current official sources. Neither document establishes live profitability.

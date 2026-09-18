# Design Review

Date: 2026-09-18

Status: initial research reviews and independent document reviews incorporated. No implementation has been run.

Three independent review assignments examined research validity, execution-stack suitability, and product/architecture failure modes. The primary agent compared their recommendations with current primary documentation and revised the proposed design.

## Findings incorporated

| Finding | Severity for this design | Resolution |
| --- | --- | --- |
| Latest Nautilus examples describe a 2.x release candidate while default installation may resolve stable 1.x | Integration correctness | Require immutable versions and a compatibility demonstration before accepting engine APIs. |
| Nautilus corporate-action support is incomplete for the intended equity/ETF track | Accounting correctness | Compare with LEAN's action handling using independently calculated fixtures; qualify a primary engine before adoption. |
| LEAN's standard IB equity path assumes USA, while the user requires Canada too | Market coverage | Make Canadian equity identity, calendars, actions, CAD accounting, and contract routing mandatory qualification cases; custom data is not trading support. |
| Official LEAN IB plugin has a separate subscription check | Existing/free-only constraint | Engine qualification includes connector licensing. Do not infer free connectivity from open-source engine availability or bypass the check. |
| Daily reference FX can leak a later publication or be mistaken for an executable quote | Temporal/accounting integrity | Separate reference valuation from actual FX trades and honor source publication time. |
| Point-in-time retrieval does not remove historical outcomes memorized by an LLM | Scientific validity | Label historical language predictions exploratory and require prospective frozen-version evidence for stronger claims. |
| Statistical correction can coexist with leaked inputs | Scientific validity | Separate temporal-integrity tests from search-aware statistics; neither stands in for the other. |
| A supposedly untouched test can be reused through campaign/agent restarts | Scientific validity | Global access ledger records overlapping periods and dataset lineage. Exposure persists across campaign names. |
| Independent agents can agree on the same contaminated evidence | Scientific validity and cost | Give reviewers raw artifacts, enforce data contracts, and measure multi-agent benefit against a simpler workflow. |
| Broker paper, local simulation, historical results, and real fills are different evidence | Product correctness | Explicit mode/account identifiers and separate interface labels; reconciliation uses actual broker observations. |
| Multiple workers writing shared analytical files creates ownership ambiguity | Operational correctness | Workers produce isolated artifacts; coordinator commits registry state; Parquet/DuckDB serve analytical reads. |
| An unrestricted self-improving strategy can reset its identity and track record | Attribution | Frozen deployed versions, separate challenger records, explicit promotion policy. |
| Free financial data and user chat connectors are not guaranteed standalone service inputs | Feasibility | Record provider access and quality; no backend credential/entitlement is presumed; data access is an explicit milestone dependency. |
| Host has .NET 9.0.310 and Docker's Linux daemon is not reachable | Runtime feasibility | Qualify an isolated engine runtime in M1; do not assume LEAN's current .NET 10 requirement or Docker readiness is already satisfied. |
| A polished dashboard may precede any working research/execution path | Scope | M1 demonstrates real replay and accounting artifacts; dashboard consumes established result contracts later. |
| Replayed model output could be counted as autonomous-research completion | Acceptance validity | M3 requires a real available model creating a new executable proposal and consuming evaluation feedback; fixture replay only verifies orchestration. |
| Held-out results can reach researchers through reviewers, summaries, or shared memory | Scientific validity | Transitive information boundary across all candidate-influencing roles and a canary-based information-flow test. |
| Serial milestones delay prospective observations behind optional sophisticated models | Evidence collection | Branch M5a frozen baseline observation from M2; advanced models and UI work proceed independently. |
| Initial comparison profile leaves borrowing/precision/fill behavior implicit | Benchmark validity | Declare long-only, unlevered, whole-share, exposure-capped research/paper defaults and next-eligible-event fills. |
| Reset/stitching fold portfolios can manufacture a continuous track record | Accounting validity | Continuous walk-forward account state; separate independently reset fold diagnostics; position-across-boundary test. |
| Repeated paper-performance peeking creates a new selection process | Scientific validity | Predeclared evaluation horizon/schedule or explicit sequential-testing policy; operational monitoring remains continuous. |
| Parameter-only trial counts omit search over the rest of the pipeline | Scientific validity | Count universe, horizon, preprocessing, features, model, allocator, ensemble, and execution-filter variants. |
| Broker paper costs may be described as real execution validation | Claim accuracy | Label simulator/account observations, compare with contemporaneous quotes, reserve actual execution-cost claims for actual fills. |

## Alternatives reviewed

- **Copy the article's large bot organization:** understandable metaphor but no demonstrated benefit from that number of agents. Adopt job roles where they improve measured outcomes.
- **Direct LLM-to-broker trading:** flexible, but weak reproducibility and attribution. Keep model output upstream of deterministic portfolio/execution contracts.
- **Nautilus for everything:** strong candidate for several markets; corporate-action handling needs qualification. Conversely, LEAN's US support does not establish Canadian support. Compare both against the complete mandate.
- **Build a universal simulator:** high control and high maintenance cost. Reuse an established engine and independently test the specific semantics we depend on.
- **Adopt an entire quant-agent framework:** useful comparator; its data/model/evaluation assumptions should not silently define our evidence standard.
- **Begin with reinforcement learning or a foundation-model ensemble:** include as later challengers. Simulator fidelity and comparative evidence must precede adoption.
- **Start with distributed services and hundreds of workers:** adds costs before throughput is measured. Begin with a local modular application and isolated workers.

## Primary-agent self-review

- The ambitious end state is preserved while milestones produce functioning vertical slices.
- US/Canada stocks and ETFs, hours-to-weeks, and no new spending without approval are confirmed user preferences; reversible engineering defaults remain separate.
- Financial and performance claims require evidence rather than product naming.
- Paid services, backend credentials, and a live mandate are not assumed.
- Failure handling is tied to real market/data/execution contracts; speculative defensive wrappers are excluded.
- Existing engine functionality is evaluated with mandatory US/Canada, actions, FX, and licensing criteria rather than assumed from feature lists.
- Historical selection and LLM contamination are addressed separately.
- Development and later 24/7 runtime are distinguished.
- Every major architecture choice records an alternative and revisit condition.
- Approval is consolidated at architecture/mandate level; routine work is autonomous.

## Remaining uncertainties and how they are resolved

| Uncertainty | Resolution point | Work that can proceed independently |
| --- | --- | --- |
| Working engine/runtime, exact revision, and complete Canadian equity semantics | First M1 qualification task | Data/evidence schema design and independently worked fixtures. |
| Suitable historical data entitlement | M2 connector selection | M1 engine and fixture verification. |
| Actual broker/account, connector entitlement, and operational constraints | M5b account setup | Historical research, M5a local forward observation, dashboard. |
| Economically useful alpha | Controlled evaluation and prospective observation | Engineering, benchmark publication, negative-result learning. |

The principal project risk is building a useful laboratory that discovers no deployable edge. The response is a low-cost complete experiment loop with falsifiable comparisons and explicit stop/continue criteria, rather than claiming that additional model sophistication guarantees returns.

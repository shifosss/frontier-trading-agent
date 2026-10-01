# Frontier Trading Agent: owner context and governing decisions

Snapshot: October 1, 2026. This records the owner's instructions and decisions preserved in this session and the repository. It is a handover of recorded decisions, implementation, evidence and unresolved questions; it cannot recover undocumented conversations or establish missing source facts.

## Purpose and current conclusion

Frontier is a local research workstation and developing automated trading agent for a Canadian owner. The intended product scans a broad stock universe, evaluates multiple strategies, makes cash-funded trading decisions, tracks positions and orders, and eventually operates a qualified automated policy. The owner wants an effective, easy-to-use system and authorizes extensive historical research and implementation without repeated routine approval.

The project has implemented substantial research, data, model, accounting, interface and paper-operation infrastructure. **No historical strategy has been qualified for promotion as a profitable automated trading policy.** The running Alpaca paper operator is a separately authorized baseline. Software tests, accurate arithmetic, a positive exploratory path, and paper fills are different kinds of evidence; none establishes reliable live profits.

The latest completed study is the 100-issuer cash-backed earnings comparison of September 29. The next proposed research was disclosure novelty/timing using cached SEC metadata, but the owner requested this handover before continuation. **No original 8-K matching audit, new financial capture, new fit, or new economic test was run during this documentation task.**

## Owner mandate and its evolution

| Subject | Governing decision | Recorded reason or implication |
|---|---|---|
| Product | Build a powerful and usable automated trading agent, with autonomous research/testing and meaningful quality review | The owner wants a working result, rather than a research article explanation alone |
| Research inspiration | Start from RohOnChain's X article at `https://x.com/RohOnChain/article/2097303933081489605` | The article is an inspiration; its claims are not evidence that Frontier earns money |
| Markets | US stocks/ETFs and Canadian stocks/ETFs; broader hypotheses may include cash-funded options | Broad scope avoids treating the original 41-symbol starter list as the final opportunity set |
| Cadence | Hourly/daily decisions, intraday to approximately one-week individual-stock holdings | The owner rejected treating long ETF-style holdings as fulfillment of active trading |
| Evaluation window | Use extensive multi-year historical observations of repeated short trades | A five-year test can be useful when it contains many short trades; it must not be confused with holding one portfolio unchanged for five years |
| Strategies | Broader technical rules, learned models, multiple outputs and combinations are authorized | Added complexity is a hypothesis to test, not a quality metric or proof of advantage |
| Research capital | USD10,000 primary simulation; USD2,000 comparison | Larger balance tests affordability/fee effects. Both are simulated balances, not broker-reconciled funds |
| Return target | At least 5%, preferably 10–15%, per week on the entire account after costs | Aspirational research target. No guaranteed minimum, no selective active-week reporting, and no lowering risk constraints to hit it |
| Risk | Cash only, no borrowing/margin use; maximum 30% account drawdown constraint | A qualification limit must be distinguished from an automatic liquidation rule. Gap overshoot and unavailable intraday loss information remain visible |
| Funding | Mainly CAD; USD conversion is acceptable, with a stated preference for Norbert's gambit | No transfer is automated or authorized. Simulations keep FX/funding assumptions explicit |
| Contributions | Approximately CAD600–800 monthly, with CAD700 used illustratively | Not an initial cash declaration and not a broker balance |
| Account | Taxable/nonregistered | Taxes and funding costs are separate from the historical execution-cost scenarios; account-specific tax outcomes are not established |
| Brokers/access | Wealthsimple is the current active broker; Moomoo cash account also exists. Owner mentioned Longbridge, Alpaca and earlier ChatGPT connectors | Existing access may be used for authorized research; ChatGPT connector availability does not automatically imply Codex or brokerage execution access |
| Spending | Existing authorized access and free resources only; ask before new spending | No new subscriptions, hosting purchases or paid data were authorized |
| ETF reserves | Keep the regular ETF portfolios separate from active capital | Existing savings preferences should not be silently repurposed as active-trading funds |
| Automation | Routine reversible development/research/testing need no repeated approval | Explicit live deployment, real orders, options orders, spending and transfers remain outside the current authority |
| Paper authority | Existing USD100,000 Alpaca PAPER account only | Frozen paper transport, code identity, universe, durable order IDs and reconciliation govern operations |
| Historical priority | Improve strategies using existing historical evidence before relying on future shadow observations | Prospective observations supplement historical work; they are not a reason to stop useful historical development |
| Code quality | Apply Ponytail at standard/full level and review material implementations | Prefer reuse and readable code; avoid cosmetic churn, unnecessary abstractions and duplicated research engines |
| October 1 priority | Document all recorded decisions and prepare private GitHub publication before new research | A person or new agent should understand and continue the project without this conversation |

### Reserved ETF portfolios

The owner reported approximately CAD1,200 in XGRO, outside this project's active-trading scope. A separate approximately CAD1,000 regular portfolio was described as 70% equities, 22% bonds, 8% gold. Within the equity allocation: XEQT54%, VDY12%, QQC4%, Canadian CHPS1%, VTV6%, VFV6%, SPMO8%, SMH1%, IXJ5%, XBI3%. These are the owner's described preferences, not a current reconciled securities ledger. Limited modifications preserving those preferences were allowed; no actual modification or transfer is established here. This allocation must not be counted as available active-trading cash.

### Scope counts and interpretation

The owner's rough market-size estimates were a request for broad coverage, not authoritative listing counts. The project records requested, discovered, usable, eligible and failed instruments separately. A present-day listing universe is not the historical population, and incomplete Canadian prices or delisted histories cannot be cured by quietly replacing names. An 11-stock operational paper universe, the old 41-symbol starter scanner, and the broad historical discovery universe serve different purposes.

## Decision authority and approval boundaries

Proceed autonomously with reversible local development, read-only broker/data diagnostics, historical experiments within declared limits, meaningful tests and code reviews. Use a predeclared hypothesis and fixed sample/cost choices before reading economic outcomes. Keep each attempt, failure, warning and excluded denominator.

Only the fixed Alpaca **paper** transport may submit the currently authorized baseline's simulated orders. Never substitute a live endpoint, place real securities or option orders, transfer funds, buy services, authenticate the owner into a broker, change the active eleven-stock paper universe, or automatically promote a historical winner. A new operational migration requires a separately qualified policy and appropriate authority.

Uncertain submissions, rejected exits, unsupported actions, code drift and unexplained funds or holdings require reconciliation. Preserve journals and durable identifiers; never erase the journal or blindly resubmit. Restart the initialized paper watcher once only after verifying absent owned processes, a free lock, frozen identity and reconcilable journal. Research workers and paper workers have independent locks and lifecycle.

A request to pause the goal stops research/development and scheduled research while retaining evidence. Separately authorized paper operations remain separate unless the owner explicitly stops them. The owner later resumed the goal. The present documentation request defers new research until the handover is ready; it does not authorize a live trading transition.

## Key decision register

These are the recorded project-level choices. Detailed technical and academic registers follow elsewhere in this handbook.

| ID | Decision | Reason | Evidence/status |
|---|---|---|---|
| OWN-001 | Treat autonomous trading as the product objective | Owner explicitly redirected from article-based research to an automated agent | Owner instructions; product goal, unfinished |
| OWN-002 | Preserve historical evidence ahead of new forward observation | Historical experiments can reject/refine hypotheses now | Owner instructions; implemented research factory |
| OWN-003 | Keep daily short-hold and intraday studies separate from legacy long-hold/paper baselines | Changing a global horizon or watcher frequency does not implement a new trading cadence | `docs/trading-cadence.md`; implemented daily lane |
| OWN-004 | Evaluate whole-account weekly outcomes including idle and losing weeks | Avoid turning sparse profitable trades into a misleading weekly return promise | `docs/capital-and-return-objective.md`; implemented experiment reporting |
| OWN-005 | Compare USD10,000 and USD2,000 without claiming broker funds exist | Affordability, fixed fees and risk sizing depend on account scale | Owner instructions and earnings/ETF definitions |
| OWN-006 | Keep CAD risk and ETF reserves separate from USD active simulation | Conversion and risk base are different from quote currency | `config/mandate.json`, funding study |
| OWN-007 | Retain all failed variants and source exclusions | Selecting only successful paths creates hindsight bias | Every frozen comparison; no promoted winner |
| OWN-008 | Use training-only choices, explicit chronology and purged labels | Prevent information from future outcomes entering decisions | Multi-model, conditional and earnings specifications |
| OWN-009 | Test richer models without requiring a simple profitable baseline first | Owner authorized complexity; simple baselines remain controls | Multi-model/earnings comparisons complete; complex models did not establish an edge |
| OWN-010 | Preserve immutable code/source/policy identities | A changed model or journal is a different experiment or operation | Model artifacts, research attempts, paper seven-file identity |
| OWN-011 | Distinguish fees, quoted spreads and realized fills | A quote sample is not an execution guarantee; fee assumptions must not be chosen from profits | Cost-evidence and broker-feasibility documents |
| OWN-012 | Keep free/existing-access spending boundary | Owner explicitly withheld new spending authority | Premium access failures retained, no purchases |
| OWN-013 | Use a private repository for publication | Owner will create it and supply its URL | Private `shifosss/frontier-trading-agent` provided and verified October1 |
| OWN-014 | Document actual reasoning and mark gaps rather than invent it | New readers need trustworthy recorded decisions, not retrospective certainty | This handover; unknown rationale remains unknown |

## Chronological navigation

The project grew rapidly from September 18 through September 29, 2026. Git preserves the sequence: engine qualification and immutable datasets; bounded model-provider access; local workstation; Ponytail review; scanner/dividends and CAD/USD funding; paper operator; broad current-universe research; historical-first daily short-hold research; richer model tournament; saved daily model bridge; persistent daily rehearsal; strategy interactions, timing and conditional forecasts; calibration shrinkage; actual-minute intraday; original-filing pilot; larger-capital mandate; ETF reversal/options access; 100-issuer cash-backed earnings preparation and completed results. A new reader should read the current reconciled handbook before the older dated plans. Older documents retain the assumptions and state at their time; they do not override newer results.

Git history is retained, not rewritten. Its commit identities allow a reader to recover earlier code and explanations. Full recorded decision rationales and underlying definitions are referenced through the detailed research and technical sections and the publication inventory.

## Glossary for a new reader

- **Requested/discovered/usable/eligible**: distinct denominators. A downloaded series need not have the required causal history, complete labels or tradable decision inputs.
- **Capture**: source acquisition, not an economic strategy test.
- **Attempt/definition**: a durable run record and its declared immutable inputs/settings.
- **Current-member history**: today's eligible listings studied backward; it omits some historical delisted/changed members and carries survivorship limits.
- **Point-in-time**: only facts public and usable at a stated historical decision time. Revised vendor history is not automatically point-in-time evidence.
- **Purging**: remove fitting/calibration labels whose outcome windows reach the next chronological partition.
- **Calibration**: estimate forecast correction/weights/bins using a separate earlier period. It cannot use the later test period.
- **Head**: a model output such as a horizon return or downside. Multiple outputs do not imply transformer attention.
- **Next-close**: an explicitly declared later-close simulation timing convention; distinct from earlier opens and intraday quotes.
- **Reservation**: money committed to an immutable intended order; it cannot be reused before resolution.
- **Settled cash**: proceeds available only after the applicable dated settlement schedule, distinct from marked equity and broker margin buying power.
- **Paper**: simulated broker orders/holdings in the fixed Alpaca paper account. They are not real investments or demonstrated live fills.
- **Shadow/prospective**: observations recorded after the policy is fixed; separate from historical fitting and paper-account operations.
- **Qualified**: passed the specific stated evidence/engineering/economic criteria. Source qualification, arithmetic verification and profitable strategy qualification are separate.
- **Promotion**: adopting a research candidate into an operational policy. No current historical strategy has been automatically promoted.
- **Drawdown**: decline from a previous account-equity peak. Daily-close observed drawdown does not bound intraday loss or gaps.
- **S/Q**: original income-seasonality and cash-backing features in the filing studies; exact formulas, contexts and failure rules are in the research section.
- **CIK/SIC**: SEC issuer identity / industry classification. Original matching filer-header SIC and today's profile SIC are different evidence.
- **Corporate action**: split, dividend, merger, share conversion or other issuer event requiring price/share/cash/time treatment.
- **Provenance**: original source, response bytes, hash, retrieval/publication times and mappings that let a reader trace an observation.

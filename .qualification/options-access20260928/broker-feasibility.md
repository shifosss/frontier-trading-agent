# Canadian broker feasibility: cash-funded options structures

Public-source review dated September28,2026 (America/Toronto). Scope: current Wealthsimple and Moomoo Financial Canada rules, funding and published tariffs. No authentication, broker orders, source probes, paid services or changes to the frozen studies. These are operational facts and research implications, not trade recommendations.

**Finding:** A fully paid vertical debit spread is not a supported taxable cash-account workaround at either broker under their published Canadian account rules. A margin-account type and actual borrowing are different things, but the existing mandate does not authorize an account conversion. Small debit size also does not eliminate assignment-related stock obligations. The proposed 1% premium budget remains unchanged.

## Account eligibility

| Structure | Wealthsimple taxable non-margin account | Moomoo Canada individual cash account | Margin-account route |
|---|---|---|---|
| Bought call/put | Available subject to options approval. | US options are available; account approval remains individual. | Neither account label establishes permission to borrow. |
| Fully paid vertical debit spread | Not supported; requires margin account with USD accounts enabled. | Not supported: the official Canadian strategy table says Vertical: margin Yes; cash/RRSP/TFSA No. | Both offer verticals in margin accounts; Wealthsimple says debit spreads require payment of the debit without additional collateral. |
| Covered call / covered stock | Covered calls require a registered or non-registered margin account. | Covered Stock is explicitly supported. The no-borrowing interpretation here is a long-stock covered call, not a covered put that shorts stock. | Available subject to approval and required underlying shares. |
| Equity secured put | Not offered in taxable non-margin accounts. Wealthsimple lists registered and non-registered margin accounts. | **Unresolved for this exact cash-account type.** Canadian educational pages describe cash-secured puts, but the precise account table does not list them; do not import US account-level rules. | Wealthsimple reserves assignment buying power; using securities-backed buying power could produce a cash debit after assignment. |
| Long straddle/strangle | Both long legs are individually available; unified multi-leg cash-account handling was not established. | Straddle and Strangle are marked Yes in the Canadian cash/RRSP/TFSA column. No short-volatility interpretation is assumed. | Account support does not establish affordable premiums or an economic edge. |

Sources: [Wealthsimple options eligibility, updated September15](https://help.wealthsimple.com/hc/en-ca/articles/9606205720987-Enable-options-trading-in-your-investing-account), [Wealthsimple spreads, updated September22](https://help.wealthsimple.com/hc/en-ca/articles/43913330243227-Trade-multi-leg-options-spreads), [covered calls, updated September16](https://help.wealthsimple.com/hc/en-ca/articles/39256656417819-Sell-a-covered-call), [secured puts, updated September2](https://help.wealthsimple.com/hc/en-ca/articles/43198629134235-Sell-a-secured-put), [Moomoo Canada account-strategy table](https://www.moomoo.com/ca/support/topic10_153), [Moomoo Canada options accounts](https://www.moomoo.com/ca/invest/options).

Wealthsimple's separate index-options page says long options and cash-secured puts can be traded in non-margin accounts. That wording concerns index options; it must not be generalized into permission for SPY ETF equity-option secured puts or spreads. Index contracts are a separate settlement/source qualification, not a silent substitute. [Wealthsimple index options](https://help.wealthsimple.com/hc/en-ca/articles/53055837436571-Trade-index-options).

## Funding, assignment and expiry

Wealthsimple requires existing shares to cover written calls:100shares per standard contract. For secured puts it reserves the assignment amount, with the premium offset in its example. Registered accounts require cash; margin accounts can instead use buying power. On assignment, insufficient cash in a margin account becomes an interest-bearing debit. Therefore the research no-borrowing rule must reserve actual currency cash, not merely rely on a broker buying-power number. [Covered-call requirements](https://help.wealthsimple.com/hc/en-ca/articles/39256656417819-Sell-a-covered-call), [secured-put collateral and assignment](https://help.wealthsimple.com/hc/en-ca/articles/43198629134235-Sell-a-secured-put).

Wealthsimple says expiry exercise requires the cash for a call purchase or the underlying shares for a put delivery; funds/shares must be available before15:30ET. Short options may be assigned early. Its adjusted-contract restrictions reinforce the need to verify each deliverable. [Exercise and assignment](https://help.wealthsimple.com/hc/en-ca/articles/39056801816859-Understand-exercising-options-and-assignment).

A vertical's textbook payoff bound assumes its two legs remain an effective hedge. Wealthsimple's expiry-liquidation policy describes one-sided assignment and stock exposure, and explicitly acknowledges unfilled contracts may proceed through overnight exercise/assignment. Its page currently gives a15:25ET start in the schedule but14:40ET in later self-close guidance; those inconsistent operational cutoffs need clarification before implementation. We do not choose one silently or treat broker liquidation as guaranteed. [Expiry auto-liquidation](https://help.wealthsimple.com/hc/en-ca/articles/51125523358235-Understand-auto-liquidation-of-expiring-spreads-and-short-options).

Moomoo Canada's exercise FAQ likewise describes physical stock settlement, required funding, potential position liquidation or lapse, and extra near-expiry pin-risk margin. Its example shows an initially hedged spread becoming a stock short after only one leg exercises. The premium/debit paid is not enough evidence that expiry can be handled without borrowing. [Moomoo Canada exercise, delivery and settlement](https://www.moomoo.com/ca/support/topic10_143).

For the existing maximum-five-session mandate, any eventual option test would require scheduled exits before expiry plus explicit early-assignment and failed-exit handling. It must not reset the clock by accepting indefinite assigned stock, rolling to avoid recognizing a loss, or assuming both legs settle together. This is an implementation implication, not a change to the frozen research.

## Published charges relevant to a new study

| Charge | Wealthsimple | Moomoo Canada |
|---|---|---|
| US equity/ETF option trading | US$0 contract fee; platform advertises no trading commissions. | US$0.65 per contract, minimum US$1 per order. |
| Option platform charge | No separate charge identified in the cited equity-option schedule. | US$0, waived until further notice. |
| Exercise / assignment | Early exercise US$45; auto-exercise US$0; assignment $0; do-not-exercise instruction US$45. The schedule does not label the US$45 item as a per-contract tariff. | No commission or platform fee on US option exercise/assignment. |
| Published option sell-side regulatory charge | Do not add an unverified tariff beyond the applicable published schedule. | SEC:0.0000206×transaction amount, minimum US$0.01/trade, on sales. Third-party actual charges prevail under the carrying-broker note. |
| USD funding | CAD-account trading FX conversion1.5%; trading from a USD account has no trade conversion fee. Separate CAD/USD cash-conversion tiers apply. | Advertised separate FX fee $0, but the conversion rate includes a variable spread. |

Sources: [Wealthsimple current legal fee schedule](https://www.wealthsimple.com/en-ca/legal/fees/trade), [Wealthsimple equity options pricing](https://www.wealthsimple.com/en-ca/trade/options), [Moomoo Canada US fee schedule](https://www.moomoo.com/ca/support/topic10_122), [Moomoo Canada FX-rate qualification](https://www.moomoo.com/ca/invest/options).

Wealthsimple USD accounts cost CA$10/month plus applicable tax after the trial for subscribing Core clients; Premium/Generation clients can opt in free. The user's tier/subscription status is unverified, so this is not an authorized new expense. [USD-account eligibility and subscription](https://help.wealthsimple.com/hc/en-ca/articles/4414660979355-Upgrade-to-USD-accounts-for-stock-and-crypto-trading).

A one-contract Moomoo single-leg entry and later exit imply at least US$2 total broker commission before sell-side and other costs. The reviewed Canadian materials did not resolve whether a multi-leg minimum is applied separately per leg; US/Singapore rules are not evidence for Canada. Do not label a two-leg round trip US$2.60 without that clarification. These are current published charges, not verified historical tariffs or a substitute for bid/ask execution costs.

## What changes the strategy decision

A same-expiry vertical debit spread could reduce initial premium relative to the bought option by selling away part of its upside. For an illustrative verified-standard100-share contract, a0.50net debit is US$50 before costs: within aUS$100budget but above aUS$20budget. That is arithmetic, not an observed quote or recommended strike. Capped upside, two-leg spread costs and assignment add different economics. Since both brokers require a margin-account type, it remains a separately considered future route rather than a cash-account solution. [Wealthsimple debit-spread structure and collateral](https://help.wealthsimple.com/hc/en-ca/articles/43913330243227-Trade-multi-leg-options-spreads).

Covered calls and cash-secured puts also do not make expensive underlyings cheap. Using the fixture's495–505strikes and a **conditional, unverified100-share multiplier** would require US$49,500–50,500 gross assignment funding for one put, before premium offset and costs. That exceeds both research balances. Lower-priced stocks can reduce the lot commitment, but require a separate declared universe and retain stock downside; premium collected is not the maximum loss. A covered call additionally needs the whole underlying share lot. No reserved ETF holdings are used to supply that collateral.

The practical next step remains the cash-funded ETF/stock research while existing-access option contract/quote feasibility is investigated separately. Keep the1%premium cap as a proposal pending risk-design review; do not increase it, choose farther-out-of-the-money contracts, or switch account type merely to produce trades. Neither debit spreads nor covered structures establish a path to5–15%weekly whole-account returns or eliminate the30%drawdown constraint.

## Evidence limits and exact unresolved items

- Wealthsimple pages were read directly. Direct Moomoo page opens returned403“Operations too frequent”; no repeated direct fetch or alternate-client bypass was used. Moomoo findings above use the search provider's indexed text of the linked **official Canadian** pages, crawled between four days and two weeks earlier where reported. Treat live account availability as unverified, even though the published account table is explicit.
- Moomoo Canadian cash-account equity cash-secured-put eligibility remains unconfirmed. Canadian educational strategy pages are not an account-specific permission grant. The `/ca/learn/options-trading-levels` article also links a US application endpoint, so it is not used to infer Canadian options levels.
- Personal approvals, account configuration, USD funding, subscription waivers, special contract deliverables, multi-leg fee-minimum application, executable liquidity and programmatic order capability have not been inspected.
- The options fixture remains six predetermined SPY contracts over six sessions. It supplies no quotes, contract master, historical chain or actual fill evidence; this broker review does not upgrade its source qualification.
- All existing requests, probes, research definitions, capital comparisons and account results remain unchanged. No broker was contacted on the user's behalf.

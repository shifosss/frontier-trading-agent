# Automated daily/weekly trading: delivery plan and current implementation

Updated September 18, 2026. This supersedes the research-first delivery order, not the saved research evidence.

## Product outcome

The destination is software that the owner can deploy to operate a trading account: select opportunities, enter positions, manage exits, respect available cash and portfolio risk, and explain every decision. A scanner is one input. Paper execution is a validation stage on that path, not the final product.

Daily reviews and weekly entries fit the requested horizon. They do not need high-frequency infrastructure. Advanced strategies can be added through versioned decision policies; complexity must beat simpler alternatives after realistic costs, rather than become a product requirement in itself.

The confirmed mandate remains a taxable, cash-only active sleeve, approximately CAD600–800 in new monthly contributions, US/CAD stocks and ETFs, and a maximum tolerated loss of 30%. CAD-to-USD funding is acceptable. No contribution is treated as deposited until observed. XGRO and the regular ETF portfolio are separate. Options require another qualified execution/accounting lane. This implementation records a 30% sampled, cash-flow-adjusted CAD drawdown halt; it cannot guarantee that gaps or intervening moves stop at 30%.

## Decisions and reasons

| Decision | Reason and practical consequence |
| --- | --- |
| Build the portfolio operating loop next | Repeated scans and restarted backtests cannot carry holdings or manage orders. |
| Alpaca paper first | A documented paper HTTP API allows one end-to-end order lifecycle without adding a new SDK. The endpoint is fixed to paper. No live account is connected. |
| Moomoo Canada as a US execution candidate | Current v10.11 documentation explicitly supports US stocks/ETFs for the Canadian entity. The owner's actual cash-account permissions and OpenD setup still need verification. Canadian-listed securities are absent from that API capability matrix. |
| Do not automate Wealthsimple through private endpoints | Its current intended-use guidance restricts APIs/algorithms. Built-in investing automations are not a general external strategy interface. |
| Broker owns fills and holdings | No hand-written market simulator or synthetic fills are inserted into the operating journal. Nautilus remains the separate historical execution engine. |
| One process, SQLite, existing HTTP library | Durable intent IDs and OS locking handle this single-account workload. No agent framework, distributed queue, abstract adapter factory or new dependency is needed. |
| Frozen policy and code identity | A restart cannot silently reinterpret previously accepted decisions. Strategy migrations with open holdings need an explicit migration design; code edits currently stop this paper mandate. |
| Whole shares and settled USD only | Avoid assuming Moomoo Canada fractional permissions or treating Alpaca paper margin buying power as cash. This limits opportunities at a small initial balance. |
| Missing evidence produces a wait | A missing high-ranked stock must not silently promote a runner-up. A missing broker acknowledgement must not produce a duplicate submission. |

Sources checked September 18, 2026: [Alpaca paper specification](https://docs.alpaca.markets/us/docs/paper-trading), [Alpaca order lifecycle](https://docs.alpaca.markets/us/docs/working-with-orders), [Moomoo v10.11 capabilities](https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html), [Wealthsimple intended use](https://help.wealthsimple.com/hc/en-ca/articles/360056581214-Day-trading-at-Wealthsimple).

## Implemented vertical slice

`paper-init` pins a dedicated empty USD paper account and its exact simulated starting cash. `paper-cycle` reconciles saved intents against the broker, verifies cash/shares against recorded fills, marks CAD risk, submits eligible saved paper orders, and creates the next daily decision after the market closes. `paper-watch` repeats that same durable cycle every five minutes while the host stays awake. Repeated completed-session scans are skipped. Nothing starts on page load.

The first policy uses SPY's 200-session trend as an entry regime,20/60-session stock momentum normalized by volatility, and complete 201-session histories across the declared USD stock universe. Entries are decided after the week's last trading close, with buffered DAY limit orders eligible at the next opening. Holiday calendars determine the opening. Unfilled plans expire. Holdings are reviewed daily for a 50-session trend break, a 2.5-ATR decline from an observed closing-price peak, and a 20-session maximum holding period. These are close-confirmed exits, not intraday stops.

Default allocation limits are four positions, 20% per position, 80% gross exposure, one stock per exposure group, and 0.5% modeled ATR risk per entry. Existing holdings still consume exposure and slots until filled exits are observed. Expected sale proceeds cannot finance another order before conservative T+1 settlement. Settlement skips both US banking holidays and exchange holidays, including dates when stocks trade but settlement is closed. [DTCC 2026 settlement holiday schedule](https://www.dtcc.com/-/media/Files/pdf/2025/10/15/23036-25.pdf)

Orders move through separate planned, submitting, uncertain, broker-observed and terminal states. A submitted request whose response is lost is looked up by its durable client order ID. An unresolved lookup never causes blind resubmission. Partially filled shares and remaining cash reservations are preserved. A rejected exit remains a visible recovery issue. Each accepted order refreshes holdings and exposure before another order can be submitted.

External funding is recorded separately with a unique event ID. Unitized CAD performance treats that flow at its observation valuation: CAD700 falling to 490 remains a 30% loss after another 700 is added. This is sampled performance, not a reconstructed intraday capital-flow path. Unexplained cash/holdings changes block orders. A latched drawdown halt cancels outstanding buys and schedules exits; resuming an entry pause does not reset it.

The Trading desk displays saved account state, portfolio risk, daily reasons, order intents, actual paper acknowledgements and fills. Reading it never calls a broker or submits anything. The scanner, historical studies and research experiments remain accessible.

## Validation and remaining acceptance gates

Automated tests cover scheduled eligibility, partial fills, cash settlement and holidays, uncertain requests, restart/duplicate recovery, code-version changes, expired plans, missing-data retries, daily exits during an entry pause, rejected exits, fresh observation times, per-order exposure refresh, atomic peak-state persistence, and cash-flow-neutral drawdown. Browser checks cover setup and operational states across desktop/mobile widths. These are software and mocked-broker tests, not a completed broker trial or proof of profitability.

Next acceptance gates, in order:

1. Continue the paper trial activated September 18 on the owner-selected US$100,000 simulated account. Initialization, initial real reconciliation and five-minute worker startup passed; real order submission, partial/expired/canceled states, disconnects, and host restart remain to be qualified. Signal rules are shared, but this balance does not validate whole-share affordability at US$500. No credentials belong in chat.
2. Accumulate dated forward operations and compare the frozen baseline with cost-matched alternatives. Account for Alpaca paper's omitted dividends, fees, queueing and market impact separately. Zero-commission paper observations do not establish Moomoo net returns.
3. Expand the liquid, affordable universe and compare complementary strategies: trend/pullback, short-horizon mean reversion, and event-driven signals where data access supports them. Use fixed validation periods and prospective challenger decisions; do not auto-promote a backtest winner.
4. Implement and qualify Moomoo's account-specific cash execution adapter, corporate actions, actual fee schedule, account activity/funding import, and operational recovery. Add Canadian execution only through a verified supported broker route.
5. Prepare owner-operated live deployment with a reconciled account, precise capital allocation, frozen strategy versions and executable operating instructions. The assistant can develop and test the software but does not custody funds or operate a live securities account.

Options, unattended live operation, robust corporate-action accounting for the paper broker, strategy migration, larger universe validation and demonstrated net profitability remain unfinished. A small-budget policy can rationally hold cash when no affordable candidate fits; these tests do not establish an edge.

# Independent ETF account-ledger audit

All12 accounts passed. The audit rebuilt4,862 trades and27,288 daily cash/equity states, including every planned order against the frozen candidate ranking. All146 frozen inputs and15 attempt outputs matched their recorded hashes; exactly one declared12-account attempt remains. No account or frozen input was changed or rerun.

Checks cover nominal entry prices, original fee-inclusive reservations, whole-share quantities that can only decrease at fill, buy/sell fees using independent Decimal arithmetic, adjusted-notional daily marks/exits, settlement dates and receivables, held/pending state, nonnegative cash and settled balances, five-slot caps, drawdown-halt decisions and next-session liquidation instructions, weekly/monthly returns, annual compounding and CAGR.

All12 accounts recorded zero weeks at or above5%,10%or15%, with idle/losing weeks and initialization/liquidation scopes retained. Eleven lost money; the sole positive account was the USD10,000 Wealthsimple matched-count control. Both reversal recipes lost money at both capitals and brokers. This is evidence against promoting these fixed rules under the declared cost scenario, not evidence that more elaborate rules cannot work.

| Recipe | Initial USD | Broker | Trades | Net P&L USD | Modeled costs USD | Maximum drawdown | Halt session |
|---|---:|---|---:|---:|---:|---:|---|
| residual_reversal | 10000 | wealthsimple_usd | 535 | -91.04 | 1107.96 | 10.2209% | none |
| residual_reversal | 10000 | moomoo_ca_us | 534 | -2238.26 | 3119.91 | 22.6034% | none |
| residual_reversal | 2000 | wealthsimple_usd | 415 | -53.34 | 146.92 | 8.4135% | none |
| residual_reversal | 2000 | moomoo_ca_us | 132 | -598.87 | 571.76 | 30.0095% | 2019-06-26 |
| residual_reversal_trend | 10000 | wealthsimple_usd | 427 | -523.98 | 958.07 | 9.2454% | none |
| residual_reversal_trend | 10000 | moomoo_ca_us | 427 | -2142.32 | 2586.34 | 21.6500% | none |
| residual_reversal_trend | 2000 | wealthsimple_usd | 339 | -113.22 | 129.25 | 7.7970% | none |
| residual_reversal_trend | 2000 | moomoo_ca_us | 136 | -599.86 | 591.41 | 30.0233% | 2020-01-31 |
| matched_count_control | 10000 | wealthsimple_usd | 643 | 415.41 | 1368.41 | 8.9243% | none |
| matched_count_control | 10000 | moomoo_ca_us | 641 | -2218.07 | 3749.34 | 23.7953% | none |
| matched_count_control | 2000 | wealthsimple_usd | 486 | -36.42 | 174.38 | 7.4819% | none |
| matched_count_control | 2000 | moomoo_ca_us | 147 | -600.90 | 637.91 | 30.0452% | 2019-03-19 |

All three USD2,000 Moomoo accounts triggered the30%drawdown halt. The reviewer independently matched the first trigger, canceled pending orders and advanced outstanding exits to the next close. Actual drawdown can exceed30%because observation/exit timing and gaps do not create a guaranteed loss cap.

The largest absolute daily cash/equity difference between independent reconstruction and recorded floats was 1.73e-11USD. Five in-memory mutation checks detected altered entry fees, reservations, daily cash,5%week counts and halt drawdown. Original artifacts remained unchanged.

Source-panel construction and causal signal mathematics are separately reviewed; this audit binds their frozen raw-derived arrays and rankings. Adjusted-notional exits retain the declared synthetic corporate-action convention rather than proving actual broker share/cash accounting. The15bps quote-informed allowance plus current broker tariffs excludes fixed subscription/funding FX, personal tax and unresolved execution charges. No live/paper promotion or profitability qualification follows from arithmetic passing.

Detailed evidence: audit-20260929T004447Z.json, checker-validation.json, and audit_accounts.py.

# Engine qualification (2026-09-18)

Neither candidate is fully qualified for the combined US/Canadian market and corporate-action accounting requirement. Nautilus 1.231.0 is usable for a strictly limited synthetic/raw-data execution harness with native USD/CAD ledgers. Corporate-action periods must remain unsupported until the missing accounting and event semantics are resolved. This is an engineering qualification, not a performance backtest or live-capital authorization.

## Executed Nautilus result

Official PyPI version JSON confirmed 1.231.0, including a CPython 3.13 Windows wheel. The wheel SHA-256 is `5fc8e08e98b6a47a5f0104c12ac6d8d3cefa0fd9dd2bb0d211c1b14517ff9aaf`. The installation uses existing Python 3.13.7 at `C:\Python313\python.exe`, workspace environment `.qualification/nautilus`, and workspace uv cache `.cache/uv`. All 15 installed package versions are pinned in `engines/qualification/requirements.lock`; no global Python package was installed. Package identity is in `evidence/pypi-identity.json`.

`engines/qualification/probe.py` imports the real installed engine. Each scenario supplies 8 synthetic quotes and 2 synthetic bars for distinct native Equity objects `SYNTH_US.XNAS` (USD) and `SYNTH_CA.XTSE` (CAD). Each venue has its own cash account with initial USD 10,000 and CAD 10,000; this does not establish a consolidated cross-venue brokerage account. Fixed fee is 1 native currency unit per order. These identifiers, prices, timestamps and market conditions are engineering fixtures, not real stocks or data.

For each instrument, the baseline buys 10 shares at 100.00. Hand calculation: 10,000 - (10 x 100) - 1 = 8,999 native currency cash. Actual engine cash is exactly 8,999, quantity 10, basis 100, realized P&L -1 (fee), unrealized P&L 0. The other currency remains 10,000. A sell limit of 5 at 300 remains ACCEPTED. Both quote and external bar delivery are exercised.

No FX market is supplied: `cache.get_xrate(venue, CAD, USD)` returns null on both venues. Native cash balances therefore do not establish a consolidated USD NAV. The adapter needs explicit dated FX instrument quotes/rates and conversion policy; funding an account does not cause automatic USD/CAD conversion. FX execution and triangulation were not tested.

## Actual action experiments and qualification gaps

The public `SimulatedExchange.adjust_account(Money)` is reached through a registered `SimulationModule`. `Position.apply_adjustment(PositionAdjusted)` accepts quantity and realized-P&L changes. The actual adjustment enum contains only COMMISSION and FUNDING; there is no native dividend or split type.

A separate dividend experiment adds 5 native cash (10 shares x 0.50) and adds 5 to the existing position's realized P&L using FUNDING explicitly as an experimental carrier. Result: cash 9,004; quantity 10; basis 100; realized P&L +4 after the original fee; unrealized P&L 0; open limit unchanged. These numbers pass, but the event is semantically a funding event and direct position mutation is not evidence of durable engine-wide propagation, accounting reports, replay or entitlement/pay-date correctness. A cash-only adjustment would omit position attribution. Dividends remain unqualified for production use; no synthetic fills are used or claimed equivalent.

The 2-for-1 split experiment adds 10 shares through the same public position adjustment API and changes a resting limit from 5 at 300 to 10 at 150 through `Strategy.modify_order`. The actual order remains ACCEPTED and cash remains 9,004. Quantity becomes 20, but basis stays 100 instead of 50. At a synthetic post-split quote of 50, engine unrealized P&L is **-1,000 instead of 0**, while realized P&L remains +4. Thus the available quantity adjustment alone is not a faithful split adapter. The probe deliberately asserts this known failure rather than mocking a passing split.

An exploratory order-repricing run from 120 to 60 while the book still quoted 100 actually filled the modified order at 100. The final repeatable test uses non-crossing limits to isolate the accounting defect; atomic action/book/order ordering is an additional unresolved requirement. A faithful implementation also needs fractional splits/cash-in-lieu, shorts, pending/partially filled orders, cache/report updates, action idempotency and future exit P&L validation. None is claimed here.

## LEAN: pinned source inspection and blocked build, no engine execution

Pinned accessible source: commit `985ef30ad3ac774218c5ac516b4cb0aa2655730f` from QuantConnect/Lean. Its Launcher project targets `net10.0`; source license is Apache-2.0. Source inspection finds actual `ApplyDividend` and `ApplySplit` logic, including quantity and average-price adjustment; the dividend method explicitly says payable dates are not properly modeled. These are source observations, not executed results.

Default market-hours keys contain `Equity-usa-[*]` and `Equity-india-[*]`; inspected `Market.cs` has no Canada/Toronto constant and default equity symbol properties provide no verified Canadian market route. Arbitrary market extensions may be possible but Canadian native data/calendar/symbol/fee/corporate-action configuration is unqualified. US-listed Canadian exposure is not evidence of native CAD Canadian equities.

The host has SDK 9.0.310 and an existing .NET 10.0.12 runtime. Building the fetched pinned Launcher project with `--no-restore` fails NETSDK1045 because SDK 9 cannot target .NET 10. This is a target-framework preflight on the actual Launcher file, not a full repository build; no executable was produced or run. No .NET runtime/SDK or Docker change was made. First-run CLI output mentioned a development certificate; read-only inspection found only a localhost certificate dated 2026-05-31, predating this task. Nothing was deleted. `lean-build.txt` captures the exact failure; `lean-inspection.json` captures compact source content; full downloaded source snapshots are local in ignored `.qualification/lean-source-inspection`.

## Smallest route and validation

Use a pinned Nautilus adapter only for approved local raw bars/quotes -> orders -> actual fills/account snapshots. Keep the account ledger and currency identity explicit, require external dated FX for combined NAV, and fail closed on unsupported corporate actions. Do not route research fixtures to a broker. To qualify the combined scope, first establish a supported position cost-basis adjustment and event/report propagation path (or a narrowly maintained upstream change), then validate full split/dividend lifecycle against independent cash, holdings, order and P&L calculations. If that cannot be done without substituting core accounting, reassess LEAN after a compatible local build toolchain and Canadian configuration become available. Neither route presently satisfies the full scope.

Run from repository root in PowerShell:

```powershell
& 'C:\Users\user\.local\bin\uv.exe' venv --python 'C:\Python313\python.exe' '.qualification/nautilus'
& 'C:\Users\user\.local\bin\uv.exe' pip install --python '.qualification/nautilus/Scripts/python.exe' --cache-dir '.cache/uv' -r 'engines/qualification/requirements.lock'
& '.qualification/nautilus/Scripts/python.exe' 'engines/qualification/probe.py'
```

The final probe exits 0: baseline, dividend, split each run twice (six real engine runs), with direct equality of normalized financial/order content and independent cash/fee/quantity/order/P&L assertions. Generated event/order/position IDs and wall-clock run timings are excluded explicitly; economic fields are retained. Output is `engines/qualification/evidence/nautilus-probe.json`. The installed engine emits a pandas `Timestamp.utcnow` deprecation warning; it does not affect assertions. Initial development errors (calling the adjustments property and crossing split order) were investigated before this final successful run. `rtk --version` exited 1 because rtk is not available in the working escalated shell; explicit executable paths were used. Regular sandbox commands were unavailable due to helper setup failure.

Sources: [PyPI pinned release](https://pypi.org/pypi/nautilus_trader/1.231.0/json), [LEAN pinned Launcher](https://github.com/QuantConnect/Lean/blob/985ef30ad3ac774218c5ac516b4cb0aa2655730f/Launcher/QuantConnect.Lean.Launcher.csproj), [LEAN portfolio accounting](https://github.com/QuantConnect/Lean/blob/985ef30ad3ac774218c5ac516b4cb0aa2655730f/Common/Securities/SecurityPortfolioManager.cs), [LEAN market hours](https://github.com/QuantConnect/Lean/blob/985ef30ad3ac774218c5ac516b4cb0aa2655730f/Data/market-hours/market-hours-database.json), [LEAN license](https://github.com/QuantConnect/Lean/blob/985ef30ad3ac774218c5ac516b4cb0aa2655730f/LICENSE).

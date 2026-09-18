# Task 1 report

Status: bounded qualification complete; neither engine fully qualified. No broker/account or live-capital operation.

- Installed official Nautilus 1.231.0 with Python 3.13.7 into workspace `.qualification/nautilus`; all dependencies pinned in `engines/qualification/requirements.lock`.
- Final command: `& '.qualification/nautilus/Scripts/python.exe' 'engines/qualification/probe.py'`; exit 0. Six real engine runs, normalized repeated equality; native USD/CAD purchases and fee cash match 8,999 exactly. Structured actual output: `engines/qualification/evidence/nautilus-probe.json`.
- Dividend experiment numerically reconciles cash 9,004 and realized P&L +4 using funding adjustment carrier, but dividend event semantics, entitlement timing and reporting propagation are not qualified.
- Split quantity/order experiment exposes a real blocker: quantity 20, order 10 @150 ACCEPTED, basis remains100 instead of50 and unrealized P&L is -1,000 instead of0. No synthetic-fill workaround. Corporate actions must fail closed.
- FX conversion without FX quotes returns null. Native-currency debits are proven in two separately seeded multi-currency venue accounts, each initially funded with USD 10,000 plus CAD 10,000; a consolidated broker account/NAV is not proven.
- LEAN pinned commit985ef30ad3ac774218c5ac516b4cb0aa2655730f requires net10.0; host has runtime10.0.12 but SDK9.0.310. Actual Launcher target preflight exit1 NETSDK1045. No LEAN engine execution. Inspected native Canada route unverified; default equity calendars are USA/India. Apache-2.0 source license.
- Source snapshots kept ignored under `.qualification/lean-source-inspection`; compact identity, source excerpts and actual build failure checked in under owned evidence path. `fetch_sources.py` retrieves the pinned Launcher csproj into this current snapshot directory. `docs/engine-qualification.md` records the exact original preflight command, explains the old path in its log, and gives a reproducible command for the current snapshot path. Review fixes did not rerun the probe or .NET.
- Self-review caught adjustments property misuse and split order crossing stale pre-split book; final probe uses non-crossing limit to isolate basis defect. Source-only findings clearly separated from executed findings. No global package/runtime installs. .NET first-run certificate message investigated read-only; only preexisting 2026-05-31 localhost cert found, none removed.
- RTK unavailable in escalated shell (exit1); explicit runtime paths used. Sandbox helper setup failure required escalated commands. Root handles integration, independent review and commits.

Recommendation: bounded Nautilus raw quote/bar execution adapter with explicit native-currency snapshots, unsupported-action rejection, and dated external FX for consolidated reporting. See `docs/engine-qualification.md` for commands, source links, exact boundaries and remaining qualification work.

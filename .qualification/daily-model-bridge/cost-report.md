# Task 4 execution-cost evidence

Completed September 19, 2026. Only docs/trading-cost-evidence.md and isolated cost-* evidence were changed. No production assumptions, frozen study files, paper account or trading transport were changed; no account/order/live/upgrade endpoints were called and no spending occurred.

Predeclared 6 symbols x 3 dates x 3 one-minute windows independently of model returns. All 54 cells and 17 SIP historical GET pages completed: 131,655 updates. Preserved every raw response with SHA-256 and safe metadata. Valid/crossed/uncovered duration reconciles to 3,240 seconds. Complete cells, including sparse BANF opening states, are in cost-all-cells.md and cost-analysis.json; duration means span 0.552 to 420.968 bps across cells. This is quotes, not fills or calibrated slippage.

Current primary Canadian broker tariffs rechecked: Moomoo direct HTTP403 limitation retained, indexed primary schedule verified; Wealthsimple legal page read directly. Five USD400 slot caps including fees yield 39 shares at USD10 on Moomoo, with USD19.90 aggregate round-trip broker charge plus USD0.05 SEC before other charges. Fee arithmetic and USD-account/FX alternatives are separately documented. 20/40/100 scenarios remain unchanged.

Offline validation passed all 54 duration means using independent Decimal loops, SHA-256 checks, ordinary session calendar checks and synthetic boundary/invalid/equal-time cases. First analyzer invocation hit pandas fractional/nonfractional ISO timestamp parsing error; repaired by explicit ISO8601 parsing, no capture changes or sample substitutions. No historical request errors occurred.

Reproduce offline (PowerShell, repository root):

```powershell
& 'D:\安装包\rtk-x86_64-pc-windows-msvc\rtk.exe' proxy .venv/Scripts/python.exe -X utf8 .qualification/daily-model-bridge/cost-analyze.py
& 'D:\安装包\rtk-x86_64-pc-windows-msvc\rtk.exe' proxy .venv/Scripts/python.exe -X utf8 .qualification/daily-model-bridge/cost-verify.py
```

Do not rerun cost-probe.py capture over this fixture; it intentionally rejects overwrite. See cost-definition.json for fixed selection and bounds, cost-capture-summary.json for page completion, cost-tariff-source-review.json for fee provenance, cost-verification.json for independent arithmetic. These artifacts remain unqualified for economic promotion: purposive surviving-stock sample, three January dates, quote-state persistence assumptions, present provider vintage, and unverified owner tariff/execution remain material limitations.

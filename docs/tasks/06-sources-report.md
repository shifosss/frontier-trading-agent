# Task6: Existing connector source integration report

Owned files: src/frontier/sources.py, tests/test_sources.py, scripts/import_longbridge_snapshot.py, docs/existing-connectors.md and this report. No UI, CLI entrypoint, dependency, broker or auth configuration changes.

## Completed evidence

- Actual import:434 retained Longbridge SPY hourly bars across62sessions; source period starts converted to official session endpoints with final partial bar and one-minute inferred availability. Dataset ID: `c45b18a7ce3ad18a53d18e5534ff1148aa46861bec3ec5bc0a802c524a167f81`.
- Dataset observation range:2026-06-22T14:30:00Z to2026-09-17T20:00:00Z. Local capture/save mtime:2026-09-18T14:45:15.727564Z. Basis explicitly says filesystem save timestamp, not provider response time.
- All62 daily aggregated opens/closes equal retained Alpha Vantage values. Max high discrepancy0.08USD; low0.27USD; volume44,264,518shares. Differences remain in per-date evidence, without forcing equality or inventing a cause.
- Alpaca June18 ex-date/July31 payable+process record excluded from flat June22 window by economic ex-date. Exclusion recorded; action coverage remains unknown. BoC dated FX uses inferred16:30Toronto publication, with DST and no future publication inclusion.
- Source mode historical, interval1h, inferred availability, raw-price/exploratory limitations. No Canadian hourly source/qualification claimed.
- Actual read-only CLI help/schema/status inspected. CLI token.status is expired. Helper fails with manual `longbridge auth login` hint before history fetch. Working app connector snapshot and expired standalone CLI are kept distinct. No login, updater, token file inspection, account or order command executed.
- Actual public BoC helper request returned3 observations forJune18–22. First call cache_hit=false; second cache_hit=true. Raw capture: artifacts/sources/cache/boc_fxusdcad_2026-06-18_2026-06-22.5692106dbce4c1e8d55dbf60b9f05ceb6f6e82ee299204706667792c8a73e49e.json.
- Narrow helpers use HTTP/subprocess timeouts, argument arrays, explicit raw adjustments/intraday session, dated content-addressed raw cache. Longbridge helper rejects potential1000-row truncation rather than claiming exhaustive history.

## Commands and results

```powershell
& .venv/Scripts/python.exe -m pytest tests/test_sources.py -q
# 11 passed in1.43s
& .venv/Scripts/python.exe -m ruff check src/frontier/sources.py scripts/import_longbridge_snapshot.py tests/test_sources.py
# All checks passed
& .venv/Scripts/python.exe scripts/import_longbridge_snapshot.py
# imported434rows and wrote fullcomparison evidence
```

Tests cover full/partial/early-close bar endpoints, off-session and holiday rejection, unavailable/future bars, DST FX availability, ex-date versus process/pay dates, daily disagreements retained, successful raw cache/reuse/explicit refresh, expired auth fail-closed with no quote/login/trade call, fixed read-only history arguments, 1000-row boundary and unsupported symbols.

Artifacts: data/imports/longbridge-spy-hourly-2026-06-22_2026-09-17, immutable data/datasets/<dataset_id>, artifacts/sources/longbridge-hourly-import.json. HTTP/CLI/UI wiring and hourly engine qualification are root's next integration step. An authenticated standalone CLI history call remains untested because auth is expired; no successful response was fabricated.

References and exact connector boundaries are documented in docs/existing-connectors.md.

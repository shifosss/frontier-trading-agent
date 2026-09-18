# Existing market-data connectors

The workstation now has a retained Longbridge US hourly source importer and narrow read-only source helpers in `frontier.sources`. These are separate from the existing app connectors. They do not connect a broker, submit orders, authenticate automatically or change any installed tool.

## Retained Longbridge SPY hourly snapshot

The app connector supplied 434 regular-session bars for SPY from 2026-06-22 through2026-09-17. Source timestamps are interpreted as period starts. Official XNYS session endpoints convert 13:30–19:30 UTC starts to 14:30–20:00 UTC ends; the final bar is 30 minutes, including correct early-close clipping. Availability is inferred at endpoint plus one minute, and bars unavailable at the supplied capture boundary are rejected. This is historical snapshot research, not an observed point-in-time publication feed.

Run from the repository root:

```powershell
& .venv/Scripts/python.exe scripts/import_longbridge_snapshot.py
```

The default capture boundary is the retained hourly file's actual filesystem modification timestamp in UTC, labeled as observed local save completion rather than provider response time. An explicit timezone-aware `--captured-at` is available for controlled replay. The import remains `historical`, `interval=1h`, `availability_basis=inferred`, `corporate_actions_status=unknown`. No Canadian hourly data is provided by this adapter.

Daily aggregation is compared with the retained Alpha Vantage SPY snapshot, without editing either source to agree. All 62 session opens and closes match. Maximum absolute differences are 0.08 USD for highs, 0.27 USD for lows, and 44,264,518 shares for daily volume. These differences are evidence of source disagreement; their cause is not established here. Full daily comparisons are in `artifacts/sources/longbridge-hourly-import.json`.

The Alpaca snapshot includes a cash dividend with process/payment date 2026-07-31 and economic ex-date 2026-06-18. Window membership uses ex-date. A fresh flat June 22 account has no inherited June 18 dividend entitlement; the July process date does not introduce an in-window action. The excluded record remains in provenance. This small snapshot does not establish complete action coverage, so replay still requires explicit exploratory opt-in and cannot claim total return.

## Standalone Longbridge CLI

Verified installed executable: `C:\Users\user\AppData\Local\Programs\longbridge\longbridge.exe`. Read-only `auth status --format json` reports `expired`; the working app connector's retained snapshot does not establish standalone CLI authentication. To restore CLI authentication, the user may run `longbridge auth login` manually. The helper never initiates login, reads token files directly or runs the advertised updater.

On this Windows installation, this explicit command also works when the CLI is not
on PATH. Complete the interactive sign-in yourself:

```powershell
& "$env:LOCALAPPDATA\Programs\longbridge\longbridge.exe" auth login
```

Then inspect `frontier source-status` before attempting a dated fetch. Authentication
alone does not establish quote entitlement or Canadian coverage.

`longbridge_status()` returns only status, authenticated flag and an actionable hint. `fetch_longbridge_history('SPY.US', start, end, capture_dir)` issues a subprocess argument array with `shell=False` and a timeout, using:

```text
kline history SPY.US --period 1h --start YYYY-MM-DD --end YYYY-MM-DD --adjust none --session intraday --format json
```

Both dates are mandatory. The installed CLI help says omitting either date falls back to the latest 100 bars and ignores the other date. The upstream historical API caps a response at 1000 rows; with both dates, an oversized query prioritizes rows nearest the end. The helper rejects windows that may reach that cap and responses of 1000 rows rather than accepting silently truncated history. Request smaller windows explicitly. [Longbridge historical candlesticks](https://open.longbridge.com/docs/quote/pull/history-candlestick).

Only US symbols are accepted. Quote entitlement failures are explicit. Read-only command and cache behavior are tested; an authenticated CLI history request was not executed because the current login is expired.

## Bank of Canada FX

`fetch_boc_fx(start, end, capture_dir, refresh=False, timeout=15)` fetches the free public Valet FXUSDCAD endpoint with bounded HTTP timeout. It stores exact successful response bytes under a content-addressed filename and records URL, parameters, observed retrieval time and digest in a capture index. Repeat requests reuse that dated capture after digest validation; `refresh=True` explicitly requests a new observation. Prior raw versions are retained. [Valet API](https://www.bankofcanada.ca/valet/docs).

`boc_rows(snapshot, captured_at)` uses 16:30 America/Toronto publication availability with DST. This is an inferred publication time, not proof that any particular historical response was available at precisely that minute; future publications are omitted at the capture boundary. Rates support reporting, without creating currency conversion trades. The Bank describes its published rates as indicative daily averages. [Daily exchange rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/).

Actual helper smoke fetched 3 FX observations for 2026-06-18 through2026-06-22, persisted raw bytes, then returned the same cached response on the second call. No paid provider or credential was introduced.

# Sample market data: source and limits

Checked on 2026-09-18 (America/Toronto). These are raw, dated research snapshots; the application must show their last observation date and must not describe them as live prices.

| Snapshot | Source | Coverage |
| --- | --- | --- |
| `data/raw/alpha_vantage_spy_daily_compact_2026-09-17.json` | Existing Alpha Vantage connector, `TIME_SERIES_DAILY`, `SPY`, raw/compact | 100 daily OHLCV bars; latest 2026-09-17; metadata timezone `US/Eastern` |
| `data/raw/alpha_vantage_xiu_trt_daily_compact_2026-09-17.json` | Existing Alpha Vantage connector, `TIME_SERIES_DAILY`, `XIU.TRT`, raw/compact | 100 daily OHLCV bars, 2026-04-27 through 2026-09-17; metadata timezone `US/Eastern` |
| `data/raw/alpha_vantage_spy_dividends_2026-09-18.json` | Existing Alpha Vantage connector, `DIVIDENDS`, `SPY` | 111 distribution records, 1999-03-19 through 2026-06-18; amount, ex-dividend, declaration, record, and payment dates (older missing dates are literal `None` strings) |
| `data/raw/boc_fxusdcad_2026-04-27_2026-09-17.json` | Bank of Canada Valet `FXUSDCAD` JSON | 100 dated observations, 2026-04-27 through 2026-09-17; value is CAD for one USD |

Alpha Vantage symbol search returned `XIU.TRT` as a Toronto ETF in CAD. `DIVIDENDS(XIU.TRT)` returned an empty `data` array; that is missing provider coverage, **not** evidence that the fund had no distributions. The raw daily responses contain no adjusted close or corporate-action fields. `SPLITS(AAPL)` separately returned split factors including 4 on 2020-08-31 and 7 on 2014-06-09. No Canadian action history was established. Keep raw price returns separate from dividend-inclusive total returns, and do not infer total returns for XIU from this sample.

Alpha Vantage's [API documentation](https://www.alphavantage.co/documentation/) describes compact daily output as 100 bars and requires premium access for full daily history; it labels historical intraday as premium. Its [support page](https://www.alphavantage.co/support/) states a standard free limit of 25 API requests per day. This existing connector supplied the snapshots, but it is not an app credential or a promise of independent access from a local backend. The Financial Datasets connector returned a zero-credit error for a small SPY daily query and was not used.

The [Bank of Canada Valet how-to](https://www.bankofcanada.ca/valet-api-how-to/) states that FX access is free and needs neither registration nor an API key. The exact tested URL was `https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=2026-04-27&end_date=2026-09-17`; its JSON records use `d` for date and `FXUSDCAD.v` for a decimal string. The [Bank's rate page](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/) describes an indicative daily average published each business day by 16:30 ET, rather than a trading-session close. Follow its [terms](https://www.bankofcanada.ca/terms/) on attribution, accuracy, and request limits; cache fetched observations.

For longer history or hourly bars, use an explicit user-supplied CSV import with symbol, exchange, currency, timezone, bar timestamp, interval, OHLCV, adjustment policy, source, and separate dividend/split events. No unrestricted, no-credential hourly US-and-Canadian source was verified. Yahoo's internal chart route is undocumented and its [Canadian terms](https://legal.yahoo.com/ca/en/yahoo/terms/otos/) restrict automated data collection without prior permission, so it should not be used as the default importer.

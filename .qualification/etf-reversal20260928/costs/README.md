# Predeclared ETF execution-cost sample
Fixed11 equity ETFs, first2016/2020/2024sessions,15:59-16:00ET:33cells. No quote GET or ETF strategy outcome preceded this declaration. The unchanged capture and analyzer are reused with a bounded streaming wrapper. All cells and raw failures remain visible; incomplete cells are never replaced.

All33cells need complete pagination, no source/analysis error, finite nonnegative full-spread mean, and at least59of60seconds mechanically valid quoted-state duration. The uniform round-trip sensitivity is ceiling(maximum cell mean full spread)+10bps. The extra10bps is an uncalibrated5bps-per-side adverse allowance. No pre-window quote or stale-age cutoff is used. This is not a realized-fill calibration, liquidity qualification or upper bound.

[Alpaca contract](https://docs.alpaca.markets/us/reference/stockquotes-1) defines symbol-first pagination and inclusive endpoints; analysis excludes observations exactly at16:00. Session-asof selects entity mapping and does not reconstruct a point-in-time data vintage.

[Wealthsimple](https://www.wealthsimple.com/en-ca/legal/fees/trade) lists zero equity commission and no trade FX for existingUSDaccounts. Its ordinaryCAD10monthly fee plus applicable tax is separate; owner waiver and marginal subscription burden are unknown. Funding/withdrawal currency conversion and the variable corporate-rate spread are excluded from trading returns.

[Moomoo Canada](https://www.moomoo.com/ca/support/topic10_122) direct retrieval was denied403; indexed primary Canadian-entity content supports the existing per-share/minimum commission, platform and sellSEC components. Venue charges, taxes, actual rounding/promotions and carrying-broker completeness remain unresolved. Current tariffs applied to historical prices are a counterfactual, not a historical fee reconstruction. The existing cent-ceiling convention is a scenario assumption. No US-entity fee schedule is substituted.

[BoC daily observation](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=2026-09-28&end_date=2026-09-28) is1.4168CAD/USD. An unwaivedCAD120annual fee isUSD84.70beforetax:4.2349%ofUSD2000or0.8470%ofUSD10000. This one-date indicative conversion is not an executed broker FX quote or annual historical rate. An illustrative13%tax calculation is separately recorded and is not an assumption about the user's tax residence.

Before account inputs use the inferred allowance, independently verify all33cells with Decimal, raw SHA256 and full token chains. No strategy outcomes or account/model files are read by this capture.

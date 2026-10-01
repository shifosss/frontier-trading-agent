"""Human-reviewed primary evidence, kept separate from numeric source checks."""
from pathlib import Path
import csv, json, hashlib
from collections import Counter
ROOT=Path(__file__).resolve().parent
def load(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
# No model outputs, strategy outcomes, or account journals are inputs.
CASES=[
("DHR","2016-07-05","contradicted_split_only","distribution_not_DHR_share_split","regular_way_July5_explicit",
 "Danaher/FTV","One FTV share per two DHR shares; distributed July2, regular-way FTV trading and expected DTC credit July5. Provider1.319 is not a DHR share-quantity ratio.",
 "Fractional FTV rights sold and proceeds distributed; exact sale proceeds and broker credit unverified."),
("LINK","2016-04-04","unresolved","unverified","unverified",
 "Interlink Electronics","Retained proxy identifies Interlink and shares outstanding April4; it does not verify this1.25 split. Both independent windows empty.",
 "Action rights and settlement unresolved."),
("MRBK","2023-03-21","partial_notice","ratio_corroborated","next_session_inferred_from_after_close_March20",
 "Meridian Corporation","Two-for-one via100% stock dividend, recordMarch14, distribution after closeMarch20. March21 is the next-session inference, not a separately stated exchange ex-date.",
 "Stock distribution terms found; complete broker credit handling unverified."),
("IP","2021-10-01","contradicted_split_only","distribution_not_IP_share_split","October1_completion_explicit",
 "International Paper/SLVM","October1 Sylvamo spin-off, one SLVM share per11 IP shares; provider1.056 is not an IP share-quantity ratio.",
 "Distribution value, fractional handling and broker credit not reconciled."),
("OLOX","2023-09-28","contradicted_split_only","distribution_not_same_security_split","September27_distribution;September28_market_boundary_unverified",
 "Safe & Green -> Olenox January20,2026","Issuer10-K reports September27,2023 SGDevCorp distribution of0.930886 shares perfive parent shares. Provider2.133 is not a same-security share-quantity ratio. Current name changed January20,2026.",
 "Cash in lieu stated; proceeds, exact ex-session and historical share-class mapping remain incomplete."),
("NTES","2020-10-02","partial_notice","ADS_ratio_corroborated","next_session_inferred_from_after_close_October1",
 "NetEase ADS","ADS underlying shares25->5, economically five ADS perold ADS; effective October1 close, giving next-session October2. Ordinary shares unchanged.",
 "Existing ADS remain valid and no exchange required; actual broker credit timing unverified."),
("EVO","2021-10-20","unresolved","unverified","unverified",
 "Evotec current ADS; earlier representation unresolved","Annual report confirms November2021 IPO ADS each represents0.5 ordinary share. It does not establish the alleged October20 four-for-one boundary. Independent boundary bars both12.62 with zero volume disagree with frozen nominal prices.",
 "Earlier security/share units and source entity mapping unresolved; cannot choose either series as truth."),
("CZFS","2024-06-14","partial_notice","one_percent_stock_dividend_corroborated","record_date_verified;ex_session_unverified",
 "Citizens Financial Services (CZFS)","Issuer release confirms1% stock dividend payableJune28 to June14 record holders, with separate0.49 cash dividend. It does not explicitly establish June14 as ex-session. Independent split factor unchanged at requested boundary.",
 "Separate stock/cash entitlement and broker settlement unverified."),
("ODFL","2024-03-28","basic_terms_corroborated","ratio_corroborated","split_adjusted_trading_March28_explicit",
 "Old Dominion Freight Line","SEC proxy explicitly confirms two-for-one and adjusted trading March28. Numeric test remains outside the original strict precision interval.",
 "Fractional/broker mechanics not audited."),
("DIT","2026-03-23","partial_notice","ratio_corroborated","March20_effective;March23_market_session_unverified",
 "AMCON Distributing","SEC10-Q says3-for-2 through50% stock dividend effectedMarch20, recordMarch6. Exact March23 market ex-session not explicitly established.",
 "Broker credit and fractional mechanics unresolved."),
("BRAI","2026-04-29","basic_terms_corroborated","ratio_corroborated","April29_split_adjusted_trading_announced",
 "Braiin Limited","Issuer SEC exhibit declares3-for-1, after-closeApril28 distribution, adjusted trading expectedApril29; bar factor consistent.",
 "Broker credit/fractional mechanics not audited."),
("WMT","2024-02-26","basic_terms_corroborated","ratio_corroborated","February26_split_adjusted_trading_explicit",
 "Walmart","Three-for-one with two additional shares; payable after closeFebruary23, adjusted tradingFebruary26.",
 "Actual broker credit not audited."),
("TOPS","2017-10-06","basic_terms_corroborated","ratio_corroborated","October6_effective_explicit",
 "TOP Ships","SEC annual report confirms one-for-two effectiveOctober6. Split factor agrees, but effective nominal source close0.53 vs raw0.5325 exceeds declared price precision; volume factor is unidentifiable under declared rounding after extreme later adjustment.",
 "Price/volume conventions unresolved; ratio agreement does not qualify full history."),
("CRVO","2023-08-17","basic_terms_corroborated","ratio_corroborated","August17_split_adjusted_trading_explicit",
 "Diffusion Pharmaceuticals/DFFN -> CervoMed/CRVO August17,2023","Issuer announces completed EIP merger and1-for-1.5 reverse-adjusted CRVO tradingAugust17. New ticker/name and merger coincide.",
 "Merger share-class entitlements, fractional/cash settlement not fully reconciled."),
("ENOV","2022-04-05","contradicted_split_only","actual_reverse_ratio_one_third_not_0.581","April5_regular_way_trading_explicit",
 "Colfax/CFX -> Enovis/ENOV plus ESAB","Issuer confirms one ESAB share perthree old parent shares distributedApril4, followed by1-for-3 reverse split; both regular-way tradingApril5. Independent split factor3 agrees with actual reverse, not reciprocal0.581.",
 "Distribution valuation, fractional proceeds and broker credit unverified; do not replace composite vendor factor blindly."),
("CYPH","2023-06-21","basic_terms_corroborated","ratio_corroborated","June21_split_adjusted_trading_explicit",
 "Leap Therapeutics/LPTX -> Cypherpunk/CYPH November13,2025","Issuer explicitly reclassifies tenold shares intoone at June20 5pm, tradingJune21; later SEC filing maps name/ticker inNovember2025.",
 "Proportional cash instead of fractional shares stated; actual cash and broker settlement unverified."),
("NUWE","2022-12-12","basic_terms_corroborated","ratio_corroborated","December12_exchange_effective_explicit",
 "Nuwellis; new CUSIP67113Y405","Nasdaq notice confirms one-for-100 and December12 effective date; independent factor agrees.",
 "Exchange notice alone does not reconcile fractions, cash or broker settlement."),
("QXL","2022-09-06","partial_notice","ratio_corroborated","August31_legal_effective;September6_market_session_unverified",
 "Viewbix/VBIX -> Quantum X/QXL April30,2026","SEC report confirms1-for-28 concurrent with certificate effectiveAugust31,2022; September6 is referenced filing date, not established market ex-session. Both independent requested windows empty.",
 "Legal/market date distinction and historical data mapping unresolved."),
("ALM","2025-07-07","partial_notice","ratio_corroborated","July7_TSX_verified;USD_market_session_unverified",
 "Almonty common shares; USD listing path unresolved","Issuer filing confirms1.5old->1, legalJuly3 and TSX adjusted tradingJuly7. Selected source isUSD; independent response has onlyfour later bars and neither boundary.",
 "US predecessor/venue mapping, fractions and broker handling unresolved."),
("HON","2026-06-29","contradicted_split_only","actual_reverse_ratio_one_half_not_0.9535","June29_effective_explicit",
 "Honeywell Technologies/HON plus Honeywell Aerospace/HONA","Issuer confirms one HONA pertwo old HON shares plus1-for-2 HON reverse effectiveJune29. Independent factor2 agrees with reverse ratio, not reciprocal0.9535.",
 "Spin-off and reverse fractions sold for cash; actual proceeds/credits unverified. Composite factor is not a quantity multiplier."),
("WHLR","2024-11-19","basic_terms_corroborated","ratio_corroborated","November19_exchange_effective_explicit",
 "Wheeler REIT; new CUSIP963025846","Nasdaq confirms1-for-2 November19. Price factor agrees; zero-volume boundary prevents volume-factor conclusion.",
 "Fractional/cash and broker mechanics unverified."),
("STKH","2025-04-28","basic_terms_corroborated","ADS_ratio_corroborated","April28_effective_explicit",
 "Steakholder Foods ADS;100->500ordinary perADS","SEC annual report confirms everyfiveADS intoone onApril28; ordinary shares perADS100->500.",
 "Underlying ordinary shares must not be confused with ADS quantity; depositary charges, fractions and broker settlement unresolved."),
("WOK","2025-12-29","basic_terms_corroborated","ratio_corroborated","December29_exchange_effective_explicit",
 "WORK Medical ClassA; CUSIPG9767H125","Nasdaq confirms1-for-100 and par0.05->5 effectiveDecember29. Observed price factor100, but propagated interval width3.67% exceeds predeclared2% maximum, so not numerically accepted.",
 "No assumption about fractional rounding/cash from price evidence; full terms and broker settlement unresolved."),
("QXL","2025-03-14","basic_terms_corroborated","ratio_corroborated","March14_effective_explicit",
 "Viewbix/VBIX -> Quantum X/QXL April30,2026","SEC report explicitly confirms1-for-4 effectiveMarch14,2025. Both requested independent windows empty despite dated mapping evidence.",
 "Historical market-data entity path and broker/action settlement unresolved.")
]
def main():
    bar={(r['symbol'],r['effective_session']):r for r in load('bar-factor-results.json')}
    notices=[]
    for symbol,day,status,ratio,session,entity,note,limits in CASES:
        main_symbol='QXL' if symbol=='QXL' else symbol
        pattern=f'notice-{main_symbol}-[0-9]*.capture.json'
        metas=[json.loads(p.read_text()) for p in ROOT.glob(pattern)]
        if symbol in ('CYPH','QXL'):metas += [json.loads(p.read_text()) for p in ROOT.glob(f'notice-{symbol}-mapping-*.capture.json')]
        assert metas and all(m['status_code']==200 for m in metas)
        evidence=[dict(url=m['url'],raw_file=m['raw_file'],sha256=m['sha256'],captured_at=m['captured_at'],text_file=m['text_file']) for m in metas]
        b=bar[symbol,day]
        notices.append(dict(symbol=symbol,effective_session=day,notice_status=status,ratio_status=ratio,session_status=session,dated_entity_mapping=entity,
            findings=note,full_action_accounting_status='unresolved',limits=limits,primary_evidence=evidence,
            price_factor_status=b['price_factor_status'],volume_factor_status=b.get('volume_factor_status','unresolved_missing_boundary'),
            nominal_status={k:v['nominal_comparison'] for k,v in b['boundaries'].items()}))
    (ROOT/'notice-assessments.json').write_text(json.dumps(notices,indent=2),encoding='utf-8')
    selected={(n['symbol'],n['effective_session']):n for n in notices}
    sample=list(csv.DictReader((ROOT.parent/'action-inventory20260928/validation-sample.csv').open(encoding='utf-8',newline='')))
    rows=[]
    for s in sample:
        n=selected.get((s['symbol'],s['effective_session']))
        rows.append(dict(symbol=s['symbol'],effective_session=s['effective_session'],currency=s['currency'],stratum=s['stratum'],source_sha256=s['source_sha256'],
            batch_status='attempted' if n else 'pending_out_of_scope',
            price_factor_status=n['price_factor_status'] if n else 'not_attempted',
            notice_status=n['notice_status'] if n else 'not_attempted',
            full_action_accounting_status='unresolved' if n else 'not_attempted',
            reason=n['findings'] if n else 'Outside fixed USD on/after2016-01-04 scope; retained without replacement.'))
    with (ROOT/'all91-status.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary=dict(total_sample=91,attempted_events=24,pending_events=67,bar_requests=48,notice_requests=25,
        price_factor_counts=dict(Counter(n['price_factor_status'] for n in notices)),
        notice_counts=dict(Counter(n['notice_status'] for n in notices)),
        full_action_accounting_qualified=0,
        scope='Original sample unchanged; no additional searches or acquisitions after fixed batch.')
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()


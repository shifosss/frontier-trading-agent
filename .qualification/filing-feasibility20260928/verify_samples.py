"""Checks for the bounded three-accession feasibility sample, no strategy outcomes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json, hashlib, re, html, xml.etree.ElementTree as ET
P=Path(__file__).parent
requests=json.loads((P/'requests.json').read_text()); facts=json.loads((P/'fact-context-inspection.json').read_text())
assert len(requests)==11
for request in requests:
    raw=(P/request['raw_file']).read_bytes()
    assert request['status']==200 and len(raw)==request['bytes'] and hashlib.sha256(raw).hexdigest()==request['sha256']
expected={
 'aapl_2020q3':('AAPL','0000320193-20-000062','2020-03-29','2020-06-27','11253000000','2019-03-31','2019-06-29','10044000000','2019-09-28','338516000000'),
 'msft_2024q3':('MSFT','0000950170-24-048288','2024-01-01','2024-03-31','21939000000','2023-01-01','2023-03-31','18299000000','2023-06-30','411976000000'),
 'f_2024q2':('F','0000037996-24-000144','2024-04-01','2024-06-30','1831000000','2023-04-01','2023-06-30','1917000000','2023-12-31','273310000000')}
calendar_path=P.parent/'intraday-opening20260928/calendar.json'; calendar=json.loads(calendar_path.read_text())
examples=[]
for name,(symbol,acc,s1,e1,v1,s2,e2,v2,instant,assets) in expected.items():
    rows=facts[name]['rows']; assert not any('extraction_error'in r for r in rows)
    chosen=[]
    for tag,conditions,value in [('us-gaap:NetIncomeLoss',{'startDate':s1,'endDate':e1},v1),('us-gaap:NetIncomeLoss',{'startDate':s2,'endDate':e2},v2),('us-gaap:Assets',{'instant':instant},assets)]:
        matches=[r for r in rows if not r['dimensions'] and r['name']==tag and all(r['context'].get(k)==v for k,v in conditions.items())]
        assert matches and {r['numeric_value'] for r in matches}=={value}
        for r in matches:
            unit=ET.fromstring(r['unit_xml']); measures=[e.text for e in unit.iter() if e.tag.endswith('}measure')]
            assert measures==['iso4217:USD'] and r.get('scale')=='6'
        chosen.append({'concept':tag,'period':conditions,'USD':value,'occurrences':len(matches),'contextRefs':sorted({r['contextRef'] for r in matches})})
    raw_index=(P/'raw'/(name+'_index.bin')).read_text(encoding='utf-8'); plain=re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',raw_index)))
    index_acc=re.search(r'SEC Accession No\. ([0-9-]+)',plain)[1]; assert index_acc==acc
    filed=re.search(r'Filing Date (\d{4}-\d{2}-\d{2})',plain)[1]
    accepted=re.search(r'Accepted (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',plain)[1]
    D=max(filed,accepted[:10]); entry=next(r for r in calendar if r['session']>D)
    securities=[]
    for title in [r for r in rows if r['name']=='dei:Security12bTitle']:
        related={r['name']:r['text'] for r in rows if r['contextRef']==title['contextRef'] and r['name'].startswith('dei:')}
        securities.append({'title':title['text'],'ticker':related.get('dei:TradingSymbol'),'exchange':related.get('dei:SecurityExchangeName'),'contextRef':title['contextRef'],'dimensions':title['dimensions']})
    assert any(r['ticker']==symbol and r['title'].lower().startswith('common stock') for r in securities)
    examples.append({'symbol':symbol,'accession':acc,'source_sha256':facts[name]['source_sha256'],'accepted_index_text':accepted,'accepted_timezone_interpretation':'America/New_York; Apple independently API corroborated, others index convention only','filingDate':filed,'facts':chosen,'securities':securities,'proposed_D':D,'proposed_cutoff_local':D+' end-of-day +1hour','proposed_next_session':entry['session'],'proposed_entry_close_utc':entry['close'],'clock_is_proxy':True})
sub=json.loads((P/'raw/aapl_submissions.bin').read_bytes()); r=sub['filings']['recent']; apis=[]
for acc in ['0000320193-20-000062','0000320193-20-000060']:
    i=r['accessionNumber'].index(acc); row={k:v[i] for k,v in r.items()}; api_et=datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S'); row['acceptance_ET']=api_et; apis.append(row)
assert apis[0]['acceptance_ET']=='2020-07-30 19:29:09' and apis[0]['filingDate']=='2020-07-31'
header=(P/'raw/aapl_2020q3_header.bin').read_text(); assert '<ACCEPTANCE-DATETIME>20200730192909' in header and '<FILING-DATE>20200731' in header
concept=json.loads((P/'raw/aapl_eps_concept.bin').read_bytes()); vintages=[r for r in concept['units']['USD/shares'] if r.get('start')=='2020-03-29' and r.get('end')=='2020-06-27']; assert [(r['accn'],str(r['val'])) for r in vintages]==[('0000320193-20-000062','2.58'),('0000320193-20-000096','0.65'),('0000320193-21-000065','0.65')]
original_eps=[r for r in facts['aapl_2020q3']['rows'] if r['name']=='us-gaap:EarningsPerShareDiluted' and r['context'].get('startDate')=='2020-03-29' and not r['dimensions']]; assert {r['numeric_value'] for r in original_eps}=={'2.58'}
result={'status':'bounded_source_checks_passed_not_strategy_qualification','requests':len(requests),'http_200':len(requests),'total_raw_bytes':sum(r['bytes'] for r in requests),'raw_hashes_verified':True,'parsed_selected_fact_rows':sum(len(x['rows']) for x in facts.values()),'examples':examples,'apple_API_index_header_join':apis,'apple_EPS_same_period_vintages':vintages,'calendar_sha256':hashlib.sha256(calendar_path.read_bytes()).hexdigest(),'limits':['Not independent proof of historical public dissemination time','Original accession content retrieved in2026; postacceptance corrections possible','Only3examples; no eight-innovation warmup or universe completeness check','No return, signal, strategy or live execution result']}
(P/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['examples','apple_API_index_header_join','apple_EPS_same_period_vintages']}))

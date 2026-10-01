"""Qualify Q on already saved originals and prove frozen S/clock/history unchanged."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal,localcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
import cash_backing as model

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
OLD=REPO/'.qualification/filing-features20260928/attempts/657ca3491cb34dd59f29c37f3eca96c0'
CALENDAR=REPO/'.qualification/post-filing-strategy20260928/calendar.json'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2),encoding='utf-8')

def main():
    inputs={str(p.relative_to(REPO)):digest(p) for p in [OLD/'records.json',OLD/'events.json',OLD/'summary.json',CALENDAR,model.BASE_PATH,ROOT/'cash_backing.py',ROOT/'test_cash_backing.py',ROOT/'extraction-declaration.json',Path(__file__)]}
    for name,want in read(OLD/'summary.json')['files'].items():assert digest(OLD/name)==want
    attempt=ROOT/'compatibility'/uuid4().hex;attempt.mkdir(parents=True)
    save(attempt/'request.json',{'started_at':datetime.now(timezone.utc).isoformat(),'scope':'all252 existing original filing records; source-only compatibility, no new capture or return join','inputs':inputs,'expected_records':252})
    try:
        records=read(OLD/'records.json');old_events=read(OLD/'events.json');assert len(records)==len(old_events)==252
        enriched=[model.enrich_record(r) for r in records]
        for before,after in zip(records,enriched):assert all(after[k]==v for k,v in before.items()),before['accession']
        events=model.build_features(enriched,read(CALENDAR)['sessions']);lookup={e['accession']:e for e in events}
        for before in old_events:assert all(lookup[before['accession']][k]==v for k,v in before.items()),before['accession']
        span_checks=0;arithmetic_checks=0
        for r in enriched:
            if r['q_status']!='qualified':continue
            raw=Path(r['source_path']).read_bytes();assert sha256(raw).hexdigest()==r['source_sha256']
            for f in r['q_selected_facts']:
                for obj in [f,f['context_source'],f['unit_source']]:
                    assert sha256(raw[slice(*obj['source_span'])]).hexdigest()==obj['fragment_sha256'];span_checks+=1
            a,b,c,d,assets=[Fraction(Decimal(r[k])) for k in ['q_current_cfo','q_current_ni','q_prior_cfo','q_prior_ni','q_prior_fy_assets']]
            value=((a-b)-(c-d))/assets
            with localcontext() as precision:
                precision.prec=60;expected=Decimal(value.numerator)/Decimal(value.denominator)
                assert abs(expected-Decimal(r['Q']))<=Decimal('1e-36')*max(1,abs(expected))
            arithmetic_checks+=1
        extensions=[{k:v for k,v in r.items() if k.startswith('q_') or k in ['Q','symbol','accession','source_sha256','source_path','source_url','status','u']} for r in enriched]
        compact=[{k:v for k,v in r.items() if k not in ['all_facts','selected_facts','q_all_facts']} for r in events]
        save(attempt/'q-records.json',extensions);save(attempt/'q-events.json',compact)
        evaluation=[e for e in events if '2017-01-01'<=e['filing_date']<='2025-12-31']
        summary={'at':datetime.now(timezone.utc).isoformat(),'status':'complete','records':252,'original_records_all_fields_unchanged':True,'original_events_all_fields_unchanged':True,'q_status':dict(Counter(r['q_status'] for r in enriched)),'q_unavailable_reasons':dict(Counter(reason for r in enriched for reason in r['q_reasons'])),'joint_feature_status':dict(Counter(e['joint_feature_status'] for e in events)),'evaluation_originals':len(evaluation),'evaluation_S_eligible':sum(e['feature_status']=='qualified' and e['execution_status']=='qualified' for e in evaluation),'evaluation_joint_eligible':sum(e['joint_feature_status']=='qualified' for e in evaluation),'by_issuer':{symbol:{'records':sum(r['symbol']==symbol for r in enriched),'q_qualified':sum(r['symbol']==symbol and r['q_status']=='qualified' for r in enriched),'evaluation_joint_eligible':sum(e['symbol']==symbol and e['joint_feature_status']=='qualified' for e in evaluation)} for symbol in sorted({r['symbol'] for r in enriched})},'original_fact_context_unit_spans_checked':span_checks,'rational_Q_arithmetic_checked':arithmetic_checks,'inputs':inputs,'files':{name:digest(attempt/name) for name in ['q-records.json','q-events.json','request.json']},'price_returns_read':False,'new_network_requests':0,'limitation':'Compatibility on the previously requested six-issuer originals; it neither selects nor replaces the new100-issuer cohort, and includes pilotfinancialissuerBANF only to preserve complete original denominator.'}
        for path,want in inputs.items():assert digest(REPO/path)==want,path
        save(attempt/'summary.json',summary);print(json.dumps({'attempt':str(attempt),**summary},indent=2))
    except BaseException as error:
        import traceback
        save(attempt/'failure.json',{'error':repr(error),'traceback':traceback.format_exc()});raise
if __name__=='__main__':main()

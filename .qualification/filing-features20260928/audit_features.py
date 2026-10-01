"""Read-only source feature arithmetic/spans audit; never reruns parser or policy."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal,localcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def as_decimal(f):return Decimal(f.numerator)/Decimal(f.denominator)


def audit(attempt):
    attempt=Path(attempt).resolve();summary=read(attempt/'summary.json')
    for name,want in summary['files'].items():assert digest(attempt/name)==want,name
    records=read(attempt/'records.json');events=read(attempt/'events.json')
    assert len(records)==len(events)==summary['original_records']==252
    keyed={(r['symbol'],r['accession']):r for r in records}
    assert len(keyed)==252
    original_ratios={};span_checks=0
    with localcontext() as precision:
        precision.prec=60
        for r in records:
            if r['status']!='qualified':continue
            raw=Path(r['source_path']).read_bytes();assert sha256(raw).hexdigest()==r['source_sha256']
            for f in r['selected_facts']:
                for obj in (f,f['context_source'],f.get('unit_source')):
                    if obj is None:continue
                    start,end=obj['source_span'];assert sha256(raw[start:end]).hexdigest()==obj['fragment_sha256'];span_checks+=1
            ratio=(Fraction(Decimal(r['current_ni']))-Fraction(Decimal(r['prior_ni'])))/Fraction(Decimal(r['prior_fy_assets']))
            original_ratios[(r['symbol'],r['accession'])]=ratio
            assert abs(Decimal(r['u'])-as_decimal(ratio))<=Decimal('1e-36')*max(1,abs(as_decimal(ratio)))
        for e in events:
            if e['feature_status']!='qualified':continue
            history=[keyed[(e['symbol'],a)] for a in e['history_accessions']]
            assert len(history)==8 and [h['slot'] for h in history]==list(range(e['slot']-8,e['slot']))
            cutoff=datetime.fromisoformat(e['decision_time'] or e['availability_floor'])
            assert all(h['status']=='qualified' and datetime.fromisoformat(h['availability_floor'])<=cutoff for h in history)
            values=[original_ratios[(h['symbol'],h['accession'])] for h in history]
            mean=sum(values)/8;variance=sum((v-mean)**2 for v in values)/7
            assert variance>0
            expected=as_decimal(original_ratios[(e['symbol'],e['accession'])])/as_decimal(variance).sqrt()
            assert abs(Decimal(e['S'])-expected)<=Decimal('1e-34')*max(1,abs(expected))
            assert e['selected']==(Decimal(e['S'])>=1)
    financial=Counter(r['status'] for r in records);features=Counter(e['feature_status'] for e in events)
    assert dict(financial)==summary['financial_status'] and dict(features)==summary['feature_status']
    evaluation=[e for e in events if '2017-01-01'<=e['filing_date']<='2025-12-31']
    eligible=[e for e in evaluation if e['feature_status']=='qualified' and e.get('execution_status')=='qualified']
    out={'at':datetime.now(timezone.utc).isoformat(),'status':'passed','attempt':str(attempt),'summary_sha256':digest(attempt/'summary.json'),'original_records':len(records),'financial_status':dict(financial),'feature_status':dict(features),'source_fact_context_unit_spans':span_checks,'evaluation_originals':len(evaluation),'execution_eligible':len(eligible),'selected_eligible':sum(e['selected'] for e in eligible),'by_issuer':{s:{'financial_qualified':sum(r['symbol']==s and r['status']=='qualified' for r in records),'eligible':sum(e['symbol']==s for e in eligible),'selected':sum(e['symbol']==s and e['selected'] for e in eligible)} for s in sorted({r['symbol'] for r in records})},'unavailable_reasons':dict(Counter(reason for r in records for reason in r.get('reasons',[]))),'limitations':['Recomputes arithmetic and original byte-span identities, not an independent full XBRL parser','Source metadata and conservative availability remain retrospective proxies','No returns, prices or trading outcomes accessed']}
    target=attempt/('independent-feature-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');target.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps({'report':str(target),**out},indent=2))
    return out

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('attempt',type=Path);audit(cli.parse_args().attempt)

"""Independent Decimal quote-state audit; no network, fees, orders or strategy returns."""
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime, timezone
from collections import Counter
import json, hashlib
import pandas as pd
P=Path(__file__).resolve().parent.parent
OUT=Path(__file__).resolve().parent

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ns(text): return pd.Timestamp(text).value

def audit(rows,start,end):
    times=[ns(r['t']) for r in rows]
    assert times==sorted(times) and all(start<=t<=end for t in times)
    terminal=sum(t==end for t in times)
    pairs=[(t,r) for t,r in zip(times,rows) if t<end]
    fields=Counter(quotes=len(pairs),terminal_quotes_excluded=terminal)
    durations=Counter(valid=0,crossed=0,other=0,uncovered=pairs[0][0]-start if pairs else end-start,locked=0)
    weighted=D(0); midpoint=D(0); count_spread=D(0); values=[]
    for i,(t,r) in enumerate(pairs):
        dt=(pairs[i+1][0] if i+1<len(pairs) else end)-t
        bid,ask,bs,az=(D(str(r[k])) for k in ['bp','ap','bs','as'])
        positive=bid.is_finite() and ask.is_finite() and bid>0 and ask>0
        size=bs.is_finite() and az.is_finite() and bs>0 and az>0
        crossed=positive and ask<bid; valid=positive and size and ask>=bid
        fields['invalid_price_quotes']+=not positive; fields['invalid_size_quotes']+=not size
        if crossed:
            fields['crossed_quotes']+=1; durations['crossed']+=dt
        elif valid:
            fields['valid_quotes']+=1; durations['valid']+=dt
            spread=D(20000)*(ask-bid)/(ask+bid)
            weighted+=D(dt)*spread; midpoint+=D(dt)*(ask+bid)/2; count_spread+=spread
            if dt: values.append((spread,dt))
            if ask==bid: fields['locked_quotes']+=1; durations['locked']+=dt
        else: durations['other']+=dt
    fields['equal_timestamp_updates']=sum(a[0]==b[0] for a,b in zip(pairs,pairs[1:]))
    fields['exact_duplicate_records']=len(pairs)-len({json.dumps(r,sort_keys=True) for _,r in pairs})
    assert sum(durations[k] for k in ['valid','crossed','other','uncovered'])==end-start
    return dict(counts=dict(fields),nanoseconds=dict(durations),mean_bps=str(weighted/D(durations['valid'])) if durations['valid'] else None,count_mean_bps=str(count_spread/D(fields['valid_quotes'])) if fields['valid_quotes'] else None,midpoint_mean=str(midpoint/D(durations['valid'])) if durations['valid'] else None)

# Hand-calculated interval semantics independent of the saved float analyzer.
start=ns('2024-01-02T14:30:00Z'); end=start+60000000000
synthetic=[{'t':pd.Timestamp(start+t*1000000000,tz='UTC').isoformat(),'bp':b,'ap':a,'bs':z,'as':z} for t,b,a,z in [(5,99,101,1),(10,102,100,1),(20,100,100,1),(30,99,101,0),(40,99,101,1),(40,98,102,1),(60,99,101,1)]]
test=audit(synthetic,start,end); assert test['nanoseconds']==dict(valid=35000000000,crossed=10000000000,other=10000000000,uncovered=5000000000,locked=10000000000)
assert abs(D(test['mean_bps'])-D(9000)/35)<D('1e-20')
assert audit([],start,end)['nanoseconds']['uncovered']==60000000000


definition=json.loads((P/'cost-definition.json').read_text())
impl=json.loads((P/'implementation.json').read_text())
summary=json.loads((P/'cost-capture-summary.json').read_text())
saved=json.loads((P/'cost-analysis.json').read_text())
qualified=json.loads((P/'cost-qualification.json').read_text())
completion=json.loads((P/'completion.json').read_text())
repo=P.parents[2]
for name,h in impl['files'].items():assert digest(P/name)==h
for name,h in impl['external_files'].items():assert digest(repo/name)==h
assert saved['definition_sha256']==qualified['definition_sha256']==digest(P/'cost-definition.json')
assert len(summary)==len(definition['windows'])==3 and len(saved['cells'])==33
assert definition['symbols']==['DIA','IWM','QQQ','XLE','XLF','XLI','XLK','XLP','XLU','XLV','SPY']
cell_map={(c['window'],c['symbol']):c for c in saved['cells']};assert len(cell_map)==33
calendar={r['date']:r for r in json.loads((P/'calendar-check.json').read_text())['sessions']}
starts=[json.loads(x) for x in (P/'request-starts.jsonl').read_text().splitlines()]
assert len(starts)<=60 and [r['number'] for r in starts]==list(range(1,len(starts)+1))
checks=[];page_checks=[];all_metadata=[];invalid=[];means=[];completed=0
for w,window in zip(definition['windows'],summary,strict=True):
    assert w['id']==window['window']
    first=pd.Timestamp(w['start']);last=pd.Timestamp(w['end']);day=w['id'][:10]
    assert day in ['2016-01-04','2020-01-02','2024-01-02']
    assert first.tz_convert('America/New_York').strftime('%H:%M')=='15:59'
    assert last==pd.Timestamp(calendar[day]['close_utc']) and last-first==pd.Timedelta(minutes=1)
    assert calendar[day]['first_session_of_year']==day
    records={s:[] for s in definition['symbols']};previous_token=None;hashes=[]
    assert len(window['request_attempts'])<=20
    for page,name in enumerate(window['request_attempts'],1):
        meta=json.loads((P/name).read_text());all_metadata.append(name)
        assert meta['page']==page and meta['window']==w['id'] and meta['method']=='GET' and meta['url']==definition['endpoint']
        params=dict(symbols=','.join(definition['symbols']),start=w['start'],end=w['end'],feed='sip',sort='asc',limit=10000,asof=day,**({'page_token':previous_token} if previous_token else {}))
        assert meta['params']==params
        body=None
        if meta.get('raw_file'):
            raw=(P/meta['raw_file']).read_bytes()
            assert digest(P/meta['raw_file'])==meta['sha256'] and len(raw)==meta['bytes'] and len(raw)<=8*1024**2+1
            if meta.get('status_code')==200 and not meta.get('error'):
                body=json.loads(raw)
                for symbol,rows in body.get('quotes',{}).items():
                    assert symbol in records;records[symbol].extend(rows)
            page_checks.append({'metadata':name,'metadata_sha256':digest(P/name),'raw_sha256':meta['sha256'],'bytes':len(raw),'status_code':meta.get('status_code'),'error':meta.get('error')})
        if name in window['pages']:hashes.append(meta['sha256'])
        previous_token=body.get('next_page_token') if body is not None else None
        if page<len(window['request_attempts']):assert previous_token
    if window['complete']:
        assert window['request_attempts']==window['pages'] and previous_token is None
        assert window['request_attempts'] and body is not None
        completed+=1
    for symbol,rows in records.items():
        c=cell_map[(w['id'],symbol)]
        assert c['pagination_complete']==window['complete'] and c['capture_hashes']==hashes
        if not window['complete']:
            assert c.get('error') and 'duration_weighted_spread_bps' not in c
            checks.append({'window':w['id'],'symbol':symbol,'status':'incomplete_capture_preserved'})
            invalid.append((w['id'],symbol));continue
        independent=audit(rows,first.value,last.value)
        for key,value in independent['counts'].items():assert c.get(key,0)==value,(w['id'],symbol,key)
        for k,field in [('valid','valid_observed_seconds'),('crossed','crossed_seconds'),('other','other_invalid_seconds'),('uncovered','uncovered_seconds'),('locked','locked_seconds')]:
            assert abs(D(str(c.get(field,0)))-D(independent['nanoseconds'][k])/D(10**9))<D('1e-9')
        for key,field in [('mean_bps','duration_weighted_spread_bps'),('count_mean_bps','count_weighted_spread_bps'),('midpoint_mean','observed_midpoint_usd')]:
            actual=c.get(field)
            if independent[key] is None:assert actual is None
            else:assert actual is not None and abs(D(str(actual['mean']))-D(independent[key]))<D('1e-9')
        valid_mean=independent['mean_bps']
        if independent['nanoseconds']['valid']<59*10**9 or valid_mean is None or not D(valid_mean).is_finite() or D(valid_mean)<0:
            invalid.append((w['id'],symbol))
        else:means.append(D(valid_mean))
        checks.append(dict(window=w['id'],symbol=symbol,status='complete',**independent))
assert len(all_metadata)==len(starts)==completion['request_starts']
for name,start in zip(all_metadata,starts,strict=True):
    meta=json.loads((P/name).read_text())
    assert {k:start[k] for k in ['method','url','params']}=={k:meta[k] for k in ['method','url','params']}
raw_bytes=sum(p['bytes'] for p in page_checks)
assert raw_bytes==completion['raw_bytes'] and raw_bytes<=128*1024**2+1
assert completed==completion['complete_windows']
assert {(c['window'],c['symbol']) for c in qualified['invalid_cells']}==set(invalid)
derived=None
if invalid:
    assert qualified['status']=='unqualified' and 'round_trip_bps' not in qualified
else:
    from decimal import ROUND_CEILING
    derived=int(max(means).to_integral_value(rounding=ROUND_CEILING))+10
    assert qualified['status']=='qualified_quote_informed_sensitivity' and qualified['round_trip_bps']==derived
    assert abs(D(str(qualified['maximum_duration_weighted_full_spread_bps']))-max(means))<D('1e-9')
result={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'status':'passed','method':'Independent Decimal interval and quote arithmetic; original float analyzer not imported or rerun','tolerance':'1e-9 absolute bps/seconds/USD for float serialization','cells':len(checks),'complete_windows':completed,'pages':len(page_checks),'raw_bytes':raw_bytes,'quotes':sum(c.get('counts',{}).get('quotes',0) for c in checks),'invalid_cells':[list(x) for x in invalid],'derived_round_trip_bps':derived,'independent_maximum_mean_bps':str(max(means)) if means else None,'totals_seconds':{k:str(sum(D(c.get('nanoseconds',{}).get(k,0)) for c in checks)/D(10**9)) for k in ['valid','crossed','other','uncovered','locked']},'definition_sha256':digest(P/'cost-definition.json'),'implementation_sha256':digest(P/'implementation.json'),'analysis_sha256':digest(P/'cost-analysis.json'),'qualification_sha256':digest(P/'cost-qualification.json'),'prior_method_sha256':digest(repo/'.qualification/intraday-cost-windows20260928/independent-verification/verify_cost_windows.py'),'source_pages':page_checks,'cells_verified':checks,'limitations':['Three purposive January sessions; not a representative execution distribution','Full quote spreads and stale-carried states are not fills or capacity','Uniform maximum plus10bps is a declared sensitivity, not calibrated slippage or upper bound','Broker tariffs, fundingFX and account charges remain separate; no strategy outcomes inspected']}
with (OUT/'verification.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ['source_pages','cells_verified']},indent=2))

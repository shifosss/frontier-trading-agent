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

definition=json.loads((P/'cost-definition.json').read_text()); impl=json.loads((P/'implementation.json').read_text()); summary=json.loads((P/'cost-capture-summary.json').read_text()); saved=json.loads((P/'cost-analysis.json').read_text())
for name,sha in impl['files'].items(): assert digest(P/name)==sha
assert saved['definition_sha256']==digest(P/'cost-definition.json')
assert len(summary)==len(definition['windows'])==24 and len(saved['cells'])==144
assert definition['symbols']==['AAPL','MSFT','F','T','HRL','BANF']
cell_map={(c['window'],c['symbol']):c for c in saved['cells']}; assert len(cell_map)==144
calendar_path=P.parent/'intraday-opening20260928/calendar.json'; calendar={x['session']:x for x in json.loads(calendar_path.read_text())}
checks=[]; page_checks=[]; dates=set()
for w,window in zip(definition['windows'],summary,strict=True):
    assert w['id']==window['window'] and window['complete']
    first=pd.Timestamp(w['start']); last=pd.Timestamp(w['end']); local=first.tz_convert('America/New_York'); day=local.strftime('%Y-%m-%d'); dates.add(day)
    assert local.year in [2017,2021,2025] and local.month in [2,5,8,11] and local.dayofweek==1 and 8<=local.day<=14
    assert local.strftime('%H:%M') in ['10:46','12:46'] and last-first==pd.Timedelta(minutes=1)
    assert pd.Timestamp(calendar[day]['open'])<=first<last<=pd.Timestamp(calendar[day]['close'])
    records={s:[] for s in definition['symbols']}; previous_token=None; hashes=[]
    assert window['request_attempts']==window['pages']
    for page,name in enumerate(window['pages'],1):
        meta=json.loads((P/name).read_text()); raw=(P/meta['raw_file']).read_bytes()
        assert meta['status_code']==200 and len(raw)==meta['bytes'] and digest(P/meta['raw_file'])==meta['sha256']
        assert meta['page']==page and meta['window']==w['id'] and meta['method']=='GET' and meta['url']==definition['endpoint']
        params=meta['params']; assert params==dict(symbols=','.join(definition['symbols']),start=w['start'],end=w['end'],feed='sip',sort='asc',limit=10000,asof=day,**({'page_token':previous_token} if previous_token else {}))
        body=json.loads(raw); token=body.get('next_page_token'); assert bool(token)==(page<len(window['pages']))
        previous_token=token; hashes.append(meta['sha256']); page_checks.append({'metadata':name,'metadata_sha256':digest(P/name),'raw_sha256':meta['sha256'],'bytes':len(raw),'quotes':sum(len(z) for z in body.get('quotes',{}).values())})
        for symbol,rows in body.get('quotes',{}).items(): assert symbol in records; records[symbol].extend(rows)
    for symbol,rows in records.items():
        c=cell_map[(w['id'],symbol)]; independent=audit(rows,first.value,last.value)
        assert c['pagination_complete'] and c['capture_hashes']==hashes
        for key,value in independent['counts'].items(): assert c.get(key,0)==value,(w['id'],symbol,key,c.get(key),value)
        for k,field in [('valid','valid_observed_seconds'),('crossed','crossed_seconds'),('other','other_invalid_seconds'),('uncovered','uncovered_seconds'),('locked','locked_seconds')]: assert abs(D(str(c.get(field,0)))-D(independent['nanoseconds'][k])/D(1000000000))<D('1e-9'),(w['id'],symbol,field)
        for key,field in [('mean_bps','duration_weighted_spread_bps'),('count_mean_bps','count_weighted_spread_bps'),('midpoint_mean','observed_midpoint_usd')]:
            actual=c.get(field)
            if independent[key] is None: assert actual is None
            else: assert actual is not None and abs(D(str(actual['mean']))-D(independent[key]))<D('1e-9'),(w['id'],symbol,key)
        checks.append(dict(window=w['id'],symbol=symbol,**independent))
assert len(dates)==12
result={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'status':'passed','method':'Independent Decimal interval arithmetic following prior cost-verify methodology; saved analyzer not imported or invoked','tolerance':'1e-9 absolute seconds/bps/USD for float serialization','windows':24,'dates':sorted(dates),'cells':len(checks),'pages':len(page_checks),'quotes':sum(c['counts']['quotes'] for c in checks),'empty_cells':[c['window']+':'+c['symbol'] for c in checks if not c['counts']['quotes']],'totals_seconds':{k:str(sum(D(c['nanoseconds'][k]) for c in checks)/D(1000000000)) for k in ['valid','crossed','other','uncovered','locked']},'frozen_files_verified':impl['files'],'source_analysis_sha256':digest(P/'cost-analysis.json'),'calendar_sha256':digest(calendar_path),'prior_method_sha256':digest(P.parent/'daily-model-bridge/cost-verify.py'),'source_pages':page_checks,'cells_verified':checks,'limitations':['Quoted states after fixed clocks, not actual fills, slippage or total fees','No pre-window quote carry; leading/empty periods uncovered, not proof of absent market quotes','No stale timeout or condition-specific executability qualification','Six surviving pilot symbols,12fixed dates,2windows; not universe-wide calibration','No fee changes or strategy outcomes used']}
(OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['source_pages','cells_verified','frozen_files_verified']},indent=2))

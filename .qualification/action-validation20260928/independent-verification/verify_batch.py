"""Bounded source-only verification. No network, Frontier/model/performance imports."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D, getcontext
import hashlib, json, math
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

getcontext().prec=70
ROOT=Path(__file__).resolve().parents[3]
BATCH=Path(__file__).resolve().parent.parent
OUT=Path(__file__).resolve().parent
INVENTORY=ROOT/'.qualification/action-inventory20260928'
NY=ZoneInfo('America/New_York')
def digest(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def dec(x):return D(str(x))
def close(a,b):assert abs(dec(a)-dec(b)) <= D('1e-40')*max(D(1),abs(dec(b))),(a,b)
def uncertainty(x):return max(D('0.0005'),abs(x)*D('0.0000005'))
def interval(x,volume=False):
    q=D(1) if volume else uncertainty(x)
    return x-q,x+q

def factor_check(a,b,c,d,expected,volume=False):
    # (split/raw) before divided by (split/raw) after: a*d/(b*c).
    observed=a*d/(b*c) if min(a,b,c,d)>0 else None
    if observed is None:return dict(status='unresolved_zero_volume' if volume else 'unresolved_nonpositive_price')
    bounds=[interval(v,volume) for v in [a,b,c,d]]
    if min(x[0] for x in bounds)<=0:return dict(status='unresolved_precision_insufficient')
    lo=bounds[0][0]*bounds[3][0]/(bounds[1][1]*bounds[2][1])
    hi=bounds[0][1]*bounds[3][1]/(bounds[1][0]*bounds[2][0])
    width=(hi-lo)/expected
    status='consistent' if lo<=expected<=hi else 'inconsistent'
    if not volume and width>D('0.02'):status='unresolved_precision_insufficient'
    return dict(status=status,observed=str(observed),interval=[str(lo),str(hi)],relative_width=str(width))

raw_definition=(BATCH/'definition.json').read_bytes();definition=json.loads(raw_definition)
sample_bytes=(INVENTORY/'validation-sample.csv').read_bytes()
assert digest(sample_bytes)==definition['sample_sha256']
sample=list(csv.DictReader(sample_bytes.decode('utf-8-sig').splitlines()))
assert len(sample)==definition['sample_total']==91
assert len({(r['symbol'],r['event_key'],r['source_sha256']) for r in sample})==91
inventory_definition=load(INVENTORY/'definition.json')
seed=inventory_definition['followup_sample']['seed']
groups=defaultdict(list)
for line in (INVENTORY/'events.jsonl').read_text().splitlines():
    row=json.loads(line)
    if row['status']!='valid_event' or row['currency'] not in ['USD','CAD'] or row['direction']=='neutral' or not row['effective_by_cutoff']:continue
    year=int(row['effective_session'][:4]);era='<=2009' if year<=2009 else '2010-2019' if year<=2019 else '2020-2023' if year<=2023 else '2024-2026'
    magnitude=max(row['new_shares_per_old'],1/row['new_shares_per_old']);size='<=2' if magnitude<=2 else '>2'
    liquidity=row['prior20_native_dollar_volume_proxy'];activity='unavailable' if liquidity is None else '<1000000' if liquidity<1_000_000 else '>=1000000'
    cell='|'.join([row['currency'],row['direction'],era,size,activity])
    identity=f"{seed}|{row['symbol']}|{row['effective_session']}|{row['numerator']}:{row['denominator']}"
    groups[cell].append((digest(identity.encode()),row))
assert len(groups)==91
for row in sample:
    rank,event=min(groups[row['stratum']],key=lambda x:x[0])
    assert row['sample_rank_sha256']==rank and int(row['stratum_events'])==len(groups[row['stratum']])
    assert all(str(event[k])==row[k] for k in ['symbol','event_key','source_sha256','effective_session','numerator','denominator'])
selected={(r['symbol'],r['effective_session']):r for r in sample if r['currency']=='USD' and r['effective_session']>='2016-01-04'}
declared={(r['symbol'],r['effective_session']):r for r in definition['selected']}
assert set(selected)==set(declared) and len(selected)==24 and len({s for s,d in selected})==23
for key,row in selected.items():
    assert row['stratum']==declared[key]['stratum'] and float(row['new_shares_per_old'])==declared[key]['ratio']
pending=[dict(symbol=r['symbol'],effective_session=r['effective_session'],stratum=r['stratum'],source_sha256=r['source_sha256'],status='pending_not_in_this_batch') for r in sample if (r['symbol'],r['effective_session']) not in selected]
assert len(pending)==67
request_files=sorted(p for p in BATCH.glob('*.capture.json') if load(p).get('params',{}).get('adjustment') in ['raw','split'])
assert len(request_files)==48
captures={};request_audit=[]
for path in request_files:
    meta=load(path);key=(meta['symbol'],meta['effective_session']);assert key in selected
    params=meta['params'];adjustment=params['adjustment'];assert adjustment in ['raw','split']
    event=datetime.fromisoformat(key[1]).replace(tzinfo=NY)
    start=event-timedelta(days=10);end=min(event+timedelta(days=11),datetime(2026,9,19,tzinfo=NY))-timedelta(microseconds=1)
    expected=dict(timeframe='1Day',start=start.astimezone(timezone.utc).isoformat(),end=end.astimezone(timezone.utc).isoformat(),feed='sip',adjustment=adjustment,asof='2026-09-18',currency='USD',limit=10000,sort='asc')
    assert params==expected
    url=urlparse(meta['url']);assert url.scheme=='https' and url.netloc=='data.alpaca.markets' and url.path==f'/v2/stocks/{key[0]}/bars'
    assert parse_qs(url.query)=={k:[str(v)] for k,v in expected.items()}
    assert meta['method']=='GET' and meta['status']=='response_retained' and meta['status_code']==200
    assert datetime.fromisoformat(meta['started_at'])>=datetime.fromisoformat(definition['declared_at'])
    assert datetime.fromisoformat(meta['captured_at'])>=datetime.fromisoformat(meta['started_at'])
    raw_path=BATCH/meta['raw_file'];assert raw_path.parent==BATCH
    content=raw_path.read_bytes();assert digest(content)==meta['sha256'] and len(content)==meta['bytes']
    payload=json.loads(content,parse_float=D);assert payload.get('symbol')==key[0] and not payload.get('next_page_token')
    bars=payload.get('bars') or [];assert len(bars)==meta['bar_count'] and meta['pagination_complete'] is True
    mapped={}
    for bar in bars:
        timestamp=datetime.fromisoformat(bar['t'].replace('Z','+00:00'));label=timestamp.astimezone(NY).date().isoformat()
        assert start<=timestamp<=end and label not in mapped
        mapped[label]=bar
    assert list(mapped)==sorted(mapped)
    assert (key,adjustment) not in captures;captures[key,adjustment]=mapped
    request_audit.append(dict(file=path.name,sha256=meta['sha256'],bar_count=len(bars),sessions=list(mapped)))
assert all((key,a) in captures for key in selected for a in ['raw','split'])
analysis=load(BATCH/'bar-factor-results.json');assert len(analysis)==24
analysis={(r['symbol'],r['effective_session']):r for r in analysis};assert set(analysis)==set(selected)
results=[];source_count=set();boundary_counts=Counter();classification_differences=[]
for key,row in selected.items():
    source_path=(ROOT/'data/historical/capture-workspace'/row['source_path']).resolve()
    assert source_path.is_relative_to(ROOT/'data/historical/capture-workspace/data/scanner/raw')
    content=source_path.read_bytes();assert digest(content)==row['source_sha256'];source_count.add(row['source_sha256'])
    payload=json.loads(content)['chart']['result'][0]
    raw_event=payload['events']['splits'][row['event_key']]
    assert raw_event==json.loads(row['event_raw_json'])
    assert datetime.fromtimestamp(raw_event['date'],timezone.utc).astimezone(NY).date().isoformat()==key[1]
    dates=[datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat() for t in payload['timestamp']]
    assert len(set(dates))==len(dates)
    prior=max([s for s in dates if s<key[1]],default=None)
    assert prior==row['prior_session']
    boundary={};reported=analysis[key]
    assert reported['prior_session']==prior
    capture_day=datetime.fromisoformat(row['captured_at']).astimezone(NY).date().isoformat()
    for label,session in [('prior',prior),('effective',key[1])]:
        raw=captures[key,'raw'].get(session);split=captures[key,'split'].get(session)
        source_index=dates.index(session) if session in dates else None
        values=dict(session=session,independent_raw=raw is not None,independent_split=split is not None)
        if source_index is not None:
            close_value=payload['indicators']['quote'][0]['close'][source_index]
            factors=[float(ev['numerator'])/float(ev['denominator']) for ev in payload.get('events',{}).get('splits',{}).values() if session<datetime.fromtimestamp(ev['date'],timezone.utc).astimezone(NY).date().isoformat()<=capture_day]
            nominal=float(close_value)*math.prod(factors) if close_value is not None else None
            if nominal is not None:
                assert math.isclose(nominal,float(row[label+'_reconstructed_nominal_close']),rel_tol=1e-12,abs_tol=1e-12)
            if nominal is not None and raw is not None:
                a,b=dec(nominal),dec(raw['c']);band=uncertainty(a)+uncertainty(b)
                status='agrees_within_precision' if abs(a-b)<=band else 'discrepancy'
                values.update(nominal_source=str(a),independent_raw_close=str(b),difference=str(a-b),uncertainty_sum=str(band),status=status)
            else:values['status']='missing'
        else:values['status']='missing'
        boundary_counts[values['status']]+=1
        assert values['status']==reported['boundaries'].get(label,{}).get('nominal_comparison','missing'),(key,label,values,reported['boundaries'].get(label))
        boundary[label]=values
    expected=dec(raw_event['denominator'])/dec(raw_event['numerator'])
    close(expected,reported['expected_price_factor'])
    if any(x not in captures[key,a] for x in [prior,key[1]] for a in ['raw','split']):
        price=volume=dict(status='unresolved_missing_boundary')
    else:
        before_raw,before_split=captures[key,'raw'][prior],captures[key,'split'][prior]
        after_raw,after_split=captures[key,'raw'][key[1]],captures[key,'split'][key[1]]
        price=factor_check(*(dec(x['c']) for x in [before_split,before_raw,after_split,after_raw]),expected)
        volume=factor_check(*(dec(x['v']) for x in [before_split,before_raw,after_split,after_raw]),1/expected,volume=True)
    assert price['status']==reported['price_factor_status'],(key,price,reported['price_factor_status'])
    if volume['status']!=reported.get('volume_factor_status','unresolved_missing_boundary'):
        classification_differences.append(dict(symbol=key[0],effective_session=key[1],dimension='volume',independent=volume['status'],reported=reported.get('volume_factor_status'),reason='Positive integer volume of one has declared plus/minus-one interval touching zero; a finite factor is unidentifiable, not contradicted.'))
    if 'observed' in price:
        close(price['observed'],reported['observed_price_factor'])
        for a,b in zip(price['interval'],reported['price_factor_interval']):close(a,b)
        close(price['relative_width'],reported['relative_interval_width'])
    if 'observed' in volume:
        close(volume['observed'],reported['observed_volume_factor'])
        for a,b in zip(volume['interval'],reported['volume_factor_interval']):close(a,b)
    results.append(dict(symbol=key[0],effective_session=key[1],source_sha256=row['source_sha256'],expected_price_factor=str(expected),price=price,volume=volume,boundaries=boundary))
summary=dict(status='passed_with_reported_classification_difference' if classification_differences else 'passed',scope='Source evidence and arithmetic only; no network/model/PnL/journal access or correction',
             script_sha256=digest(Path(__file__).read_bytes()),definition_sha256=digest(raw_definition),sample_sha256=digest(sample_bytes),
             sample_identities_and_stratum_minima=91,batch_events=24,batch_symbols=23,pending_outside_batch=67,
             request_count=48,retained_response_hashes_verified=48,raw_source_hashes_verified=len(source_count),
             retained_bars=sum(r['bar_count'] for r in request_audit),
             price_status_counts=dict(Counter(r['price']['status'] for r in results)),
             volume_status_counts=dict(Counter(r['volume']['status'] for r in results)),nominal_boundary_counts=dict(boundary_counts),
             classification_differences=classification_differences,matched_analysis_sha256=digest((BATCH/'bar-factor-results.json').read_bytes()),
             assumptions=['Current symbol plus fixed asof=2026-09-18 is a requested entity mapping, not independent predecessor-security verification.',
                          'Fresh raw/split bars do not freeze historical adjustment vintage or contemporaneous availability.',
                          'America/New_York dates are independently recomputed from retained timestamps; exact source prior/effective sessions are never forward-filled.',
                          'Price and volume consistency do not establish legal action type, notices, entitlements, cash-in-lieu or full accounting.',
                          'All strict predeclared tolerances retained; near misses stay inconsistent and missing cases stay unresolved.'])
(OUT/'verification.json').write_text(json.dumps(dict(summary=summary,requests=request_audit,events=results,pending_cases=pending),indent=2)+'\n')
print(json.dumps(summary),flush=True)

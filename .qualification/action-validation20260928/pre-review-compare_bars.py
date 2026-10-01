"""Offline source-only comparisons; never reads strategy returns or account files."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, localcontext
import csv, hashlib, json

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
INVENTORY=ROOT.parent/'action-inventory20260928'
D=Decimal
NY=ZoneInfo('America/New_York')

def load(path):
    return json.loads(path.read_text(encoding='utf-8'),parse_float=D)
def uncertainty(value):
    return max(D('0.0005'),abs(value)*D('0.0000005'))
def ratio_interval(numerators,denominators,volume=False):
    low=high=D(1)
    for value in numerators:
        u=D(1) if volume else uncertainty(value)
        if value-u<=0:return None
        low*=value-u;high*=value+u
    for value in denominators:
        u=D(1) if volume else uncertainty(value)
        if value-u<=0:return None
        low/=value+u;high/=value-u
    return low,high
def serialized(value):
    return str(value) if isinstance(value,D) else value
def dump(name, value):
    (ROOT/name).write_text(json.dumps(value,indent=2,default=serialized,allow_nan=False),encoding='utf-8')
def bars_for(event,adjustment):
    pages=sorted(ROOT.glob(f"{event['symbol']}-{event['effective_session']}-{adjustment}-*.capture.json"))
    bars={};captures=[]
    for path in pages:
        meta=load(path);raw=ROOT/meta['raw_file']
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==meta['sha256']
        captures.append(meta)
        if meta['status_code']!=200:continue
        for bar in load(raw).get('bars') or []:
            session=datetime.fromisoformat(bar['t'].replace('Z','+00:00')).astimezone(NY).date().isoformat()
            assert session not in bars, (event,adjustment,session)
            bars[session]=bar
    return bars,captures
def main():
    definition=load(ROOT/'definition.json')
    sample_path=INVENTORY/'validation-sample.csv'
    assert hashlib.sha256(sample_path.read_bytes()).hexdigest()==definition['sample_sha256']
    sample=list(csv.DictReader(sample_path.open(encoding='utf-8',newline='')))
    by_id={(row['symbol'],row['effective_session']):row for row in sample}
    results=[];window_rows=[]
    with localcontext() as ctx:
        ctx.prec=50
        for event in definition['selected']:
            row=by_id[event['symbol'],event['effective_session']]
            source_path=REPO/'data/historical/capture-workspace'/row['source_path']
            assert hashlib.sha256(source_path.read_bytes()).hexdigest()==row['source_sha256']
            raw,raw_captures=bars_for(event,'raw');split,split_captures=bars_for(event,'split')
            prior=row['prior_session'];effective=row['effective_session']
            out=dict(symbol=row['symbol'],effective_session=effective,prior_session=prior,
                     source_path=str(source_path),source_sha256=row['source_sha256'],
                     raw_capture_files=[c['raw_file'] for c in raw_captures],split_capture_files=[c['raw_file'] for c in split_captures],
                     expected_price_factor=D(row['denominator'])/D(row['numerator']),
                     expected_volume_factor=D(row['numerator'])/D(row['denominator']),
                     raw_sessions=list(raw),split_sessions=list(split),boundaries={},price_factor_status='unresolved_missing_boundary')
            for session in sorted(set(raw)|set(split)):
                window_rows.append(dict(symbol=row['symbol'],effective_session=effective,session=session,raw=raw.get(session),split=split.get(session)))
            missing=[]
            for label,session in [('prior',prior),('effective',effective)]:
                if session not in raw or session not in split:
                    missing.append(dict(boundary=label,required_session=session,raw_present=session in raw,split_present=session in split))
                    continue
                nominal=D(row[label+'_reconstructed_nominal_close'])
                rv=D(str(raw[session]['c']));sv=D(str(split[session]['c']))
                delta=nominal-rv
                band=uncertainty(nominal)+uncertainty(rv)
                source_volume=D(row[label+'_reconstructed_nominal_volume'])
                out['boundaries'][label]=dict(session=session,source_timestamp=row[label+'_timestamp'],
                    source_provider_close=row[label+'_provider_close'],source_adjusted_close=row[label+'_provider_adjclose'],
                    source_nominal_close=nominal,source_provider_volume=row[label+'_provider_volume'],
                    source_nominal_volume=source_volume,raw=raw[session],split=split[session],
                    nominal_delta=delta,nominal_precision_band=band,
                    nominal_comparison='agrees_within_precision' if abs(delta)<=band else 'discrepancy',
                    volume_nominal_delta=source_volume-D(str(raw[session]['v'])))
            out['missing_boundaries']=missing
            if not missing:
                a,b=out['boundaries']['prior'],out['boundaries']['effective']
                rp,sp,re,se=[D(str(v)) for v in [a['raw']['c'],a['split']['c'],b['raw']['c'],b['split']['c']]]
                observed=sp*re/(rp*se);bounds=ratio_interval([sp,re],[rp,se])
                out['observed_price_factor']=observed
                out['price_factor_interval']=bounds
                if bounds is None:out['price_factor_status']='unresolved_nonpositive_precision_boundary'
                else:
                    width=(bounds[1]-bounds[0])/out['expected_price_factor']
                    out['relative_interval_width']=width
                    if width>D('.02'):out['price_factor_status']='unresolved_precision_insufficient'
                    elif bounds[0]<=out['expected_price_factor']<=bounds[1]:out['price_factor_status']='consistent'
                    else:out['price_factor_status']='inconsistent'
                vrp,vsp,vre,vse=[D(str(v)) for v in [a['raw']['v'],a['split']['v'],b['raw']['v'],b['split']['v']]]
                volume_bounds=ratio_interval([vsp,vre],[vrp,vse],True)
                out['volume_factor_interval']=volume_bounds
                if min(vrp,vsp,vre,vse)<=0:out['volume_factor_status']='unresolved_zero_volume'
                else:
                    out['observed_volume_factor']=vsp*vre/(vrp*vse)
                    out['volume_factor_status']='consistent' if volume_bounds and volume_bounds[0]<=out['expected_volume_factor']<=volume_bounds[1] else 'inconsistent'
            results.append(out)
    dump('bar-factor-results.json',results);dump('bar-windows.json',window_rows)
    slim=[dict(symbol=r['symbol'],effective_session=r['effective_session'],prior_session=r['prior_session'],
        expected_price_factor=r['expected_price_factor'],observed_price_factor=r.get('observed_price_factor'),
        price_factor_status=r['price_factor_status'],volume_factor_status=r.get('volume_factor_status','unresolved_missing_boundary'),
        prior_nominal=r['boundaries'].get('prior',{}).get('nominal_comparison','missing'),
        effective_nominal=r['boundaries'].get('effective',{}).get('nominal_comparison','missing')) for r in results]
    with (ROOT/'bar-factor-summary.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(slim[0]));writer.writeheader();writer.writerows(slim)
    print(json.dumps(slim,indent=2,default=serialized))
if __name__=='__main__':main()


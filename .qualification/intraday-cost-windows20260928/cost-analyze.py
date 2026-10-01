"""Offline multi-window analyzer adapted from cost-access20260919/analyze_saved.py."""
import json, hashlib
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
def statistics(values, weights):
    selected = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values,weights = values[selected],weights[selected]
    if not len(values):
        return None
    order = np.argsort(values, kind='stable')
    sorted_values, ordered_weights = values[order],weights[order]
    cumulative = np.cumsum(ordered_weights)/ordered_weights.sum()
    result = {'mean':float(np.average(values, weights=weights)), 'min':float(values.min()), 'max':float(values.max())}
    for q in [0.05,0.5,0.9,0.95,0.99]:
        result[f'p{int(q*100):02}'] = float(sorted_values[min(np.searchsorted(cumulative,q,side='left'),len(values)-1)])
    return result


def analyze(rows,start,end):
    if not rows:
        return {'quotes':0,'valid_observed_seconds':0.,'crossed_seconds':0.,'other_invalid_seconds':0.,'uncovered_seconds':(end-start)/1e9,'duration_weighted_spread_bps':None,'count_weighted_spread_bps':None}
    times=pd.DatetimeIndex(pd.to_datetime([r['t'] for r in rows],utc=True,format='ISO8601')).as_unit('ns').asi8
    assert (np.diff(times)>=0).all()
    assert ((times>=start)&(times<=end)).all()
    terminal=int((times==end).sum()); rows=[r for r,t in zip(rows,times) if t<end]; times=times[times<end]
    if not rows: return analyze([],start,end)
    f=pd.DataFrame(rows); bp=f.bp.to_numpy(float); ap=f.ap.to_numpy(float); bs=f.bs.to_numpy(float); az=f['as'].to_numpy(float)
    positive_price=np.isfinite(bp)&np.isfinite(ap)&(bp>0)&(ap>0)
    positive_size=np.isfinite(bs)&np.isfinite(az)&(bs>0)&(az>0)
    crossed=positive_price&(ap<bp); valid=positive_price&positive_size&(ap>=bp)
    durations=(np.r_[times[1:],end]-times)/1e9
    with np.errstate(divide='ignore',invalid='ignore'): spreads=10000*(ap-bp)/((ap+bp)/2)
    leading=float((times[0]-start)/1e9)
    valid_seconds=float(durations[valid].sum()); crossed_seconds=float(durations[crossed].sum()); other_seconds=float(durations[~valid&~crossed].sum())
    assert abs(valid_seconds+crossed_seconds+other_seconds+leading-(end-start)/1e9)<1e-8
    return {'quotes':len(rows),'terminal_quotes_excluded':terminal,'valid_quotes':int(valid.sum()),'crossed_quotes':int(crossed.sum()),'invalid_price_quotes':int((~positive_price).sum()),'invalid_size_quotes':int((~positive_size).sum()),'locked_quotes':int((valid&(ap==bp)).sum()),'valid_observed_seconds':valid_seconds,'crossed_seconds':crossed_seconds,'other_invalid_seconds':other_seconds,'uncovered_seconds':leading,'locked_seconds':float(durations[valid&(ap==bp)].sum()),'longest_quote_state_seconds':float(durations.max()),'equal_timestamp_updates':int((np.diff(times)==0).sum()),'exact_duplicate_records':len(rows)-len({json.dumps(r,sort_keys=True) for r in rows}),'first_timestamp':rows[0]['t'],'last_timestamp':rows[-1]['t'],'conditions':dict(Counter(json.dumps(r.get('c')) for r in rows)),'bid_exchange_codes':sorted(f.bx.unique().tolist()),'ask_exchange_codes':sorted(f.ax.unique().tolist()),'tapes':sorted(f.z.unique().tolist()),'observed_midpoint_usd':statistics((ap+bp)/2,np.where(valid,durations,0.)),'count_weighted_spread_bps':statistics(spreads,np.where(valid,1.,0.)),'duration_weighted_spread_bps':statistics(spreads,np.where(valid,durations,0.))}
def main():
    definition=json.loads((ROOT/'cost-definition.json').read_text()); summary=json.loads((ROOT/'cost-capture-summary.json').read_text()); cells=[]
    for w,s in zip(definition['windows'],summary,strict=True):
        assert w['id']==s['window']
        records={symbol:[] for symbol in definition['symbols']}; hashes=[]
        for name in s['pages']:
            meta=json.loads((ROOT/name).read_text()); raw=(ROOT/meta['raw_file']).read_bytes(); assert hashlib.sha256(raw).hexdigest()==meta['sha256']; hashes.append(meta['sha256'])
            if meta['status_code']==200:
                body=json.loads(raw)
                for symbol,rows in body.get('quotes',{}).items(): assert symbol in records; records[symbol].extend(rows)
        for symbol,rows in records.items():
            result={'window':w['id'],'symbol':symbol,'pagination_complete':s['complete'],'capture_hashes':hashes}
            if s['complete']: result.update(analyze(rows,pd.Timestamp(w['start']).value,pd.Timestamp(w['end']).value))
            else: result['error']='incomplete capture; no full-window statistics'
            cells.append(result)
    (ROOT/'cost-analysis.json').write_text(json.dumps({'definition_sha256':hashlib.sha256((ROOT/'cost-definition.json').read_bytes()).hexdigest(),'cells':cells},indent=2,allow_nan=False),encoding='utf-8')
    lines=['| Date / time ET | Symbol | Updates | Midpoint USD mean | Spread mean / median / p95 bps | Valid / crossed / other invalid / uncovered seconds |','| --- | --- | ---: | ---: | --- | --- |']
    for c in cells:
        d=c.get('duration_weighted_spread_bps'); midpoint=c.get('observed_midpoint_usd')
        spread=' / '.join(f'{d[k]:.3f}' for k in ['mean','p50','p95']) if d else 'missing'
        duration=' / '.join(f'{c.get(k,0):.6f}' for k in ['valid_observed_seconds','crossed_seconds','other_invalid_seconds','uncovered_seconds'])
        lines.append('| '+c['window']+' | '+c['symbol']+' | '+str(c.get('quotes',0))+' | '+(f"{midpoint['mean']:.3f}" if midpoint else 'missing')+' | '+spread+' | '+duration+' |')
    (ROOT/'cost-all-cells.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'cells':len(cells),'quotes':sum(c.get('quotes',0) for c in cells),'empty':sum(c.get('quotes',0)==0 for c in cells),'valid_seconds':sum(c.get('valid_observed_seconds',0) for c in cells),'crossed_seconds':sum(c.get('crossed_seconds',0) for c in cells),'other_invalid_seconds':sum(c.get('other_invalid_seconds',0) for c in cells),'uncovered_seconds':sum(c.get('uncovered_seconds',0) for c in cells),'symbol_means':{symbol:[round(c['duration_weighted_spread_bps']['mean'],3) if c.get('duration_weighted_spread_bps') else None for c in cells if c['symbol']==symbol] for symbol in definition['symbols']}},indent=2))
if __name__=='__main__': main()

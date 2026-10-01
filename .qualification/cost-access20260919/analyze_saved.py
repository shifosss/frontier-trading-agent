"""Analyze the fixed SIP quote fixture offline; no network, account or order access."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent
definition = json.loads((root/'probe-definition.json').read_text())
summary = json.loads((root/'probe-summary.json').read_text())
start = pd.Timestamp(definition['params']['start']).value
end = pd.Timestamp(definition['params']['end']).value
records = {name: [] for name in ('AAPL','MSFT','F')}
identities = []
for path in sorted(root.glob('quotes-page-*.capture.json')):
    meta = json.loads(path.read_text())
    raw = (root/meta['raw_file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    assert meta['status_code'] == 200
    body = json.loads(raw)
    for symbol, values in body['quotes'].items():
        assert symbol in records
        records[symbol].extend(values)
    identities.append({'page':meta['page'], 'sha256':meta['sha256'], 'raw_file':meta['raw_file']})
assert not summary['pagination_incomplete'], 'Do not infer full-window statistics from truncated pages'

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

result = {'window_start':definition['params']['start'], 'window_end_exclusive':definition['params']['end'], 'feed':'sip', 'capture_hashes':identities, 'pagination_complete':True, 'quantiles':'inverse empirical weighted CDF; no interpolation', 'quote_size_units':'raw provider round-lot units; no share-capacity inference', 'symbols':{}}
for symbol, values in records.items():
    assert values
    all_times = pd.DatetimeIndex(pd.to_datetime([row['t'] for row in values],utc=True)).as_unit('ns').asi8
    assert (np.diff(all_times) >= 0).all(), 'Provider quote ordering changed'
    assert ((all_times >= start) & (all_times <= end)).all()
    terminal = int((all_times == end).sum())
    rows = [row for row,time in zip(values,all_times) if time < end]
    times = all_times[all_times < end]
    frame = pd.DataFrame(rows)
    bp,ap = frame.bp.to_numpy(float),frame.ap.to_numpy(float)
    bs,asks = frame.bs.to_numpy(float),frame['as'].to_numpy(float)
    positive_price = np.isfinite(bp) & np.isfinite(ap) & (bp>0) & (ap>0)
    positive_size = np.isfinite(bs) & np.isfinite(asks) & (bs>0) & (asks>0)
    noncrossed = ap >= bp
    valid = positive_price & positive_size & noncrossed
    locked = positive_price & (ap==bp)
    crossed = positive_price & (ap<bp)
    with np.errstate(divide='ignore', invalid='ignore'):
        spread = 10000*(ap-bp)/((ap+bp)/2)
    durations = (np.r_[times[1:],end] - times)/1e9
    assert (durations>=0).all()
    valid_seconds = float(durations[valid].sum())
    invalid_seconds = float(durations[~valid].sum())
    leading = float((times[0]-start)/1e9)
    assert abs(valid_seconds + invalid_seconds + leading - 60) < 1e-8
    serial = [json.dumps(row,sort_keys=True,separators=(',',':')) for row in rows]
    conditions = Counter(json.dumps(row.get('c'),sort_keys=True) for row in rows)
    result['symbols'][symbol] = {
        'quotes':len(rows), 'quotes_exactly_at_end':terminal, 'first_timestamp':rows[0]['t'], 'last_timestamp':rows[-1]['t'],
        'mechanically_valid_quotes':int(valid.sum()), 'invalid_price_quotes':int((~positive_price).sum()), 'invalid_size_quotes':int((~positive_size).sum()),
        'noninteger_positive_size_quotes':int((positive_size & ((bs!=np.floor(bs)) | (asks!=np.floor(asks)))).sum()),
        'locked_quotes':int(locked.sum()), 'crossed_quotes':int(crossed.sum()), 'exact_duplicate_records':len(serial)-len(set(serial)), 'equal_timestamp_updates':int((np.diff(times)==0).sum()),
        'conditions':[{'codes':json.loads(code),'count':count} for code,count in sorted(conditions.items())],
        'bid_exchange_codes':sorted(frame.bx.unique().tolist()), 'ask_exchange_codes':sorted(frame.ax.unique().tolist()), 'tapes':sorted(frame.z.unique().tolist()),
        'bid_size_raw':{'min':float(bs.min()),'median':float(np.median(bs)),'max':float(bs.max())},
        'ask_size_raw':{'min':float(asks.min()),'median':float(np.median(asks)),'max':float(asks.max())},
        'count_weighted_spread_bps':statistics(spread,np.where(valid,1.,0.)),
        'duration_weighted_spread_bps':statistics(spread,np.where(valid,durations,0.)),
        'valid_observed_seconds':valid_seconds, 'valid_duration_fraction_of_window':valid_seconds/60,
        'invalid_observed_seconds':invalid_seconds, 'uncovered_leading_seconds':leading,
        'longest_quote_state_seconds':float(durations.max()), 'locked_observed_seconds':float(durations[locked & valid].sum()),
    }
result['limitations'] = [
    'One fixed early-close minute for three stocks, selected independently of strategy results; not a representative liquidity distribution.',
    'Full quoted spread divided by contemporaneous midpoint, not actual fills, effective spread, slippage, impact, latency, broker charges or all-in round-trip costs.',
    'Time weighting assumes a quote persists to the next observed update; equal-timestamp updates give zero time to all but the last provider record.',
    'Mechanically positive/noncrossed quotes retain all raw conditions; eligibility for execution was not independently certified.',
    'No pre-window quote is available; the leading milliseconds remain uncovered. No terminal quote is carried beyond the declared close.',
    'Historical corrected quotes are the retrieved provider vintage; asof maps symbol identity, not a historical information vintage.',
    'The current daily study cost scenarios and completed results are unchanged; any expanded execution-cost experiment requires its own predeclared sampling design.',
]
(root/'quote-analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({symbol:{key:row[key] for key in ['quotes','mechanically_valid_quotes','locked_quotes','crossed_quotes','conditions','valid_observed_seconds','uncovered_leading_seconds','count_weighted_spread_bps','duration_weighted_spread_bps']} for symbol,row in result['symbols'].items()},indent=2))

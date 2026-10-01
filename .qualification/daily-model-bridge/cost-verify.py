"""Offline hand-calculated edge cases, calendar and Decimal independent audit."""
import importlib.util, json, hashlib
from decimal import Decimal as D
from pathlib import Path
import pandas as pd
import exchange_calendars as xc
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cost_analyze',P/'cost-analyze.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
s=pd.Timestamp('2024-01-02T14:30:00Z').value; e=s+60*10**9
def quote(t,b,a,size=1): return {'t':pd.Timestamp(s+t*10**9,tz='UTC').isoformat(),'bp':b,'ap':a,'bs':size,'as':size,'bx':'N','ax':'N','z':'A','c':['R']}
rows=[quote(5,99,101),quote(10,102,100),quote(20,100,100),quote(30,99,101,0),quote(40,99,101),quote(40,98,102),quote(60,99,101)]
r=module.analyze(rows,s,e)
assert r['valid_observed_seconds']==35 and r['crossed_seconds']==10 and r['other_invalid_seconds']==10 and r['uncovered_seconds']==5
assert r['locked_seconds']==10 and r['equal_timestamp_updates']==1 and r['terminal_quotes_excluded']==1
assert abs(r['duration_weighted_spread_bps']['mean']-9000/35)<1e-10
assert r['duration_weighted_spread_bps']['p50']==400
assert module.analyze([],s,e)['uncovered_seconds']==60
calendar=xc.get_calendar('XNYS',start='2016-01-01',end='2024-01-03'); schedule=[]
for day in ['2016-01-04','2020-01-02','2024-01-02']:
    opening=calendar.session_open(day); close=calendar.session_close(day)
    assert opening.tz_convert('America/New_York').strftime('%H:%M')=='09:30'
    assert close.tz_convert('America/New_York').strftime('%H:%M')=='16:00'
    schedule.append({'date':day,'open':str(opening),'close':str(close)})
cells=json.loads((P/'cost-analysis.json').read_text())['cells']; raw_total=0; crossed_ns=0; valid_ns=0; uncovered_ns=0
for w in json.loads((P/'cost-definition.json').read_text())['windows']:
    records={}
    for m in sorted(P.glob('cost-'+w['id']+'-page-*.capture.json')):
        meta=json.loads(m.read_text()); raw=(P/meta['raw_file']).read_bytes(); assert hashlib.sha256(raw).hexdigest()==meta['sha256']; assert meta['status_code']==200
        for sym,rows in json.loads(raw)['quotes'].items(): records.setdefault(sym,[]).extend(rows)
    for sym,rows in records.items():
        start=pd.Timestamp(w['start']).value; end=pd.Timestamp(w['end']).value
        rows=[r for r in rows if pd.Timestamp(r['t']).value<end]
        weighted=D(0); valid=0; crossing=0
        for i,r in enumerate(rows):
            t=pd.Timestamp(r['t']).value; next_t=pd.Timestamp(rows[i+1]['t']).value if i+1<len(rows) else end
            duration=next_t-t; bid=D(str(r['bp'])); ask=D(str(r['ap']))
            if ask<bid: crossing+=duration
            elif bid>0 and ask>0 and r['bs']>0 and r['as']>0:
                valid+=duration; weighted+=D(duration)*D(20000)*(ask-bid)/(ask+bid)
        c=next(c for c in cells if c['window']==w['id'] and c['symbol']==sym)
        assert abs(float(weighted/D(valid))-c['duration_weighted_spread_bps']['mean'])<1e-9
        raw_total+=len(rows); crossed_ns+=crossing; valid_ns+=valid; uncovered_ns+=pd.Timestamp(rows[0]['t']).value-start
fees=[]
for price in [D('1'),D('5'),D('10'),D('50'),D('100'),D('400')]:
    def side(q): return max(D('.99'),D('.0049')*q)+max(D('1'),D('.005')*q)
    quantity=int(D('400')/price)
    while quantity>0 and quantity*price+side(quantity)>400: quantity-=1
    notional=quantity*price; fee=side(quantity) if quantity else D(0); sec=max(D('.01'),notional*D('.0000206')) if quantity else D(0)
    fees.append({'price':str(price),'whole_shares':quantity,'notional':str(notional),'buy_fee':str(fee),'round_trip_broker':str(2*fee),'sell_SEC_before_rounding':str(sec),'round_trip_broker_bps':str(2*fee/notional*10000) if notional else None,'five_slots_buy_cash':str(5*(notional+fee)),'five_slots_round_trip_broker':str(10*fee),'five_slots_SEC':str(5*sec)})
result={'synthetic_tests':'passed: empty, terminal-exclusive, duplicate-time last update, locked, crossed, invalid size, coverage and hand-computed weighted mean/median','independent_decimal_all_cells':'passed','quotes':raw_total,'valid_seconds':valid_ns/1e9,'crossed_seconds':crossed_ns/1e9,'uncovered_seconds':uncovered_ns/1e9,'calendar':schedule,'fee_examples':fees}
(P/'cost-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))

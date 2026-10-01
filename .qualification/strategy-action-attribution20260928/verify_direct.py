"""Second method: direct boundary predicate and original trade records."""
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import csv,json,hashlib
ROOT=Path(__file__).resolve().parent
STUDY=ROOT.parent/'strategy-interactions20260928'
D=Decimal
def read(p):return json.loads(p.read_text(encoding='utf-8'),parse_float=D)
def main():
    events=defaultdict(list)
    for line in (ROOT.parent/'action-inventory20260928/events.jsonl').read_text().splitlines():
        e=json.loads(line)
        if e['currency']=='USD':events[e['symbol']].append(e['effective_session'])
    expected_cross={}
    account_rows={r['account']:r for r in read(ROOT/'account-attribution.json')}
    largest={r['account']:r for r in read(ROOT/'largest-contributions-all54.json')}
    account_count=trade_count=0
    for f in sorted((STUDY/'accounts').glob('*.json')):
        report=read(f);name=f.stem;rows=report['trade_records']
        selected=[]
        for i,t in enumerate(rows):
            hits=sorted(day for day in events[t['symbol']] if t['entry_session']<day<=t['exit_session'])
            if hits:
                expected_cross[name,i]=(t['net_pnl'],[t['symbol']+'|'+d for d in hits]);selected.append((i,t))
        a=account_rows[name]
        total=sum((t['net_pnl'] for t in rows),D(0));hit=sum((t['net_pnl'] for _,t in selected),D(0))
        assert total==D(a['total_net_pnl']) and hit==D(a['action_crossing_net_pnl'])
        assert len(selected)==a['action_crossing_trades'] and len(rows)==a['total_trades']
        assert total-hit==D(a['noncrossing_net_pnl'])
        for label,items in [('all_trades',list(enumerate(rows))),('action_crossing_trades',selected)]:
            for sign,order in [('positive',-1),('negative',1)]:
                valid=[(i,t) for i,t in items if (t['net_pnl']>0 if sign=='positive' else t['net_pnl']<0)]
                expected=[i for i,t in sorted(valid,key=lambda it:(order*it[1]['net_pnl'],it[0]))[:5]]
                assert expected==[t['trade_index'] for t in largest[name][label][sign]],(name,label,sign)
        account_count+=1;trade_count+=len(rows)
    saved=list(csv.DictReader((ROOT/'crossing-trades.csv').open(encoding='utf-8')))
    actual={(r['account'],int(r['trade_index'])):(D(r['net_pnl']),r['events'].split(';')) for r in saved}
    assert len(actual)==len(saved) and actual==expected_cross
    original_hashes=read(STUDY/'result-hashes.json')
    assert all(hashlib.sha256((STUDY/'accounts'/n).read_bytes()).hexdigest()==h for n,h in original_hashes.items())
    result=dict(status='passed',method='Direct predicate over original USD provider split-labelled inventory, original records and numeric top-contribution sort; no bisect or imported analysis functions.',
        accounts=account_count,trades=trade_count,crossings=len(actual),top_trade_lists_checked=account_count*4,
        original_account_hashes_unchanged=len(original_hashes),
        limit='Verifies descriptive join/arithmetic and trade extreme selection; not causal action PnL, dividend completeness or signal-lookback cleanliness.')
    (ROOT/'direct-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()


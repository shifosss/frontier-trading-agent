"""Descriptive attribution of immutable completed trade logs; no replay or repair."""
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from pathlib import Path
import csv, hashlib, json

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
STUDY=ROOT.parent/'strategy-interactions20260928'
D=Decimal
ZERO=D(0)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'),parse_float=D)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(name,obj):
    (ROOT/name).write_text(json.dumps(obj,indent=2,default=str,allow_nan=False),encoding='utf-8')

def write_csv(name,rows):
    if not rows:return
    with (ROOT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def stats(trades):
    positive=sum((t['net_pnl'] for t in trades if t['net_pnl']>0),ZERO)
    negative=sum((t['net_pnl'] for t in trades if t['net_pnl']<0),ZERO)
    return dict(trades=len(trades),wins=sum(t['net_pnl']>0 for t in trades),
        losses=sum(t['net_pnl']<0 for t in trades),flat=sum(t['net_pnl']==0 for t in trades),
        net_pnl=positive+negative,positive_pnl=positive,negative_pnl=negative,
        absolute_pnl=positive-negative,gross_pnl=sum((t['gross_pnl'] for t in trades),ZERO),
        fees=sum((t['entry_fee']+t['exit_fee'] for t in trades),ZERO))

def ratio(a,b):
    return a/b if b else None

def extremes(trades,key='net_pnl'):
    return dict(positive=sorted((t for t in trades if t[key]>0),key=lambda t:(-t[key],t['trade_index'] if 'trade_index' in t else t['event_id']))[:5],
        negative=sorted((t for t in trades if t[key]<0),key=lambda t:(t[key],t['trade_index'] if 'trade_index' in t else t['event_id']))[:5])

def main():
    declaration=read(ROOT/'definition.json')
    for path,digest in declaration['inputs'].items():
        assert sha(REPO/path)==digest, 'Declared input changed: '+path
    status=read(STUDY/'status.json')
    assert status['phase']=='complete' and status['completed']==54
    request=read(STUDY/'request.json')
    hashes=read(STUDY/'result-hashes.json')
    identity=read(STUDY/'definition.json')
    assert all(sha(REPO/name)==digest for name,digest in identity['files'].items()), 'Frozen study code changed'
    expected=[f"{p}-{h}-{c}.json" for p in request['policies'] for h in request['holding_sessions'] for c in request['cost_profiles']]
    assert len(expected)==54 and set(expected)==set(hashes)
    source=read(STUDY/'source-evidence.json')
    audit_definition=read(ROOT.parent/'action-inventory20260928/definition.json')
    assert source['capture_index_sha256']==audit_definition['capture_index_sha256']
    source_hashes={s['symbol']:s['sha256'] for s in source['source_hashes']}
    notice={(n['symbol'],n['effective_session']):n for n in read(ROOT.parent/'action-validation20260928/notice-assessments.json')}
    events=defaultdict(list);event_by_id={}
    for line in (ROOT.parent/'action-inventory20260928/events.jsonl').read_text(encoding='utf-8').splitlines():
        e=json.loads(line,parse_float=D)
        if e['symbol'] not in source_hashes:continue
        assert e['source_sha256']==source_hashes[e['symbol']]
        symbol,day=e['symbol'],e['effective_session']
        flags=['any_reported_action']
        if e.get('large_adjusted_move_triage'):flags.append('large_adjusted_move_triage')
        if e.get('ratio_alignment_triage'):flags.append('ratio_alignment_triage')
        if e.get('missing_boundary_reason'):flags.append('missing_source_boundary')
        n=notice.get((symbol,day))
        if n:
            if n['notice_status']=='contradicted_split_only':flags.append('audited_composite_quantity_semantics')
            if any(v=='discrepancy' for v in n['nominal_status'].values()):flags.append('audited_nominal_discrepancy')
            if n['price_factor_status']=='inconsistent':flags.append('audited_factor_outside_declared_precision')
        if (symbol,day)==('AIXI','2026-09-08'):flags.append('audited_missing_adjustment')
        if any(f in flags for f in ['audited_composite_quantity_semantics','audited_nominal_discrepancy','audited_missing_adjustment']):flags.append('known_source_issue_union')
        event=dict(event_id=symbol+'|'+day,symbol=symbol,effective_session=day,
            numerator=e['numerator'],denominator=e['denominator'],direction=e['direction'],
            source_sha256=e['source_sha256'],flags=flags)
        assert event['event_id'] not in event_by_id
        event_by_id[event['event_id']]=event;events[symbol].append(event)
    for values in events.values():values.sort(key=lambda e:e['effective_session'])
    dates={symbol:[e['effective_session'] for e in values] for symbol,values in events.items()}
    account_rows=[];category_rows=[];event_rows=[];crossing_rows=[];top_rows=[];verification=[]
    flags=declaration['categories']
    with localcontext() as ctx:
        ctx.prec=50
        for filename in expected:
            path=STUDY/'accounts'/filename
            assert sha(path)==hashes[filename],filename
            report=read(path);account=filename.removesuffix('.json')
            base=dict(account=account,policy=report['policy'],holding_sessions=report['horizon'],cost_profile=report['cost_profile'],status=report['status'],account_sha256=hashes[filename])
            records=report.get('trade_records')
            if records is None:
                account_rows.append(dict(**base,attribution_status='unavailable_missing_trade_records'))
                verification.append(dict(account=account,status='unavailable',reason='missing trade records'))
                continue
            trades=[];crossing=[];by_flag={flag:[] for flag in flags};by_event=defaultdict(list)
            arithmetic_errors=[]
            for index,t in enumerate(records):
                assert t['entry_session']<t['exit_session'], (account,index)
                t=dict(t,trade_index=index)
                for field in ['net_pnl','gross_pnl','entry_fee','exit_fee']:t[field]=D(str(t[field]))
                delta=t['gross_pnl']-t['entry_fee']-t['exit_fee']-t['net_pnl']
                if abs(delta)>D('1e-7'):arithmetic_errors.append(dict(trade_index=index,delta=delta))
                symbol=t['symbol'];ds=dates.get(symbol,[])
                crossed=events[symbol][bisect_right(ds,t['entry_session']):bisect_right(ds,t['exit_session'])]
                ids=[e['event_id'] for e in crossed]
                categories=sorted(set(f for e in crossed for f in e['flags']))
                slim=dict(trade_index=index,symbol=symbol,signal_session=t['signal_session'],entry_session=t['entry_session'],exit_session=t['exit_session'],
                    net_pnl=t['net_pnl'],gross_pnl=t['gross_pnl'],entry_fee=t['entry_fee'],exit_fee=t['exit_fee'],
                    events=ids,flags=categories)
                trades.append(slim)
                if crossed:
                    crossing.append(slim)
                    crossing_rows.append(dict(account=account,**{k:v for k,v in slim.items() if k not in ['events','flags']},
                        events=';'.join(ids),flags=';'.join(categories)))
                for flag in categories:by_flag[flag].append(slim)
                for e in crossed:by_event[e['event_id']].append(slim)
            overall=stats(trades);hit=stats(crossing)
            original_total=report.get('trade_metrics',{}).get('net_pnl_total')
            total_delta=overall['net_pnl']-D(str(original_total)) if original_total is not None else None
            tolerance=D('0.000001')+D('0.000000000001')*overall['absolute_pnl']
            count_ok=report.get('trades')==len(trades)
            total_ok=total_delta is None or abs(total_delta)<=tolerance
            assert not arithmetic_errors and count_ok and total_ok,(account,arithmetic_errors,total_delta)
            total_return=D(str(report['total_return'])) if report.get('total_return') is not None else None
            account_rows.append(dict(**base,attribution_status='complete',total_return=total_return,
                total_trades=overall['trades'],total_net_pnl=overall['net_pnl'],
                positive_pnl=overall['positive_pnl'],negative_pnl=overall['negative_pnl'],absolute_pnl=overall['absolute_pnl'],
                action_crossing_trades=hit['trades'],action_crossing_net_pnl=hit['net_pnl'],
                noncrossing_trades=overall['trades']-hit['trades'],noncrossing_net_pnl=overall['net_pnl']-hit['net_pnl'],
                known_issue_crossing_trades=len(by_flag['known_source_issue_union']),
                known_issue_crossing_net_pnl=stats(by_flag['known_source_issue_union'])['net_pnl']))
            for flag in flags:
                s=stats(by_flag[flag])
                category_rows.append(dict(account=account,category=flag,**s,
                    trade_fraction=ratio(D(s['trades']),D(overall['trades'])),
                    net_pnl_fraction=ratio(s['net_pnl'],overall['net_pnl']),
                    positive_pnl_fraction=ratio(s['positive_pnl'],overall['positive_pnl']),
                    negative_pnl_fraction=ratio(s['negative_pnl'],overall['negative_pnl']),
                    absolute_pnl_fraction=ratio(s['absolute_pnl'],overall['absolute_pnl'])))
            local_events=[]
            for event_id,ts in sorted(by_event.items()):
                e=event_by_id[event_id];s=stats(ts)
                row=dict(account=account,event_id=event_id,symbol=e['symbol'],effective_session=e['effective_session'],
                    direction=e['direction'],flags=';'.join(e['flags']),**s)
                local_events.append(row);event_rows.append(row)
            top_rows.append(dict(account=account,all_trades=extremes(trades),
                action_crossing_trades=extremes(crossing),event_contributions=extremes(local_events)))
            verification.append(dict(account=account,status='passed',trade_count=len(trades),serialized_net_sum=overall['net_pnl'],
                saved_net_total=original_total,total_delta=total_delta,tolerance=tolerance,per_trade_arithmetic_errors=arithmetic_errors))
    dump('account-attribution.json',account_rows)
    write_csv('account-attribution.csv',account_rows)
    write_csv('category-attribution.csv',category_rows)
    write_csv('event-attribution.csv',event_rows)
    write_csv('crossing-trades.csv',crossing_rows)
    dump('largest-contributions-all54.json',top_rows)
    dump('verification.json',verification)
    dump('matched-event-definitions.json',list(event_by_id.values()))
    dump('input-result-hashes.json',dict(study_result_hashes=hashes,
        files={str(p.relative_to(REPO)):sha(p) for p in [STUDY/'status.json',STUDY/'summary.json',STUDY/'result-hashes.json',STUDY/'source-evidence.json']},
        capture_index_sha256=source['capture_index_sha256']))
    assert all(sha(STUDY/'accounts'/name)==digest for name,digest in hashes.items())
    summary=dict(accounts=len(account_rows),attribution_status=dict(Counter(r['attribution_status'] for r in account_rows)),
        account_trade_observations=sum(r.get('total_trades',0) for r in account_rows),
        crossing_trade_observations=len(crossing_rows),
        events_crossed=len({r['event_id'] for r in event_rows}),
        profitable_accounts=sum(r.get('total_net_pnl',0)>0 for r in account_rows),
        known_issue_accounts=sum(r.get('known_issue_crossing_trades',0)>0 for r in account_rows),
        note='Account paths are alternative simulations, not additive independent investments. Full crossing-trade PnL is attribution, not causal action PnL or corrected account profit.')
    dump('summary.json',summary)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()


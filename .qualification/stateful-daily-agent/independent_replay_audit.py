"""Independent saved-replay ledger audit; imports no Frontier production modules.

Read journal in one SQLite snapshot. Rebuild source-priced marks, cash, settlement,
fees and period statistics from executed trades and chunk-boundary open positions.
Does not prove model quality, all-symbol ranking optimality or corporate-action completeness.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TZ = ZoneInfo('America/Toronto')
TOL = 1e-7


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def check_close(actual, expected, label):
    assert math.isfinite(actual) and math.isfinite(expected), label
    error = abs(actual - expected)
    assert error <= TOL + abs(expected) * 1e-10, (label, actual, expected, error)
    return error


def nth_weekday(year, month, weekday, n):
    day = date(year, month, 1)
    return day + timedelta(days=(weekday - day.weekday()) % 7 + (n - 1) * 7)


def us_banking_holidays(year):
    def sunday_observed(day):
        return day + timedelta(days=1) if day.weekday() == 6 else day
    holidays = {sunday_observed(date(year, m, d)) for m, d in [(1, 1), (7, 4), (11, 11), (12, 25)]}
    if year >= 2022:
        holidays.add(sunday_observed(date(year, 6, 19)))
    holidays.update([nth_weekday(year, 1, 0, 3), nth_weekday(year, 2, 0, 3),
                     nth_weekday(year, 9, 0, 1), nth_weekday(year, 10, 0, 2),
                     nth_weekday(year, 11, 3, 4)])
    last_may = date(year, 5, 31)
    holidays.add(last_may - timedelta(days=last_may.weekday()))
    return holidays


def settlement_map(sessions, extended):
    bank_holidays = set().union(*(us_banking_holidays(y) for y in range(2020, 2028)))
    result = []
    for i, label in enumerate(sessions):
        lag = 1 if label >= '2024-05-28' else 2 if label >= '2017-09-05' else 3
        for j in range(i + 1, len(extended)):
            if date.fromisoformat(extended[j]) not in bank_holidays:
                lag -= 1
                if not lag:
                    result.append(j)
                    break
        else:
            raise AssertionError(('settlement_calendar_exhausted', label))
    return result


def fee(profile, bps, quantity, notional, side):
    friction = notional * bps / 20000
    if profile != 'moomoo_ca_us':
        return friction
    q, amount = Decimal(quantity), Decimal(str(notional))
    commission, platform = ('0.0005', '0.0005') if amount < q else ('0.0049', '0.005')
    cent = Decimal('0.01')
    explicit = max(Decimal('0.99'), q * Decimal(commission)).quantize(cent, rounding=ROUND_CEILING)
    explicit += max(Decimal('1'), q * Decimal(platform)).quantize(cent, rounding=ROUND_CEILING)
    if side == 'sell':
        explicit += max(cent, amount * Decimal('0.0000206')).quantize(cent, rounding=ROUND_CEILING)
    return friction + float(explicit)


def load_raw(record, sessions, calendar):
    base = ROOT / 'data/historical/capture-workspace'
    path = (base / record['path']).resolve()
    assert path.is_relative_to(base / 'data/scanner/raw')
    content = path.read_bytes()
    assert sha(content) == record['sha256'], ('raw_hash', record['symbol'])
    result = json.loads(content)['chart']['result'][0]
    assert result['meta']['symbol'].upper() == record['symbol'].upper()
    assert result['meta']['currency'] == 'USD'
    captured = datetime.fromisoformat(record['captured_at'])
    cutoff = min(captured, datetime.fromisoformat(record.get('requested_as_of', record['captured_at'])))
    splits = []
    for event in result.get('events', {}).get('splits', {}).values():
        effective = datetime.fromtimestamp(event['date'], timezone.utc).astimezone(TZ).date().isoformat()
        if effective <= captured.astimezone(TZ).date().isoformat():
            ratio = float(event['numerator']) / float(event['denominator'])
            assert ratio > 0
            splits.append((effective, ratio))
    assert len({s[0] for s in splits}) == len(splits)
    quote = result['indicators']['quote'][0]
    adjusted = result['indicators']['adjclose'][0]['adjclose']
    rows = {}
    for k, stamp in enumerate(result['timestamp']):
        label = datetime.fromtimestamp(stamp, timezone.utc).astimezone(TZ).date().isoformat()
        if label < sessions[0] or label > sessions[-1]:
            continue
        values = [quote[field][k] for field in ['close', 'high', 'low', 'volume']] + [adjusted[k]]
        if any(x is None or not math.isfinite(float(x)) for x in values):
            continue
        if pd.Timestamp(label) not in calendar.schedule.index:
            continue
        if calendar.schedule.loc[pd.Timestamp(label), 'close'].to_pydatetime() + timedelta(minutes=1) > cutoff:
            continue
        factor = math.prod(ratio for effective, ratio in splits if label < effective)
        close, high, low, volume, adj = map(float, values)
        assert min(close, high, low, adj) > 0 and low <= close <= high and volume >= 0
        assert label not in rows
        rows[label] = dict(close=close * factor, high=high * factor, low=low * factor,
                           adjusted=adj, volume=volume / factor)
    # ATR independently computed from adjusted high/low and previous adjusted close.
    ranges = {}
    for k, label in enumerate(sessions):
        if k and label in rows and sessions[k-1] in rows:
            row, previous = rows[label], rows[sessions[k-1]]['adjusted']
            factor = row['adjusted'] / row['close']
            high, low = row['high'] * factor, row['low'] * factor
            ranges[label] = max(high-low, abs(high-previous), abs(low-previous))
        if k >= 14 and all(s in ranges for s in sessions[k-13:k+1]):
            row = rows[label]
            row['atr'] = sum(ranges[s] for s in sessions[k-13:k+1]) / 14 / (row['adjusted']/row['close'])
    return rows, splits


def period_rows(equity, sessions, budget, frequency):
    groups = {}
    for label, value in zip(sessions, equity):
        d = date.fromisoformat(label)
        iso = d.isocalendar()
        key = f'{iso.year}-W{iso.week:02}' if frequency == 'weekly' else label[:7]
        groups[key] = (label, value)
    previous, rows = budget, []
    for key, (label, value) in groups.items():
        rows.append(dict(period=key, last_session=label, **{'return': value/previous-1}))
        previous = value
    check_close(math.prod(1+r['return'] for r in rows)-1, equity[-1]/budget-1, frequency+'_compounding')
    return rows


def audit(replay_id, summary_path=None):
    path = ROOT / 'artifacts/candidate-replays' / replay_id / 'journal.sqlite'
    con = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    con.execute('BEGIN')
    assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    identity = json.loads(con.execute('SELECT payload FROM identity').fetchone()[0])
    raw_chunks = con.execute('SELECT start_index,end_index,prior_state_sha256,payload,payload_sha256 FROM chunks ORDER BY start_index').fetchall()
    attempts = [dict(zip(['attempt_id','started_at','finished_at','status','error','request'],row))
                for row in con.execute('SELECT * FROM attempts ORDER BY started_at')]
    con.close()
    assert raw_chunks
    candidate = ROOT / 'artifacts/daily-candidates' / identity['candidate_id'] / 'model'
    manifest_bytes = (candidate/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    metadata = manifest['metadata']
    assert sha(canon(metadata).encode()) == manifest['metadata_sha256']
    assert sha((candidate / manifest['payload_file']).read_bytes()) == identity['model_id'] == manifest['payload_sha256']
    for key in ['data','account','policy']:
        assert sha(canon(metadata[key]).encode()) == identity[key+'_id'] == metadata[key+'_id']
    for name, expected in {**metadata['implementation_sha256'], **identity['code_sha256']}.items():
        assert sha((ROOT/'src/frontier'/name).read_bytes()) == expected, ('implementation_hash',name)
    for key in ['fit_sample','calibration_sample']:
        sample = metadata[key]
        assert sample['latest_target_session'] < sample['exclusive_boundary']
        assert sample['latest_target_session'] < identity['first_signal']
    data = metadata['data']
    source_root = ROOT/'artifacts/historical-lab/runs'/data['run_id']
    definition_bytes = (source_root/'definition.json').read_bytes()
    records_bytes = (source_root/'capture-index.json').read_bytes()
    assert sha(definition_bytes) == data['definition_sha256']
    assert sha(records_bytes) == data['capture_index_sha256']
    definition, records = json.loads(definition_bytes), json.loads(records_bytes)
    original = data['original_source']
    original_root = ROOT/'artifacts/historical-lab/runs'/original['run_id']
    assert sha((original_root/'definition.json').read_bytes()) == original['definition_sha256']
    assert (original_root/'capture-index.json').read_bytes() == records_bytes
    symbols = sorted(s['symbol'] for s in definition['instruments'] if s['currency'] == 'USD')
    calendar = xcals.get_calendar('XNYS', start=data['window_start'], end=str(date.fromisoformat(identity['end_session'])+timedelta(days=32)))
    extended = calendar.sessions.strftime('%Y-%m-%d').tolist()
    sessions = [s for s in extended if s <= identity['end_session']]
    assert sessions[identity['start_index']] == identity['first_signal']
    assert len(sessions) == identity['end_index']+1
    settlements = settlement_map(sessions, extended)
    assert sha(canon(settlements).encode()) == identity['settlement_indices_sha256']
    budget = metadata['account']['nav']
    profile = identity['cost_specification']['name']
    bps = identity['cost_specification']['round_trip_bps']
    scope = sha(json.dumps(dict(strategy=metadata['policy']['strategy'], horizon=metadata['policy']['horizon'],
                               end=identity['end_index'], symbols=symbols, sessions=sessions,
                               cost=identity['cost_specification'], correlation_limit=None), sort_keys=True).encode())
    chunks, state, cursor = [], None, identity['start_index']
    forecasts, trades, positions, boundary = {}, [], {}, {}
    max_errors = defaultdict(float)
    for first,last,prior,raw,digest in raw_chunks:
        assert first == cursor and last >= first and last <= identity['end_index']
        assert prior == sha(canon(state).encode()) and digest == sha(raw.encode())
        chunk = json.loads(raw)
        simulation = chunk['simulation']
        assert simulation['status'] == 'complete' and not simulation['missing']
        assert simulation['trades'] == len(simulation['trade_records'])
        assert all(len(simulation[k]) == last-first+1 for k in ['equity','cash','settled_cash','unsettled_cash'])
        state = simulation['state']
        assert state['scope'] == scope and state['next_session_index'] == last+1
        for j, forecast in enumerate(chunk['forecasts'], first):
            assert forecast['session'] == sessions[j] and j not in forecasts
            rankings = forecast['rankings']
            assert len({r['symbol'] for r in rankings}) == len(rankings)
            assert all(rankings[k]['score'] >= rankings[k+1]['score'] for k in range(len(rankings)-1))
            for row in rankings:
                heads = row['forecasts']
                head = [1, 3, 5].index(metadata['policy']['horizon'])
                score = heads[head]*(1-bps/20000)-bps/10000-.5*max(0,heads[head+3])
                check_close(row['score'],score,'saved_forecast_score')
            forecasts[j] = {r['symbol']:dict(rank=k, **r) for k,r in enumerate(rankings)}
        trades.extend(simulation['trade_records'])
        boundary[last] = state
        for p in state['held']:
            key = (symbols[p['symbol_index']],p['entry'])
            row = dict(p, symbol=key[0])
            if key in positions:
                assert positions[key] == row
            positions[key] = row
        chunks.append((first,last,simulation))
        cursor = last+1
    trade_keys = set()
    for trade in trades:
        symbol = trade['symbol']; e = sessions.index(trade['entry_session']); x = sessions.index(trade['exit_session']); s = sessions.index(trade['signal_session'])
        key = (symbol,e)
        assert key not in trade_keys
        trade_keys.add(key)
        assert e == s+1 and x-e == metadata['policy']['horizon'] == trade['holding_sessions']
        assert (date.fromisoformat(sessions[x])-date.fromisoformat(sessions[e])).days == trade['holding_calendar_days']
        assert trade['settlement_index'] == settlements[x]
        base = dict(symbol=symbol,symbol_index=symbols.index(symbol),signal=s,entry=e,exit=x,
                    quantity=trade['quantity'],notional=trade['entry_notional'],entry_fee=trade['entry_fee'])
        if key in positions:
            for k,v in base.items():
                if isinstance(v,float):check_close(positions[key][k],v,'position_trade_'+k)
                else: assert positions[key][k] == v
        else:
            positions[key] = base
    selected = {s for s,_ in positions} | {'SPY'}
    selected.update(symbols[p['symbol_index']] for st in boundary.values() for p in st['pending'])
    records_by_symbol = {r['symbol']:r for r in records}
    saved_hashes = {r['symbol']:r['sha256'] for r in data['source_hashes']}
    sources, split_events = {}, {}
    for symbol in sorted(selected):
        record = records_by_symbol[symbol]
        assert record['sha256'] == saved_hashes[symbol]
        sources[symbol], split_events[symbol] = load_raw(record,sessions,calendar)
    entries, exits = defaultdict(list), defaultdict(list)
    for p in positions.values():
        assert type(p['quantity']) is int and p['quantity'] > 0
        row = sources[p['symbol']][sessions[p['entry']]]
        check_close(p['notional'],p['quantity']*row['close'],'raw_entry_notional')
        p['adjusted_entry'] = row['adjusted']
        check_close(p['entry_fee'],fee(profile,bps,p['quantity'],p['notional'],'buy'),'entry_fee')
        assert forecasts[p['signal']][p['symbol']]['score'] > 0
        entries[p['entry']].append(p)
        exits[p['exit']].append(p)
    for trade in trades:
        p = positions[(trade['symbol'],sessions.index(trade['entry_session']))]
        value = p['notional']*sources[p['symbol']][trade['exit_session']]['adjusted']/p['adjusted_entry']
        cost = fee(profile,bps,p['quantity'],value,'sell')
        profit = value-cost-p['notional']-p['entry_fee']
        for key,expected in [('exit_notional',value),('exit_fee',cost),('gross_pnl',value-p['notional']),('net_pnl',profit),('net_return',profit/p['notional'])]:
            max_errors[key] = max(max_errors[key],check_close(trade[key],expected,key))
    actual_curves = {k:[v for _,_,s in chunks for v in s[k]] for k in ['equity','cash','settled_cash','unsettled_cash']}
    held, due = {}, []
    cash = settled = budget
    total_fees = 0.0
    all_fees = {}
    rebuilt = defaultdict(list)
    max_held = 0
    action_crossing = []
    for i in range(identity['start_index'],cursor):
        matured = [amount for when,amount in due if when <= i]
        settled += sum(matured)
        due = [(when,amount) for when,amount in due if when > i]
        for p in sorted(exits[i], key=lambda p:(p['entry'], forecasts[p['signal']][p['symbol']]['rank'])):
            symbol = p['symbol']; assert symbol in held
            value = p['notional']*sources[symbol][sessions[i]]['adjusted']/p['adjusted_entry']
            cost = fee(profile,bps,p['quantity'],value,'sell')
            net = value-cost; cash += net
            if net >= 0:due.append((settlements[i],net))
            else:settled += net
            total_fees += cost
            all_fees[(symbol,p['entry'],'exit')] = cost
            del held[symbol]
            crossed = [(d,r) for d,r in split_events[symbol] if sessions[p['entry']] < d <= sessions[i]]
            if crossed:action_crossing.append(dict(symbol=symbol,entry=sessions[p['entry']],exit=sessions[i],reported_splits=crossed))
        nav = cash+sum(p['notional']*sources[s][sessions[i]]['adjusted']/p['adjusted_entry'] for s,p in held.items())
        for p in sorted(entries[i],key=lambda p:forecasts[p['signal']][p['symbol']]['rank']):
            symbol = p['symbol']; assert symbol not in held
            assert p['quantity'] > 0 and len(held)<5
            amount = p['notional']+p['entry_fee']
            assert amount <= settled+TOL and amount <= .2*nav+TOL
            signal_nav = actual_curves['equity'][p['signal']-identity['start_index']]
            signal_row = sources[symbol][sessions[p['signal']]]
            assert p['quantity']*2*signal_row['atr'] <= .005*signal_nav+TOL, ('atr_risk',symbol)
            signal_notional = p['quantity']*signal_row['close']
            assert signal_notional+fee(profile,bps,p['quantity'],signal_notional,'buy') <= .2*signal_nav+TOL
            for other in positions.values():
                assert not (other['symbol']==symbol and other['entry']<=p['signal']<other['exit']), ('held_at_signal',symbol)
            cash-=amount;settled-=amount;nav-=p['entry_fee'];held[symbol]=p
            total_fees+=p['entry_fee'];all_fees[(symbol,p['entry'],'entry')]=p['entry_fee']
        assert min(cash,settled)>=-TOL
        max_held=max(max_held,len(held))
        values=dict(cash=cash,settled_cash=settled,unsettled_cash=sum(v for _,v in due),
                    equity=cash+sum(p['notional']*sources[s][sessions[i]]['adjusted']/p['adjusted_entry'] for s,p in held.items()))
        for k,v in values.items():
            max_errors[k]=max(max_errors[k],check_close(actual_curves[k][i-identity['start_index']],v,k+'_'+sessions[i]))
            rebuilt[k].append(v)
        check_close(cash,settled+sum(v for _,v in due),'cash_reconciliation')
        if i in boundary:
            state=boundary[i]
            check_close(state['cash'],cash,'state_cash');check_close(state['settled_cash'],settled,'state_settled_cash')
            assert {symbols[p['symbol_index']] for p in state['held']}==set(held)
            for saved in state['held']:
                p=held[symbols[saved['symbol_index']]]
                for k,v in saved.items():
                    if isinstance(v,float):check_close(v,p[k],'state_position_'+k)
                    else:assert v==p[k]
            assert len(state['receivables'])==len(due)
            for actual,expected in zip(state['receivables'],due):
                assert actual[0]==expected[0];check_close(actual[1],expected[1],'state_receivable')
            reservations=0.0
            pending=state['pending']
            assert len({p['symbol_index'] for p in pending})==len(pending)
            slots=5-sum(p['exit']>i+1 for p in held.values())
            assert len(pending)<=slots
            for order in pending:
                symbol=symbols[order['symbol_index']]; q=order['quantity']
                assert symbol not in held and type(q) is int and q>0 and order['signal']==i
                assert forecasts[i][symbol]['score']>0
                row=sources[symbol][sessions[i]]; amount=q*row['close']+fee(profile,bps,q,q*row['close'],'buy')
                assert amount<=.2*values['equity']+TOL
                assert q*2*row['atr']<=.005*values['equity']+TOL
                reservations+=amount
            assert reservations<=settled+sum(v for d,v in due if d<=i+1)+TOL
    check_close(total_fees,sum(s['fees'] for _,_,s in chunks),'all_recorded_fees')
    for first,last,s in chunks:
        expected_fees=sum(v for (symbol,e,side),v in all_fees.items() if first <= (e if side=='entry' else positions[(symbol,e)]['exit']) <= last)
        check_close(s['fees'],expected_fees,'chunk_fees')
        check_close(s['net_pnl_total'],sum(t['net_pnl'] for t in s['trade_records']),'chunk_net_pnl')
    labels=sessions[identity['start_index']:cursor]
    equity=actual_curves['equity']
    peak=budget;drawdown=0.0;duration=longest=0
    for value in equity:
        peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
        duration=duration+1 if value<peak else 0;longest=max(longest,duration)
    periods={frequency:period_rows(equity,labels,budget,frequency) for frequency in ['weekly','monthly']}
    pnl=[t['net_pnl'] for t in trades]
    metrics=dict(ending_equity=equity[-1],total_return=equity[-1]/budget-1,max_drawdown=drawdown,
                 max_drawdown_duration_sessions=longest,net_pnl_total=sum(pnl),win_rate=sum(p>0 for p in pnl)/len(pnl) if pnl else None,
                 mean_holding_sessions=statistics.mean(t['holding_sessions'] for t in trades) if trades else None,
                 mean_exposure_fraction=statistics.mean(1-c/e for c,e in zip(actual_curves['cash'],equity)),
                 minimum_settled_cash=min(actual_curves['settled_cash']),maximum_held_positions=max_held,
                 fees=total_fees,completed_trades=len(trades),open_positions=len(held),pending_orders=len(state['pending']))
    summary_check='not_requested'
    if summary_path:
        summary=json.loads(Path(summary_path).read_text())
        for key in ['ending_equity','total_return','max_drawdown']:check_close(summary[key],metrics[key],'summary_'+key)
        for freq,rows in periods.items():
            assert len(rows)==len(summary['period_returns'][freq])
            for expected,actual in zip(rows,summary['period_returns'][freq]):
                assert expected['period']==actual['period'] and expected['last_session']==actual['last_session']
                check_close(expected['return'],actual['return'],'summary_'+freq)
        summary_check='passed'
    benchmark_entry=identity['start_index']+1
    spy=sources['SPY']
    q=0
    while (q+1)*spy[sessions[benchmark_entry]]['close']+fee(profile,bps,q+1,(q+1)*spy[sessions[benchmark_entry]]['close'],'buy')<=budget:
        q+=1
    nominal=q*spy[sessions[benchmark_entry]]['close'];entry_fee=fee(profile,bps,q,nominal,'buy') if q else 0
    terminal=nominal*spy[labels[-1]]['adjusted']/spy[sessions[benchmark_entry]]['adjusted']
    spy_end=budget-nominal-entry_fee+terminal-(fee(profile,bps,q,terminal,'sell') if q else 0)
    result=dict(audited_at=datetime.now(timezone.utc).isoformat(),replay_id=replay_id,status='passed',
                completeness='full_declared_replay' if cursor>identity['end_index'] else 'partial_snapshot',
                snapshot=dict(chunks=len(chunks),next_session_index=cursor,last_session=labels[-1],chunk_hashes=[r[-1] for r in raw_chunks]),
                script_sha256=sha(Path(__file__).read_bytes()),manifest_sha256=sha(manifest_bytes),
                independent_scope='No Frontier imports, no model fitting or feature rebuild; raw executed/boundary names plus SPY only',
                checks=['sqlite_integrity','journal_hash_chain_and_cursors','manifest_model_and_code_hashes','frozen_source_index_and_raw_hashes',
                        'purged_model_cutoffs','all_saved_forecast_scores','source_entry_exit_and_daily_marks','whole_shares_and_five_position_limit',
                        'entry_risk_and_twenty_percent_budgets','positive_signal_next_close_five_session_hold',
                        'independent_us_settlement_calendar_digest','daily_cash_settled_receivables_reconstruction','chunk_held_and_pending_reservations',
                        'independent_proportional_and_decimal_tariff_fees','weekly_monthly_compounding_and_drawdown'],
                sources=[dict(symbol=s,sha256=records_by_symbol[s]['sha256']) for s in sorted(selected)],
                forecast_rows=sum(len(v) for v in forecasts.values()),source_symbols=len(selected),metrics=metrics,period_returns=periods,
                summary_comparison=summary_check,max_absolute_errors=dict(max_errors),reported_split_crossing_trades=action_crossing,
                aixi_review=dict(executed_trades=[t for t in trades if t['symbol']=='AIXI'],
                                 open_positions=[p for p in held.values() if p['symbol']=='AIXI'],
                                 known_source_issue='Independent issuer/depositary evidence identifies 2026-09-08 1-for-7 reverse ADS ratio; Yahoo source continuity is unresolved here. See docs/aixi-source-continuity.md. No source correction or portfolio PnL correction is applied.'),
                spy_comparison=dict(method='Whole shares at next close; same synthetic total-return marks, entry and terminal-exit costs; unused cash retained',
                                    quantity=q,entry_session=sessions[benchmark_entry],ending_equity=spy_end,total_return=spy_end/budget-1),
                attempts=[{k:v for k,v in a.items() if k!='request'} for a in attempts],
                limitations=['Current-member adjusted-vintage research; raw provider agreement does not prove issuer/action correctness.',
                             'Only executed and chunk-boundary pending names have raw prices independently checked; no all-symbol ranking/eligibility completeness claim.',
                             'Recorded synthetic atomic closes are not real fills, partial fills or reconciled broker share/cash accounting.',
                             'Cost coverage is the saved declared scenario; missing tariff components, FX, subscriptions and taxes remain excluded.',
                             'The reused historical evaluation is not an untouched holdout or profitability qualification.'])
    out=OUT/('independent-ledger-audit-'+replay_id+'-'+str(cursor)+'.json')
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['replay_id','status','completeness','snapshot','source_symbols','forecast_rows','metrics','summary_comparison']}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('replay_id')
    parser.add_argument('--summary')
    args=parser.parse_args()
    audit(args.replay_id,args.summary)

"""Independent ETF ledger arithmetic; no engine, adapter, strategy or network imports."""
from pathlib import Path
from decimal import Decimal as D,ROUND_CEILING,ROUND_FLOOR
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from statistics import median
import copy,hashlib,importlib.util,json,math,sys,traceback
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
REPO=ROOT.parents[1]
prior=REPO/'.qualification/post-filing-strategy20260928/account-audit/audit_accounts.py'
spec=importlib.util.spec_from_file_location('previous_independent_dates',prior)
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
read,sha,near=old.read,old.sha,old.near
def decimal(x):return D(str(x))
def key(row):return row['signal_session'],row['symbol']

def fee(q,n,side,profile,bps):
    if not q:return D(0)
    n=decimal(n);explicit=D(0)
    if profile=='moomoo_ca_us':
        rates=('0.0005','0.0005') if n<D(q) else ('0.0049','0.005')
        explicit=sum(max(floor,D(q)*D(rate)).quantize(D('.01'),rounding=ROUND_CEILING)
            for floor,rate in zip((D('.99'),D('1.00')),rates))
        if side=='sell':explicit+=max(D('.01'),n*D('.0000206')).quantize(D('.01'),rounding=ROUND_CEILING)
    else:assert profile=='wealthsimple_usd'
    return explicit+n*D(str(bps))/D(20000)

def maxq(cap,price,budget,profile,bps):
    p=decimal(price);budget=decimal(budget)
    top=min(int(cap),max(0,int(budget/p)))
    return next((q for q in range(top,-1,-1) if D(q)*p+fee(q,D(q)*p,'buy',profile,bps)<=budget+D('1e-10')),0)

def weekly(values):
    streak=longest=0
    for value in values:
        streak=streak+1 if value<0 else 0;longest=max(longest,streak)
    return {'weeks':len(values),'includes_idle_and_losing_weeks':True,
        'thresholds':[{'return_at_least':t,'count':sum(v>=t for v in values),'fraction':sum(v>=t for v in values)/len(values) if values else None} for t in [.05,.10,.15]],
        'median_return':median(values) if values else None,'worst_return':min(values) if values else None,'longest_losing_week_streak':longest}

def audit(a,m,z,signals,bps=15):
    assert a['status']=='complete' and not a['missing']
    capital=a['capital'];profile=a['cost_profile'];arm=a['arm']
    sessions=m['sessions'];ix={s:i for i,s in enumerate(sessions)};sy={s:i for i,s in enumerate(m['symbols'])}
    trades=a['trade_records'];intents=a['intents'];curves=a['equity_curve'];daily=a['daily_state']
    trade_map={key(t):t for t in trades};intent_map={key(o):o for o in intents}
    assert len(trade_map)==len(trades) and len(intent_map)==len(intents)
    assert [c['session'] for c in curves]==sessions[m['first']:m['last']+1]
    planning=defaultdict(list);fills=defaultdict(list);exits=defaultdict(list)
    allfees=net=gross=D(0);price_checks=0
    for o in intents:
        i=ix[o['signal_session']];j=sy[o['symbol']];q=o['original_quantity']
        assert isinstance(q,int) and q>0
        assert o['planned_entry_session']==sessions[i+1] and o['original_exit_session']==sessions[i+4]
        assert o['signal_available_at']==m['signal_available_at'][i]
        near(o['reference_price'],z['close'][i,j],'nominal reference',1e-10)
        reserve=D(q)*decimal(float(z['close'][i,j]))+fee(q,D(q)*decimal(float(z['close'][i,j])),'buy',profile,bps)
        near(o['reserved_cash'],reserve,'original reservation');planning[i].append(o)
        if o['status']!='canceled_drawdown_halt':fills[i+1].append(o)
        price_checks+=1
    for t in trades:
        o=intent_map[key(t)];j=sy[t['symbol']];entry=ix[t['entry_session']];end=ix[t['exit_session']];q=t['quantity']
        assert q==o['filled_quantity'] and 0<q<=o['original_quantity'] and isinstance(q,int)
        assert entry==ix[t['signal_session']]+1 and t['original_exit_session']==sessions[entry+3]
        assert t['original_quantity']==o['original_quantity'] and o['status']=='closed'
        assert t['signal_available_at']==o['signal_available_at']
        near(t['reserved_cash'],o['reserved_cash'],'trade reservation')
        en=D(q)*decimal(float(z['close'][entry,j]));ex=en*decimal(float(z['adjusted'][end,j]))/decimal(float(z['adjusted'][entry,j]))
        ef=fee(q,en,'buy',profile,bps);xf=fee(q,ex,'sell',profile,bps)
        for field,value in [('entry_notional',en),('exit_notional',ex),('entry_fee',ef),('exit_fee',xf),('gross_pnl',ex-en),('net_pnl',ex-en-ef-xf)]:
            near(t[field],value,field)
        near(t['net_return'],(ex-en-ef-xf)/en,'trade return',1e-10)
        assert en+ef<=decimal(o['reserved_cash'])+D('1e-7')
        assert t['holding_sessions']==end-entry and 1<=end-entry<=3
        assert t['holding_calendar_days']==(date.fromisoformat(t['exit_session'])-date.fromisoformat(t['entry_session'])).days
        assert t['exit_advanced_by_halt']==(end!=entry+3)
        lag=1 if t['exit_session']>='2024-05-28' else 2 if t['exit_session']>='2017-09-05' else 3
        eligible=[k for k in range(end+1,min(end+12,len(sessions))) if date.fromisoformat(sessions[k]) not in old.banking_holidays(int(sessions[k][:4]))]
        assert t['settlement_index']==int(z['settlement_index'][end])==eligible[lag-1]
        exits[end].append(t);allfees+=ef+xf;net+=ex-en-ef-xf;gross+=ex-en;price_checks+=2
    cash=settled=D(capital);receivables=[];held={};peak=D(capital);halt_index=None;rebuilt=[];marks_count=0;max_error=0.
    for c,ds in zip(curves,daily,strict=True):
        i=ix[c['session']];assert ds['session']==c['session']
        settled+=sum((v for due,v in receivables if due<=i),D(0));receivables=[(due,v) for due,v in receivables if due>i]
        marks={k:p['notional']*decimal(float(z['adjusted'][i,p['j']]))/p['adjusted_entry'] for k,p in held.items()};marks_count+=len(marks)
        for t in exits[i]:
            k=key(t);assert k in held and held[k]['exit']==i
            value=marks.pop(k);near(value,t['exit_notional'],'exit mark')
            proceeds=value-fee(t['quantity'],value,'sell',profile,bps);cash+=proceeds
            if proceeds<0:settled+=proceeds
            else:receivables.append((t['settlement_index'],proceeds))
            del held[k]
        nav=cash+sum(marks.values(),D(0))
        for o in fills[i]:
            k=key(o);j=sy[o['symbol']];price=decimal(float(z['close'][i,j]))
            cap=maxq(o['original_quantity'],price,o['reserved_cash'],profile,bps)
            assert o['reservation_capped_quantity']==cap
            q=maxq(cap,price,min(D('.2')*nav,settled),profile,bps)
            t=trade_map.get(k);assert q==(t['quantity'] if t else 0),(k,'fill quantity',q)
            if not q:assert o['status']=='no_fill';continue
            assert len(held)<5 and j not in [p['j'] for p in held.values()]
            notional=D(q)*price;charge=fee(q,notional,'buy',profile,bps)
            cash-=notional+charge;settled-=notional+charge;nav-=charge
            held[k]={'j':j,'signal':i-1,'entry':i,'exit':i+3,'quantity':q,'notional':notional,
                     'adjusted_entry':decimal(float(z['adjusted'][i,j])),'entry_fee':charge}
            marks[k]=notional
        equity=cash+sum(marks.values(),D(0));unsettled=sum((v for _,v in receivables),D(0))
        assert cash>=D('-1e-7') and settled>=D('-1e-7')
        for field,value in [('cash',cash),('settled_cash',settled),('unsettled_cash',unsettled),('equity',equity)]:
            near(c[field],value,'daily '+field);max_error=max(max_error,abs(float(value)-c[field]))
        near(cash,settled+unsettled,'cash=settled+receivable')
        peak=max(peak,equity);dd=D(1)-equity/peak
        near(ds['peak'],peak,'peak');near(ds['drawdown'],dd,'drawdown',1e-10)
        # Independently enumerate frozen candidate ranks under cash/risk/slot caps.
        expected=[];available=settled+sum((v for due,v in receivables if due<=i+1),D(0))
        slots=5-sum(p['exit']>i+1 for p in held.values())
        if halt_index is None and i+4<=m['last'] and available>0:
            ranked=signals[arm+'_ranking'][i,:int(signals[arm+'_counts'][i])]
            for j0 in ranked:
                j=int(j0)
                if j in [p['j'] for p in held.values()] or len(expected)>=slots:continue
                price=float(z['close'][i,j]);atr=float(z['atr'][i,j])
                if not math.isfinite(price+atr) or min(price,atr)<=0:continue
                risk=int((D('.005')*equity/(D(2)*decimal(atr))).to_integral_value(rounding=ROUND_FLOOR))
                q=maxq(risk,price,min(D('.2')*nav,available),profile,bps)
                if not q:continue
                reserved=D(q)*decimal(price)+fee(q,D(q)*decimal(price),'buy',profile,bps)
                expected.append((j,q,reserved));available-=reserved
        assert len(expected)==len(planning[i]),(c['session'],'planned denominator',len(expected),len(planning[i]))
        for (j,q,reserve),o in zip(expected,planning[i],strict=True):
            assert sy[o['symbol']]==j and o['original_quantity']==q,(key(o),'plan quantity/order',q)
            near(o['reserved_cash'],reserve,'planned cash reservation')
        pending=[{'symbol_index':j,'quantity':q,'signal':i} for j,q,_ in expected]
        if halt_index is None and dd>=D('.3'):
            halt_index=i;halt=a['drawdown_halt'];assert halt and halt['session']==c['session']
            near(halt['nav'],equity,'halt NAV');near(halt['peak'],peak,'halt peak');near(halt['observed_drawdown'],dd,'halt DD')
            assert halt['canceled_intents']==[{'signal_session':o['signal_session'],'symbol':o['symbol']} for o in planning[i]]
            assert all(o['status']=='canceled_drawdown_halt' for o in planning[i]);pending=[]
            instructions=[]
            for p in held.values():
                original=p['exit'];p['exit']=min(original,i+1)
                instructions.append({'symbol':m['symbols'][p['j']],'previous_exit_index':original,'new_exit_index':p['exit']})
            assert halt['exit_instructions']==instructions
        assert ds['halted']==(halt_index is not None)
        assert ds['pending']==pending
        assert len(ds['held'])==len(held)
        for saved,p in zip(ds['held'],held.values(),strict=True):
            for field,target in [('symbol_index',p['j']),('signal',p['signal']),('entry',p['entry']),('exit',p['exit']),('quantity',p['quantity'])]:assert saved[field]==target
            for field in ['notional','adjusted_entry','entry_fee']:near(saved[field],p[field],'held '+field)
        assert len(ds['receivables'])==len(receivables)
        for saved,(due,value) in zip(ds['receivables'],receivables,strict=True):
            assert saved[0]==due;near(saved[1],value,'receivable')
        rebuilt.append(float(equity))
    assert not held and not receivables
    assert not a['final_state']['held'] and not a['final_state']['pending'] and not a['final_state']['receivables']
    assert (halt_index is None)==(a['drawdown_halt'] is None)
    near(a['final_state']['cash'],cash,'final cash');near(a['final_state']['settled_cash'],settled,'final settled')
    near(a['ending_equity'],D(capital)+net,'ending NAV');near(a['fees'],allfees,'total fees')
    near(a['trade_metrics']['net_pnl_total'],net,'net PNL');near(a['total_return'],net/D(capital),'total return',1e-10)
    assert a['trades']==a['trade_metrics']['completed_trades']==len(trades)
    pk=float(capital);ddmax=0.
    for value in rebuilt:pk=max(pk,value);ddmax=max(ddmax,1-value/pk)
    near(a['max_drawdown'],ddmax,'maxdrawdown',1e-10)
    years=(date.fromisoformat(curves[-1]['session'])-date.fromisoformat(curves[0]['session'])).days/365.25
    near(a['cagr'],(rebuilt[-1]/capital)**(1/years)-1,'CAGR',1e-10)
    for frequency,rows in a['period_returns'].items():
        grouped={}
        for c in curves:
            dt=date.fromisoformat(c['session']);iso=dt.isocalendar();label=f'{iso.year}-W{iso.week:02d}' if frequency=='weekly' else c['session'][:7];grouped[label]=c
        assert len(rows)==len(grouped);before=capital
        for row,(label,c) in zip(rows,grouped.items(),strict=True):
            assert row['period']==label and row['last_session']==c['session'];near(row['return'],c['equity']/before-1,'periodreturn',1e-10);before=c['equity']
    weeks=a['period_returns']['weekly']
    for row in weeks:
        end=date.fromisoformat(row['last_session']);week_start=end-timedelta(days=end.weekday())
        scope='initialization' if row['last_session']<'2017-01-01' else 'entry_period_with_liquidation_tail' if week_start<=date(2025,12,31)<end else 'liquidation_tail' if row['last_session']>'2025-12-31' else 'entry_period'
        assert row['scope']==scope
    assert a['weekly_targets']==weekly([r['return'] for r in weeks])
    assert a['entry_period_weekly_targets']==weekly([r['return'] for r in weeks if r['scope'].startswith('entry_period')])
    previous=capital;product=D(1)
    grouped={}
    for c in curves:grouped[c['session'][:4]]=c
    assert len(a['annual_returns'])==len(a['yearly'])==len(grouped)
    for annual,yearly,(year,last) in zip(a['annual_returns'],a['yearly'],grouped.items(),strict=True):
        assert annual['year']==yearly['year']==year
        ret=last['equity']/previous-1
        near(annual['starting_equity'],previous,'annual starting');near(annual['ending_equity'],last['equity'],'annual ending')
        near(annual['return'],ret,'annualreturn',1e-10);near(yearly['return'],ret,'yearlyreturn',1e-10)
        pk=previous;ydd=0.
        for c in curves:
            if c['session'].startswith(year):pk=max(pk,c['equity']);ydd=max(ydd,1-c['equity']/pk)
        near(yearly['max_drawdown'],ydd,'yearlydrawdown',1e-10)
        product*=D(1)+decimal(annual['return']);previous=last['equity']
    near(product,decimal(rebuilt[-1])/D(capital),'annual compounding',1e-10)
    return {'status':'passed','arm':arm,'capital':capital,'cost_profile':profile,'trades':len(trades),'intents':len(intents),
      'daily_rows':len(curves),'held_marks_checked':marks_count,'source_price_checks':price_checks,'gross_pnl':float(gross),
      'net_pnl':float(net),'fees':float(allfees),'ending_equity':float(cash),'max_drawdown':ddmax,'halt_session':sessions[halt_index] if halt_index is not None else None,
      'weekly_targets':a['weekly_targets'],'entry_period_weekly_targets':a['entry_period_weekly_targets'],
      'maximum_daily_absolute_error':max_error}

def main(attempt_path):
    attempt=Path(attempt_path).resolve();completed=read(ROOT/'completed.json');definition=read(ROOT/'definition.json')
    assert attempt==REPO/completed['attempt'] and sha(ROOT/'definition.json')==completed['definition_sha256']
    for name,h in completed['files'].items():assert sha(attempt/name)==h,name
    for name,h in definition['files'].items():assert sha(REPO/name)==h,name
    expected=[(arm,cap,broker) for arm in definition['arms'] for cap in definition['capital_usd'] for broker in definition['brokers']]
    assert len(expected)==12 and len(set(expected))==12 and definition['round_trip_bps']==15
    summary=read(attempt/'summary.json');assert summary['planned_accounts']==12
    assert [(r['arm'],r['capital'],r['cost_profile']) for r in summary['accounts']]==expected
    prepared=REPO/definition['prepared'];m=read(prepared/'market-inputs.json')
    z=np.load(prepared/'market-arrays.npz',allow_pickle=False);signals=np.load(prepared/'signals.npz',allow_pickle=False)
    passed=[];failures=[]
    for row in summary['accounts']:
        path=attempt/row['artifact'];assert sha(path)==row['sha256']
        try:
            report=audit(read(path),m,z,signals);report['account_sha256']=row['sha256'];passed.append(report)
        except Exception as exc:failures.append({'account':row['artifact'],'error':repr(exc),'traceback':traceback.format_exc()})
    result={'at':datetime.now(timezone.utc).isoformat(),'status':'passed' if not failures else 'failed','attempt':completed['attempt'],
        'definition_sha256':completed['definition_sha256'],'planned_accounts':12,'passed_accounts':len(passed),'failures':failures,
        'accounts':passed,'trades_checked':sum(x['trades'] for x in passed),'daily_rows_checked':sum(x['daily_rows'] for x in passed),
        'frozen_input_files_checked':len(definition['files']),'frozen_output_files_checked':len(completed['files']),
        'independence':'No simulator/policy/strategy imports; prior independent banking-date helpers reused; Decimal fee, quantity, cash, mark and reservation arithmetic.',
        'limits':['Source panel and causal signal derivation reviewed separately; this auditor binds their frozen arrays/rankings.',
          'Adjusted-notional marks preserve synthetic action convention, not actual broker share/cash action accounting.',
          'Current tariff counterfactual plus15bps scenario excludes fixed account/funding/personal tax and unverified execution costs.',
          'Passing ledger arithmetic does not qualify profitability or any live/paper promotion.']}
    output=OUT/('audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(output),'status':result['status'],'passed_accounts':len(passed),'trades_checked':result['trades_checked'],'failures':failures},indent=2))
    if failures:raise SystemExit(1)
if __name__=='__main__':main(sys.argv[1])

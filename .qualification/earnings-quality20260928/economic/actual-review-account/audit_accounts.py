"""Independent actual earnings ledgers: reuse checked Decimal fee/calendar routines; no simulator imports."""
import json,math,hashlib,importlib.util,traceback,sys,copy
from pathlib import Path
from decimal import Decimal
from datetime import date,datetime,timezone
from collections import defaultdict,Counter
from statistics import median
import numpy as np
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
REPO=ROOT.parents[2]
OLD=REPO/'.qualification/post-filing-strategy20260928/account-audit/audit_accounts.py'
spec=importlib.util.spec_from_file_location('prior_earnings_arithmetic_checker',OLD);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
D=Decimal
read,sha,near,fee,maxq,banking_holidays=old.read,old.sha,old.near,old.fee,old.maxq,old.banking_holidays
LEARNED=('ridge','hist_gradient_boosting')
def check_projection(p,profile):
    q=int(p['quantity']);n=D(q)*D(str(p['price']));mu=D(str(p['mu']));down=D(str(p['downside']));ex=n*(1+mu)
    entry=D(str(fee(q,n,'buy',profile)));exit=D(str(fee(q,ex,'sell',profile)));utility=n*mu-entry-exit-D('.5')*n*down
    for k,v in [('notional',n),('projected_exit_notional',ex),('entry_fee',entry),('exit_fee',exit),('utility',utility),('utility_fraction',utility/n)]:near(p[k],v,'projection '+k)
    assert mu>-1 and down>=0

def weekly_checks(a):
    weeks=a['period_returns']['weekly'];values=[r['return'] for r in weeks];w=a['weekly_objective']
    assert w['status']=='complete' and w['count']==len(values) and w['all_idle_and_losing_weeks_retained']
    roles=defaultdict(set)
    for c in a['equity_curve']:
        day=c['session'];y,wk,_=date.fromisoformat(day).isocalendar();role='initialization' if day<'2021-01-01' else 'liquidation_tail' if day>'2025-12-31' else 'entry_period';roles[f'{y}-W{wk:02d}'].add(role)
    for r in weeks:
        expected=sorted(roles[r['period']]);assert r['interval_roles']==expected and r['interval_role']==(expected[0] if len(expected)==1 else 'mixed')
    for target in (.05,.10,.15):
        t=w['targets'][str(target)];assert t['hits']==sum(v>=target for v in values) and t['denominator']==len(values);near(t['fraction'],t['hits']/len(values),'weekly target ratio',1e-12)
    near(w['median_return'],median(values),'median week',1e-12);near(w['worst_return'],min(values),'worst week',1e-12)
    streak=longest=0
    for v in values:streak=streak+1 if v<0 else 0;longest=max(longest,streak)
    assert w['longest_losing_streak']==longest

def audit_account(a,m,z,events,forecasts):
    assert a['status']=='complete' and not a['missing']
    sessions=m['sessions'];index={s:i for i,s in enumerate(sessions)};symbols={s:i for i,s in enumerate(m['symbols'])}
    profile={'proportional_40bps':'proportional','moomoo_ca_us_plus_40bps':'moomoo_ca_us'}[a['cost_profile']];trades=a['trade_records'];intents=a['intents'];curves=a['equity_curve'];state_rows=a['daily_state']
    bytrade={t['event_id']:t for t in trades};assert len(bytrade)==len(trades)
    byintent={o['event_id']:o for o in intents};assert len(byintent)==len(intents)
    ins=defaultdict(list);outs=defaultdict(list);planning=defaultdict(list)
    cents_total=D(0);gross_total=D(0);net_total=D(0);price_checks=0;marks_checked=0
    for o in intents:
        e=events[o['event_id']];j=symbols[o['symbol']];r=index[o['prior_price_session']];entry=index[o['entry_session']]
        assert e['feature_status']==e['execution_status']=='qualified'
        assert a['recipe'] not in ('income_surprise','income_cash_confirmation') or D(e['S'])>=1
        assert a['recipe']!='income_cash_confirmation' or D(e['Q'])>0
        assert all(e.get(k)=='qualified' for k in ('q_status','joint_feature_status','strategy_source_status','model_input_status'))
        assert o['prepared_event_sha256']==hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if a['recipe'] in LEARNED:
            f=forecasts[a['recipe']][o['event_id']];assert o['forecast']==f and f['prepared_row_sha256']==o['prepared_event_sha256'];check_projection(o['reference_projection'],profile);assert o['reference_projection']['utility']>0
            assert o['reference_projection']['mu']==f['corrected'][0] and o['reference_projection']['downside']==f['corrected'][1]
        for k in ['symbol','decision_time','availability_floor','entry_session','exit_session','S','Q','cik']:assert o[k]==e[k],k
        assert entry==r+1 and index[o['exit_session']]==entry+5
        q=o['original_quantity'];assert isinstance(q,int) and q>0
        near(o['reference_price'],z['close'][r,j],'reference source price',1e-10)
        near(o['fill_reference_price'],z['close'][entry,j],'fill source price',1e-10)
        near(o['reserved_cash'],q*o['reference_price']+fee(q,q*o['reference_price'],'buy',profile),'original reserve')
        capped=maxq(q,o['fill_reference_price'],o['reserved_cash'],profile)
        assert capped==o['reservation_capped_quantity'],(o['event_id'],'reservation cap')
        planning[r].append(o);ins[entry].append(o);price_checks+=2
    for t in trades:
        o=byintent[t['event_id']];j=symbols[t['symbol']];entry=index[t['entry_session']];exit=index[t['exit_session']]
        q=t['quantity'];assert isinstance(q,int) and 0<q<=o['original_quantity']
        assert o.get('filled_quantity')==q and t['original_quantity']==o['original_quantity']
        near(t['reserved_cash'],o['reserved_cash'],'trade reserve');assert t['entry_notional']+t['entry_fee']<=t['reserved_cash']+1e-7
        en=q*float(z['close'][entry,j]);ex=en*float(z['adjusted'][exit,j])/float(z['adjusted'][entry,j])
        near(t['entry_notional'],en,'source entry');near(t['exit_notional'],ex,'source adjusted exit')
        ef,xf=fee(q,en,'buy',profile),fee(q,ex,'sell',profile)
        near(t['entry_fee'],ef,'entry fee');near(t['exit_fee'],xf,'exit fee')
        near(t['gross_pnl'],ex-en,'gross');near(t['net_pnl'],ex-en-ef-xf,'net');near(t['net_return'],(ex-en-ef-xf)/en,'trade return',1e-10)
        assert exit-entry==t['holding_sessions']==5
        assert (date.fromisoformat(t['exit_session'])-date.fromisoformat(t['entry_session'])).days==t['holding_calendar_days']
        lag=1 if t['exit_session']>='2024-05-28' else 2 if t['exit_session']>='2017-09-05' else 3
        eligible=[k for k in range(exit+1,exit+12) if date.fromisoformat(sessions[k]) not in banking_holidays(int(sessions[k][:4]))]
        assert t['settlement_index']==int(z['settlement_index'][exit])==eligible[lag-1]
        outs[exit].append(t);cents_total+=D(str(ef))+D(str(xf));gross_total+=D(str(ex))-D(str(en));net_total+=D(str(ex))-D(str(en))-D(str(ef))-D(str(xf));price_checks+=2
    cash=D(a['starting_capital']);settled=D(a['starting_capital']);receivables=[];held={};rebuilt=[];max_cash_error=0.;max_equity_error=0.;min_settled=D(a['starting_capital'])
    for c,ds in zip(curves,state_rows,strict=True):
        s=c['session'];i=index[s];assert ds['session']==s
        settled+=sum((v for due,v in receivables if due<=i),D(0));receivables=[(due,v) for due,v in receivables if due>i]
        marks={a:D(str(t['entry_notional']))*D(str(float(z['adjusted'][i,symbols[t['symbol']]])))/D(str(float(z['adjusted'][index[t['entry_session']],symbols[t['symbol']]]))) for a,t in held.items()};marks_checked+=len(marks)
        for t in outs[i]:
            assert t['event_id'] in held
            near(marks.pop(t['event_id']),t['exit_notional'],'exit mark')
            proceeds=D(str(t['exit_notional']))-D(str(t['exit_fee']));cash+=proceeds
            if proceeds<0:settled+=proceeds
            else:receivables.append((t['settlement_index'],proceeds))
            del held[t['event_id']]
        nav=cash+sum(marks.values(),D(0))
        for o in ins[i]:
            q=maxq(o['reservation_capped_quantity'],o['fill_reference_price'],min(.2*float(nav),float(settled)),profile)
            t=bytrade.get(o['event_id'])
            if a['recipe'] in LEARNED and q:
                projection=o['fill_check']['projection'];check_projection(projection,profile);assert projection['quantity']==q
                assert projection['mu']==o['forecast']['corrected'][0] and projection['downside']==o['forecast']['corrected'][1]
                expected_accept=projection['utility']>0;assert o['fill_check']['accepted']==expected_accept
                if not expected_accept:q=0
            assert q==(t['quantity'] if t else 0),(o['event_id'],'actual cap',q)
            if not q:continue
            assert t['symbol'] not in [v['symbol'] for v in held.values()] and len(held)<5
            spend=D(str(t['entry_notional']))+D(str(t['entry_fee']));cash-=spend;settled-=spend;nav-=D(str(t['entry_fee']))
            held[t['event_id']]=t;marks[t['event_id']]=D(str(t['entry_notional']))
        equity=cash+sum(marks.values(),D(0));unsettled=sum((v for _,v in receivables),D(0));min_settled=min(min_settled,settled)
        assert cash>=0 and settled>=0
        for k,v in [('cash',cash),('settled_cash',settled),('unsettled_cash',unsettled),('equity',equity)]:near(c[k],v,'daily '+k)
        near(cash,settled+unsettled,'cash identity')
        max_cash_error=max(max_cash_error,abs(float(cash)-c['cash']));max_equity_error=max(max_equity_error,abs(float(equity)-c['equity']))
        assert len(ds['held'])==len(held) and len(ds['pending'])==len(planning[i])
        for saved,t in zip(ds['held'],held.values(),strict=True):
            for k,v in [('symbol_index',symbols[t['symbol']]),('quantity',t['quantity']),('entry',index[t['entry_session']]),('exit',index[t['exit_session']])]:assert saved[k]==v
            near(saved['notional'],t['entry_notional'],'held notional')
        for saved,o in zip(ds['pending'],planning[i],strict=True):assert saved['quantity']==o['original_quantity'] and saved['symbol_index']==symbols[o['symbol']] and saved['signal']==i
        assert len(ds['receivables'])==len(receivables)
        for x,(due,v) in zip(ds['receivables'],receivables):assert x['due_index']==due;near(x['amount'],v,'receivable')
        available=settled+sum((v for due,v in receivables if due<=i+1),D(0))
        heldnames={t['symbol'] for t in held.values()}
        for o in planning[i]:
            assert o['symbol'] not in heldnames
            risk=math.floor(.005*float(equity)/(2*float(z['atr'][i,symbols[o['symbol']]])))
            expected=maxq(risk,o['reference_price'],min(.2*float(equity),float(available)),profile)
            assert o['original_quantity']==expected,(o['event_id'],'original sizing',o['original_quantity'],expected)
            available-=D(str(o['reserved_cash']));assert available>=D('-0.0000001')
        rebuilt.append(float(equity))
    assert not held and not receivables and not a['final_state']['held'] and not a['final_state']['pending'] and not a['final_state']['receivables']
    near(a['ending_equity'],D(a['starting_capital'])+net_total,'flat ending NAV');near(a['final_state']['cash'],cash,'final cash');near(a['final_state']['settled_cash'],settled,'final settled')
    near(a['fees'],cents_total,'total fees');near(a['trade_metrics']['net_pnl_total'],net_total,'net total');near(a['trade_metrics']['net_expectancy_native'],net_total/len(trades),'dollar expectancy')
    near(a['total_return'],float(net_total)/a['starting_capital'],'account return',1e-10)
    peak=float(a['starting_capital']);dd=0.
    for value in rebuilt:peak=max(peak,value);dd=max(dd,1-value/peak)
    near(a['max_drawdown'],dd,'maximum drawdown',1e-10)
    exposure=sum(1-c['cash']/c['equity'] for c in curves)/len(curves);near(a['trade_metrics']['mean_exposure_fraction'],exposure,'exposure',1e-10)
    turnover=sum(t['entry_notional']+t['exit_notional'] for t in trades)/(sum(rebuilt)/len(rebuilt));near(a['trade_metrics']['turnover'],turnover,'turnover',1e-10)
    period_checks=0
    for frequency,rows in a['period_returns'].items():
        grouped={}
        for c in curves:
            d=date.fromisoformat(c['session']);iso=d.isocalendar();key=f'{iso.year}-W{iso.week:02d}' if frequency=='weekly' else c['session'][:7];grouped[key]=c
        before=float(a['starting_capital']);assert len(rows)==len(grouped)
        for r,(key,c) in zip(rows,grouped.items()):
            assert r['period']==key and r['last_session']==c['session'];near(r['return'],c['equity']/before-1,'period return',1e-10);before=c['equity'];period_checks+=1
    before=float(a['starting_capital'])
    for yr in a['yearly']:
        values=[c['equity'] for c in curves if c['session'].startswith(yr['year'])];near(yr['return'],values[-1]/before-1,'year return',1e-10)
        pk=before;ydd=0.
        for v in values:pk=max(pk,v);ydd=max(ydd,1-v/pk)
        near(yr['max_drawdown'],ydd,'year drawdown',1e-10);before=values[-1];period_checks+=1
    weekly_checks(a)
    projection_count=0
    for record in a.get('policy_audit',[]):
        if record.get('phase')=='full_selection':
            for decision in record['decisions']:
                if 'utility' in decision:check_projection(decision,profile);projection_count+=1
    return {'recipe':a['recipe'],'capital':a['starting_capital'],'planner_projections_checked':projection_count,'weekly_objective':a['weekly_objective'],'account_total_return':a['total_return'],'drawdown_qualification_exceeded':a['max_drawdown']>.3,'cost_profile':profile,'status':'passed','completed_trades':len(trades),'intents':len(intents),'zero_fill_intents':len(intents)-len(trades),'daily_rows':len(curves),'held_marks':marks_checked,'source_price_checks':price_checks,'period_rows':period_checks,'net_pnl':float(net_total),'gross_pnl':float(gross_total),'fees':float(cents_total),'ending_equity':float(cash),'max_drawdown':dd,'mean_exposure_fraction':exposure,'minimum_settled_cash':float(min_settled),'maximum_daily_cash_difference':max_cash_error,'maximum_daily_equity_difference':max_equity_error}

def main(attempt_path):
    attempt=Path(attempt_path).resolve();completion=read(attempt/'completion.json');definition=read(ROOT/'definition-20260929.json')
    assert completion['status']=='complete' and sha(ROOT/'definition-20260929.json')==completion['definition_sha256']=='518039219b5b7be3935fb788f14ffacc23b90cb73033411414d7fb1d70a1859f'
    outputs=completion['outputs']
    for name,h in outputs.items():assert sha(attempt/name)==h,name
    bound=read(attempt/'bound-inputs.json')
    for name,h in bound.items():
        p=Path(name);p=p if p.is_absolute() else REPO/p
        assert sha(p)==h,name
    declared=read(attempt/'declared-attempts.json');summary=read(attempt/'accounts/summary.json');assert len(summary)==len(declared['accounts'])==20
    expected=[(r['recipe'],r['starting_capital'],r['cost_profile']) for r in declared['accounts']]
    assert len(set(expected))==20 and [(r['recipe'],r['starting_capital'],r['cost_profile']) for r in summary]==expected
    paths=definition['paths'];m=read(REPO/paths['market_inputs']);z=np.load(REPO/paths['market_arrays'],allow_pickle=False);events={r['event_id']:r for r in read(attempt/'prepared-events.json')['rows']}
    forecasts={family:{r['event_id']:r for r in read(attempt/'models'/(family+'-all-forecasts.json'))['forecasts']} for family in LEARNED}
    results=[];failures=[];originals={}
    for row in summary:
        name=f"{row['recipe']}-{row['starting_capital']}-{row['cost_profile']}";path=attempt/'accounts'/(name+'.json')
        try:
            a=read(path);originals[name]=a
            for k,v in row.items():assert a.get(k)==v,(name,k,'summary differs')
            assert not a['synthetic_interval_override'] and a['holding_sessions']==5
            first=next(i for i,s in enumerate(m['sessions']) if s>='2021-01-01')-1;last=m['sessions'].index('2026-01-16')
            assert [r['session'] for r in a['equity_curve']]==m['sessions'][first:last+1]
            result=audit_account(a,m,z,events,forecasts);result['account_sha256']=sha(path);results.append(result)
        except Exception as exc:failures.append({'account':name,'error':repr(exc),'traceback':traceback.format_exc()})
    probes=[]
    if not failures:
        sample=originals['filing_control-10000-proportional_40bps']
        for field in ('entry_fee','reserved_cash','quantity'):
            damaged=copy.deepcopy(sample);damaged['trade_records'][0][field]+=1
            try:audit_account(damaged,m,z,events,forecasts)
            except AssertionError:probes.append({'mutation':field,'detected':True})
            else:raise AssertionError('Mutation not detected: '+field)
        damaged=copy.deepcopy(sample);damaged['period_returns']['weekly']=damaged['period_returns']['weekly'][1:]
        try:audit_account(damaged,m,z,events,forecasts)
        except AssertionError:probes.append({'mutation':'removed idle week','detected':True})
        else:raise AssertionError('Missing idle week not detected')
    references=read(attempt/'references.json');reference_checks=[]
    first=next(i for i,s in enumerate(m['sessions']) if s>='2021-01-01')-1;last=m['sessions'].index('2026-01-16');benchmark=m['benchmark'];prices=z['adjusted'][first:last+1,benchmark]
    for capital in (10000,2000):
        r=references[str(capital)]['SPY'];expected_equity=capital*prices/prices[0]
        assert r['first_session']==m['sessions'][first] and r['last_session']==m['sessions'][last]
        for saved,value in zip(r['equity_curve'],expected_equity,strict=True):near(saved['equity'],value,'benchmark NAV')
        near(r['total_return'],expected_equity[-1]/capital-1,'benchmark cumulative return',1e-12);reference_checks.append({'capital':capital,'total_return':r['total_return'],'daily_rows':len(expected_equity),'convention':r['convention']})
    report={'at':datetime.now(timezone.utc).isoformat(),'status':'passed' if not failures else 'failed','attempt':str(attempt),'definition_sha256':completion['definition_sha256'],'audit_code_sha256':sha(Path(__file__)),'reused_checker_sha256':sha(OLD),'bound_inputs_checked':len(bound),'outputs_checked':len(outputs),'declared_accounts':20,'passed_accounts':len(results),'failures':failures,'accounts':results,'total_trades_checked':sum(r['completed_trades'] for r in results),'daily_rows_checked':sum(r['daily_rows'] for r in results),'reference_checks':reference_checks,'mutation_probes':probes,'limits':['No simulator/policy/model fitting imports. Reused prior independent Decimal fee sizing and banking calendar routines.','Source-price check uses previously independently checked frozen market arrays; every bound input identity checked afresh.','Recorded candidate/planner proposals checked, but full omitted-candidate completeness is not independently rerun.','40bps is a sensitivity plus current tariff counterfactual, not verified fills; taxes, FX and full corporate-action cash ledger excluded.','Account drawdown is a qualification limit, not an automatic halt in this frozen design. Passing arithmetic is not economic qualification.']}
    out=OUT/('audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'path':str(out),'sha256':sha(out),'status':report['status'],'passed_accounts':len(results),'trades':report['total_trades_checked'],'failures':failures},indent=2))
    if failures:raise SystemExit(1)
if __name__=='__main__':main(sys.argv[1])

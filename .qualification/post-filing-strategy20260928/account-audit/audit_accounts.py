"""Independent recorded-ledger audit; no engine, policy or source parser imports."""
import json, math, hashlib
from pathlib import Path
from decimal import Decimal, ROUND_CEILING
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict, Counter
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
D=Decimal

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def near(a,b,label,tol=1e-7):
    assert abs(float(a)-float(b))<=tol,(label,a,b,float(a)-float(b))
def fee(q,n,side,profile):
    if not q:return 0.
    n=D(str(n)); explicit=D(0)
    if profile=='moomoo_ca_us':
        rates=('0.0005','0.0005') if n<D(q) else ('0.0049','0.005')
        explicit=sum(max(floor,D(q)*D(rate)).quantize(D('.01'),rounding=ROUND_CEILING)
                     for floor,rate in zip((D('.99'),D('1.00')),rates))
        if side=='sell':explicit+=max(D('.01'),n*D('.0000206')).quantize(D('.01'),rounding=ROUND_CEILING)
    return float(explicit+n*D('.002'))
def maxq(q,price,budget,profile):
    # Descending enumeration is independent of the engine's binary search.
    return next((v for v in range(int(q),-1,-1) if v*price+fee(v,v*price,'buy',profile)<=budget+1e-11),0)
def nth(year,month,weekday,n):
    x=date(year,month,1);return x+timedelta(days=(weekday-x.weekday())%7+7*(n-1))
def banking_holidays(year):
    fixed=[(1,1),(7,4),(11,11),(12,25)]+([(6,19)] if year>=2022 else [])
    days={date(year,m,d)+timedelta(days=(date(year,m,d).weekday()==6)) for m,d in fixed}
    days.update((nth(year,1,0,3),nth(year,2,0,3),nth(year,9,0,1),nth(year,10,0,2),nth(year,11,3,4)))
    x=date(year,5,31);days.add(x-timedelta(days=x.weekday()))
    return days

def audit_account(a,m,z,events):
    assert a['status']=='complete' and not a['missing']
    sessions=m['sessions'];index={s:i for i,s in enumerate(sessions)};symbols={s:i for i,s in enumerate(m['symbols'])}
    profile=a['cost_profile'];trades=a['trade_records'];intents=a['intents'];curves=a['equity_curve'];state_rows=a['daily_state']
    bytrade={t['accession']:t for t in trades};assert len(bytrade)==len(trades)
    byintent={o['accession']:o for o in intents};assert len(byintent)==len(intents)
    ins=defaultdict(list);outs=defaultdict(list);planning=defaultdict(list)
    cents_total=D(0);gross_total=D(0);net_total=D(0);price_checks=0;marks_checked=0
    for o in intents:
        e=events[o['accession']];j=symbols[o['symbol']];r=index[o['prior_price_session']];entry=index[o['entry_session']]
        assert e['feature_status']==e['execution_status']=='qualified'
        assert a['arm']=='filing_control' or e['selected']
        for k in ['symbol','decision_time','availability_floor','entry_session','exit_session','S']:assert o[k]==e[k],k
        assert entry==r+1 and index[o['exit_session']]==entry+5
        q=o['original_quantity'];assert isinstance(q,int) and q>0
        near(o['reference_price'],z['close'][r,j],'reference source price',1e-10)
        near(o['fill_reference_price'],z['close'][entry,j],'fill source price',1e-10)
        near(o['reserved_cash'],q*o['reference_price']+fee(q,q*o['reference_price'],'buy',profile),'original reserve')
        capped=maxq(q,o['fill_reference_price'],o['reserved_cash'],profile)
        assert capped==o['reservation_capped_quantity'],(o['accession'],'reservation cap')
        planning[r].append(o);ins[entry].append(o);price_checks+=2
    for t in trades:
        o=byintent[t['accession']];j=symbols[t['symbol']];entry=index[t['entry_session']];exit=index[t['exit_session']]
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
    cash=D(2000);settled=D(2000);receivables=[];held={};rebuilt=[];max_cash_error=0.;max_equity_error=0.;min_settled=D(2000)
    for c,ds in zip(curves,state_rows,strict=True):
        s=c['session'];i=index[s];assert ds['session']==s
        settled+=sum((v for due,v in receivables if due<=i),D(0));receivables=[(due,v) for due,v in receivables if due>i]
        marks={a:D(str(t['entry_notional']))*D(str(float(z['adjusted'][i,symbols[t['symbol']]])))/D(str(float(z['adjusted'][index[t['entry_session']],symbols[t['symbol']]]))) for a,t in held.items()};marks_checked+=len(marks)
        for t in outs[i]:
            assert t['accession'] in held
            near(marks.pop(t['accession']),t['exit_notional'],'exit mark')
            proceeds=D(str(t['exit_notional']))-D(str(t['exit_fee']));cash+=proceeds
            if proceeds<0:settled+=proceeds
            else:receivables.append((t['settlement_index'],proceeds))
            del held[t['accession']]
        nav=cash+sum(marks.values(),D(0))
        for o in ins[i]:
            q=maxq(o['reservation_capped_quantity'],o['fill_reference_price'],min(.2*float(nav),float(settled)),profile)
            t=bytrade.get(o['accession']);assert q==(t['quantity'] if t else 0),(o['accession'],'actual cap',q)
            if not q:continue
            assert t['symbol'] not in [v['symbol'] for v in held.values()] and len(held)<5
            spend=D(str(t['entry_notional']))+D(str(t['entry_fee']));cash-=spend;settled-=spend;nav-=D(str(t['entry_fee']))
            held[t['accession']]=t;marks[t['accession']]=D(str(t['entry_notional']))
        equity=cash+sum(marks.values(),D(0));unsettled=sum((v for _,v in receivables),D(0));min_settled=min(min_settled,settled)
        assert cash>=0 and settled>=0
        for k,v in [('cash',cash),('settled_cash',settled),('unsettled_cash',unsettled),('equity',equity)]:near(c[k],v,'daily '+k)
        near(cash,settled+unsettled,'cash identity')
        max_cash_error=max(max_cash_error,abs(float(cash)-c['cash']));max_equity_error=max(max_equity_error,abs(float(equity)-c['equity']))
        assert ds['held_positions']==len(held) and ds['pending_orders']==len(planning[i])
        assert len(ds['receivables'])==len(receivables)
        for x,(due,v) in zip(ds['receivables'],receivables):assert x['due_index']==due;near(x['amount'],v,'receivable')
        available=settled+sum((v for due,v in receivables if due<=i+1),D(0))
        heldnames={t['symbol'] for t in held.values()}
        for o in planning[i]:
            assert o['symbol'] not in heldnames
            risk=math.floor(.005*float(equity)/(2*float(z['atr'][i,symbols[o['symbol']]])))
            expected=maxq(risk,o['reference_price'],min(.2*float(equity),float(available)),profile)
            assert o['original_quantity']==expected,(o['accession'],'original sizing',o['original_quantity'],expected)
            available-=D(str(o['reserved_cash']));assert available>=D('-0.0000001')
        rebuilt.append(float(equity))
    assert not held and not receivables and not a['final_state']['held'] and not a['final_state']['pending'] and not a['final_state']['receivables']
    near(a['ending_equity'],D(2000)+net_total,'flat ending NAV');near(a['final_state']['cash'],cash,'final cash');near(a['final_state']['settled_cash'],settled,'final settled')
    near(a['fees'],cents_total,'total fees');near(a['trade_metrics']['net_pnl_total'],net_total,'net total');near(a['trade_metrics']['net_expectancy_native'],net_total/len(trades),'dollar expectancy')
    near(a['total_return'],float(net_total)/2000,'account return',1e-10)
    peak=2000.;dd=0.
    for value in rebuilt:peak=max(peak,value);dd=max(dd,1-value/peak)
    near(a['max_drawdown'],dd,'maximum drawdown',1e-10)
    exposure=sum(1-c['cash']/c['equity'] for c in curves)/len(curves);near(a['trade_metrics']['mean_exposure_fraction'],exposure,'exposure',1e-10)
    turnover=sum(t['entry_notional']+t['exit_notional'] for t in trades)/(sum(rebuilt)/len(rebuilt));near(a['trade_metrics']['turnover'],turnover,'turnover',1e-10)
    period_checks=0
    for frequency,rows in a['period_returns'].items():
        grouped={}
        for c in curves:
            d=date.fromisoformat(c['session']);iso=d.isocalendar();key=f'{iso.year}-W{iso.week:02d}' if frequency=='weekly' else c['session'][:7];grouped[key]=c
        before=2000.;assert len(rows)==len(grouped)
        for r,(key,c) in zip(rows,grouped.items()):
            assert r['period']==key and r['last_session']==c['session'];near(r['return'],c['equity']/before-1,'period return',1e-10);before=c['equity'];period_checks+=1
    before=2000.
    for yr in a['yearly']:
        values=[c['equity'] for c in curves if c['session'].startswith(yr['year'])];near(yr['return'],values[-1]/before-1,'year return',1e-10)
        pk=before;ydd=0.
        for v in values:pk=max(pk,v);ydd=max(ydd,1-v/pk)
        near(yr['max_drawdown'],ydd,'year drawdown',1e-10);before=values[-1];period_checks+=1
    return {'arm':a['arm'],'cost_profile':profile,'status':'passed','completed_trades':len(trades),'intents':len(intents),'zero_fill_intents':len(intents)-len(trades),'daily_rows':len(curves),'held_marks':marks_checked,'source_price_checks':price_checks,'period_rows':period_checks,'net_pnl':float(net_total),'gross_pnl':float(gross_total),'fees':float(cents_total),'ending_equity':float(cash),'max_drawdown':dd,'mean_exposure_fraction':exposure,'minimum_settled_cash':float(min_settled),'maximum_daily_cash_difference':max_cash_error,'maximum_daily_equity_difference':max_equity_error}

def main():
    completed=read(ROOT/'completed.json');definition=read(ROOT/'definition.json');assert sha(ROOT/'definition.json')==completed['definition_sha256']
    for name,value in completed['files'].items():assert sha(ROOT/name)==value,name
    for name,value in definition['files'].items():assert sha(REPO/name)==value,name
    summary=read(ROOT/completed['summary']);attempt=(ROOT/completed['summary']).parent
    request=read(ROOT/'request.json');events={e['accession']:e for e in read(REPO/request['events'])}
    m=read(ROOT/'market-inputs.json');assert sha(ROOT/'market-arrays.npz')==m['arrays_sha256']
    z=np.load(ROOT/'market-arrays.npz');results=[];failures=[]
    for row in summary['accounts']:
        try:
            report=audit_account(read(attempt/row['artifact']),m,z,events);report['account_sha256']=row['sha256'];results.append(report)
        except Exception as error:
            import traceback
            failures.append({'arm':row['arm'],'cost_profile':row['cost_profile'],'error':repr(error),'traceback':traceback.format_exc()})
    paired=[]
    if not failures:
        for profile in ['proportional','moomoo_ca_us']:
            t=next(x for x in results if x['arm']=='income_surprise' and x['cost_profile']==profile);c=next(x for x in results if x['arm']=='filing_control' and x['cost_profile']==profile)
            delta=t['net_pnl']-c['net_pnl'];paired.append({'cost_profile':profile,'treatment_minus_control_net_dollars':delta,'treatment_minus_control_return_percentage_points':delta/20,'gross_dollar_difference':t['gross_pnl']-c['gross_pnl'],'fee_saving':c['fees']-t['fees'],'difference_identity_residual':delta-((t['gross_pnl']-c['gross_pnl'])+(c['fees']-t['fees']))})
    report={'at':datetime.now(timezone.utc).isoformat(),'status':'passed' if not failures else 'failed','definition_sha256':completed['definition_sha256'],'completed_pointer_sha256':sha(ROOT/'completed.json'),'definition_files_checked':len(definition['files']),'completed_files_checked':len(completed['files']),'planned_accounts':4,'passed_accounts':len(results),'audit_failures':failures,'accounts':results,'paired_comparisons':paired,'total_completed_trades_checked':sum(r['completed_trades'] for r in results),'limits':['Recorded selections and orders only: omitted candidate completeness not independently rerun.','Source price comparisons use hashed frozen market arrays; original raw/adjusted prices and ATRs independently checked by source audit before launch.','Adjusted-notional marks/exits and original entry whole quantities are retained conventions, not action-complete broker share/cash accounting.','Settlement is declared exchange/banking intersection, not broker posting reconstruction.','40bps remains sensitivity; current Moomoo tariffs are counterfactual and omit funding/account/other charges.','Financial sample has only27 selected events and19 executed treatment trades; arithmetic passing does not qualify profitability.']}
    out=Path(__file__).parent/('audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');out.write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(out),**report},indent=2))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()

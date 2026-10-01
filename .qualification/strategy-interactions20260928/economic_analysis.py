"""Economic readout of the 54 frozen strategy accounts; never tunes the worker."""
from collections import Counter, defaultdict
from datetime import date
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[1]
CONTRASTS=[
 ('beta_residual_reversal_2','relative_reversal_2'),
 ('trend_conditioned_reversal_5','relative_reversal_5'),
 ('compression_continuation_5','relative_volume_continuation_5'),
 ('equal_percentile_blend','relative_reversal_5'),
 ('equal_percentile_blend','relative_volume_continuation_5'),
 ('volatility_regime_selector','equal_percentile_blend'),
]

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def check(a,b,label):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-7),(label,a,b)
def mean(values):return statistics.mean(values) if values else None
def median(values):return statistics.median(values) if values else None
def divide(a,b):return a/b if b else None

def periods(curve,budget,frequency):
    ends={}
    for item in curve:
        d=date.fromisoformat(item['session']);iso=d.isocalendar()
        key=f'{iso.year}-W{iso.week:02}' if frequency=='weekly' else item['session'][:7] if frequency=='monthly' else item['session'][:4]
        ends[key]=(item['session'],item['equity'])
    previous=budget;rows=[]
    for key,(session,equity) in ends.items():
        rows.append(dict(period=key,last_session=session,**{'return':equity/previous-1}))
        previous=equity
    check(math.prod(1+r['return'] for r in rows),curve[-1]['equity']/budget,frequency+' compounding')
    return rows

def account_readout(report,budget):
    row={k:report.get(k) for k in ['policy','horizon','cost_profile','status','error','missing','total_return','max_drawdown','ending_equity','cagr','annualized_volatility']}
    if report['status']!='complete':
        row['economic_metrics_valid']=False
        for key in ['total_return','max_drawdown','ending_equity','cagr','annualized_volatility']:
            row[key]=None
        row['retained_partial_trade_records']=len(report.get('trade_records',[]))
        return row
    curve=report['equity_curve'];trades=report.get('trade_records',[]);metrics=report['trade_metrics']
    assert curve and all(math.isfinite(r['equity']) and r['equity']>0 for r in curve)
    assert len(curve)==len({r['session'] for r in curve}) and [r['session'] for r in curve]==sorted(r['session'] for r in curve)
    equity=[r['equity'] for r in curve];cash=[r['cash'] for r in curve]
    gross=sum(t['exit_notional']-t['entry_notional'] for t in trades)
    net=sum(t['net_pnl'] for t in trades);fees=sum(t['entry_fee']+t['exit_fee'] for t in trades)
    for trade in trades:
        check(trade['net_pnl'],trade['exit_notional']-trade['entry_notional']-trade['entry_fee']-trade['exit_fee'],'trade net')
        check(trade['net_return'],trade['net_pnl']/trade['entry_notional'],'trade return')
        assert trade['holding_sessions']==report['horizon']
    # The complete fixed-hold engine flattens before the final test boundary.
    check(cash[-1],equity[-1],'complete path flat cash')
    check(equity[-1],budget+net,'ending NAV = capital + all completed net PnL')
    check(gross-fees,net,'gross minus fees')
    check(fees,report['fees'],'reported fees')
    check(net,metrics['net_pnl_total'],'reported net PnL')
    assert len(trades)==report['trades']==metrics['completed_trades']
    returns=[equity[i]/equity[i-1]-1 for i in range(1,len(equity))]
    check(math.prod(1+r for r in returns),equity[-1]/equity[0],'daily compounding')
    check(equity[-1]/budget-1,report['total_return'],'total return')
    peak=budget;drawdown=0.0
    for value in equity:peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
    check(drawdown,report['max_drawdown'],'drawdown')
    exposure=mean([1-c/e for c,e in zip(cash,equity)])
    turnover=sum(t['entry_notional']+t['exit_notional'] for t in trades)/mean(equity)
    check(exposure,metrics['mean_exposure_fraction'],'exposure');check(turnover,metrics['turnover'],'turnover')
    completed_periods={freq:periods(curve,budget,freq) for freq in ['weekly','monthly','yearly']}
    for frequency in ['weekly','monthly']:
        expected=completed_periods[frequency];actual=report['period_returns'][frequency]
        assert len(expected)==len(actual)
        for a,b in zip(expected,actual):
            assert a['period']==b['period'] and a['last_session']==b['last_session']
            check(a['return'],b['return'],frequency+' return')
    assert len(completed_periods['yearly'])==len(report['yearly'])
    for a,b in zip(completed_periods['yearly'],report['yearly']):
        assert a['period']==b['year'];check(a['return'],b['return'],'yearly return')
    period_metrics={}
    for frequency,values in completed_periods.items():
        r=[x['return'] for x in values]
        period_metrics[frequency]=dict(period_count=len(r),profitable_count=sum(x>0 for x in r),profitable_fraction=sum(x>0 for x in r)/len(r),
                                       mean_return=mean(r),median_return=median(r),worst_return=min(r),best_return=max(r),values=values)
    positive=[t['net_pnl'] for t in trades if t['net_pnl']>0]
    negative=[t['net_pnl'] for t in trades if t['net_pnl']<0]
    symbols=defaultdict(float)
    for t in trades:symbols[t['symbol']]+=t['net_pnl']
    positive_symbols=sorted([(s,p) for s,p in symbols.items() if p>0],key=lambda x:-x[1])
    winners=sorted(positive,reverse=True)
    concentration=dict(largest_trade_share_of_positive_trade_pnl=divide(winners[0],sum(positive)) if positive else None,
                       top_five_trades_share_of_positive_trade_pnl=divide(sum(winners[:5]),sum(positive)),
                       top_symbol_share_of_positive_symbol_net_pnl=divide(positive_symbols[0][1],sum(p for s,p in positive_symbols)) if positive_symbols else None,
                       best_symbols=sorted(symbols.items(),key=lambda x:(-x[1],x[0]))[:5],worst_symbols=sorted(symbols.items(),key=lambda x:(x[1],x[0]))[:5],
                       best_trades=[{k:t[k] for k in ['symbol','signal_session','entry_session','exit_session','entry_notional','net_pnl','net_return']} for t in sorted(trades,key=lambda t:-t['net_pnl'])[:3]],
                       worst_trades=[{k:t[k] for k in ['symbol','signal_session','entry_session','exit_session','entry_notional','net_pnl','net_return']} for t in sorted(trades,key=lambda t:t['net_pnl'])[:3]])
    row.update(economic_metrics_valid=True,arithmetic_checks='passed',first_session=curve[0]['session'],last_session=curve[-1]['session'],sessions=len(curve),
               completed_trades=len(trades),gross_pnl=gross,net_pnl=net,fees=fees,
               gross_expectancy_usd=divide(gross,len(trades)),net_expectancy_usd=divide(net,len(trades)),
               gross_expectancy_trade_return=mean([(t['exit_notional']-t['entry_notional'])/t['entry_notional'] for t in trades]),
               net_expectancy_trade_return=mean([t['net_return'] for t in trades]),
               win_rate=divide(len(positive),len(trades)),average_win=mean(positive),average_loss=mean(negative),profit_factor=divide(sum(positive),-sum(negative)),
               mean_exposure_fraction=exposure,invested_session_fraction=metrics['invested_session_fraction'],turnover=turnover,annualized_turnover=metrics['annualized_turnover'],
               median_entry_notional=median([t['entry_notional'] for t in trades]),mean_entry_notional=mean([t['entry_notional'] for t in trades]),
               fees_per_trade=divide(fees,len(trades)),fees_fraction_of_initial_capital=fees/budget,fees_to_positive_gross_pnl=divide(fees,sum(max(0,t['exit_notional']-t['entry_notional']) for t in trades)),
               median_round_trip_fee_fraction_of_entry=median([(t['entry_fee']+t['exit_fee'])/t['entry_notional'] for t in trades]),
               price_under_5_trade_fraction=divide(sum(t['entry_notional']/t['quantity']<5 for t in trades),len(trades)),
               positive_and_drawdown_within_30_percent=net>0 and drawdown<=.3,
               period_consistency=period_metrics,profit_concentration=concentration)
    return row

def regime_readout(report, context):
    rows={r['session']:r for r in context['rows']}
    curve=report['equity_curve'];trades=report['trade_records']
    assert all(r['session'] in rows for r in curve)
    assert all(t['signal_session'] in rows for t in trades)
    output={}
    for state,label in context['state_labels'].items():
        state=int(state)
        marks=[r for r in curve if rows[r['session']]['state']==state]
        cohort=[t for t in trades if rows[t['signal_session']]['state']==state]
        output[label]=dict(observed_sessions=len(marks),
            mean_marked_exposure_fraction=mean([1-r['cash']/r['equity'] for r in marks]),
            signal_cohort_trades=len(cohort),signal_cohort_entry_notional=sum(t['entry_notional'] for t in cohort),
            signal_cohort_gross_pnl=sum(t['exit_notional']-t['entry_notional'] for t in cohort),
            signal_cohort_net_pnl=sum(t['net_pnl'] for t in cohort),
            signal_cohort_fees=sum(t['entry_fee']+t['exit_fee'] for t in cohort))
    assert sum(r['observed_sessions'] for r in output.values())==len(curve)
    assert sum(r['signal_cohort_trades'] for r in output.values())==len(trades)
    check(sum(r['signal_cohort_net_pnl'] for r in output.values()),sum(t['net_pnl'] for t in trades),'regime cohort net sum')
    return output


def main():
    status=read(BASE/'status.json');request=read(BASE/'request.json')
    if status.get('phase')!='complete':
        print(json.dumps(dict(status='awaiting_complete_study',worker_phase=status.get('phase'),no_results_written=True)))
        return
    summary=read(BASE/'summary.json');hashes=read(BASE/'result-hashes.json')
    assert summary['request']==request and len(summary['results'])==request['planned_accounts']==54
    context_path=BASE.parent/'strategy-timing20260928/regime-context.json'
    context=read(context_path) if context_path.exists() else None
    if context:
        assert context['signal_definition_sha256']==summary['definition_sha256']
    output=[]
    for policy in request['policies']:
        for hold in request['holding_sessions']:
            for profile in request['cost_profiles']:
                path=BASE/'accounts'/f'{policy}-{hold}-{profile}.json'
                raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==hashes[path.name]
                report=json.loads(raw)
                assert (report['policy'],report['horizon'],report['cost_profile'])==(policy,hold,profile)
                assert report['definition_sha256']==summary['definition_sha256']
                row=account_readout(report,request['capital_usd'])
                if context and row['economic_metrics_valid']:
                    row['observed_regime_context']=regime_readout(report,context)
                row['artifact']=str(path.relative_to(REPO));row['sha256']=hashes[path.name]
                reference=summary['references'][profile]
                row['spy_total_return']=reference.get('total_return')
                row['ending_equity_minus_spy']=row['ending_equity']-reference['ending_equity'] if row['economic_metrics_valid'] and reference.get('ending_equity') is not None else None
                output.append(row)
    by_id={(r['policy'],r['horizon'],r['cost_profile']):r for r in output}
    pairs=[]
    for new,control in CONTRASTS:
        for hold in request['holding_sessions']:
            for profile in request['cost_profiles']:
                a,b=by_id[new,hold,profile],by_id[control,hold,profile]
                paired=dict(policy=new,control=control,horizon=hold,cost_profile=profile,policy_status=a['status'],control_status=b['status'],valid_pair=a['economic_metrics_valid'] and b['economic_metrics_valid'])
                if paired['valid_pair']:
                    paired['deltas']={k:a[k]-b[k] if a[k] is not None and b[k] is not None else None for k in ['ending_equity','total_return','max_drawdown','gross_expectancy_usd','net_expectancy_usd','fees','mean_exposure_fraction','annualized_turnover','completed_trades']}
                    paired['deltas'].update(weekly_worst_return=a['period_consistency']['weekly']['worst_return']-b['period_consistency']['weekly']['worst_return'],
                                           monthly_profitable_fraction=a['period_consistency']['monthly']['profitable_fraction']-b['period_consistency']['monthly']['profitable_fraction'],
                                           yearly_profitable_count=a['period_consistency']['yearly']['profitable_count']-b['period_consistency']['yearly']['profitable_count'])
                    paired['new_policy_profitable']=a['net_pnl']>0
                    paired['both_policies_profitable']=a['net_pnl']>0 and b['net_pnl']>0
                pairs.append(paired)
    assert len(output)==54 and len(pairs)==36
    grouped=[]
    for new,control in CONTRASTS:
        matched=[p for p in pairs if p['policy']==new and p['control']==control]
        valid=[p for p in matched if p['valid_pair']]
        grouped.append(dict(policy=new,control=control,planned_pairs=6,valid_pairs=len(valid),
                            improved_ending_equity_pairs=sum(p['deltas']['ending_equity']>0 for p in valid),
                            lower_drawdown_pairs=sum(p['deltas']['max_drawdown']<0 for p in valid),
                            improved_net_expectancy_pairs=sum(p['deltas']['net_expectancy_usd'] is not None and p['deltas']['net_expectancy_usd']>0 for p in valid),
                            median_ending_equity_delta=median([p['deltas']['ending_equity'] for p in valid]),
                            median_exposure_delta=median([p['deltas']['mean_exposure_fraction'] for p in valid])))
    by_profile=[]
    for profile in request['cost_profiles']:
        for new,control in CONTRASTS:
            matched=[p for p in pairs if p['policy']==new and p['control']==control and p['cost_profile']==profile]
            valid=[p for p in matched if p['valid_pair']]
            by_profile.append(dict(policy=new,control=control,cost_profile=profile,planned_pairs=3,valid_pairs=len(valid),
                improved_ending_equity_pairs=sum(p['deltas']['ending_equity']>0 for p in valid),
                lower_drawdown_pairs=sum(p['deltas']['max_drawdown']<0 for p in valid),
                improved_net_expectancy_pairs=sum(p['deltas']['net_expectancy_usd'] is not None and p['deltas']['net_expectancy_usd']>0 for p in valid),
                ending_equity_deltas_by_hold={str(p['horizon']):p['deltas']['ending_equity'] for p in valid}))
    valid=[r for r in output if r['economic_metrics_valid']]
    cost_readout=[]
    for profile in request['cost_profiles']:
        accounts=[r for r in valid if r['cost_profile']==profile]
        cost_readout.append(dict(cost_profile=profile,complete_accounts=len(accounts),
            positive_gross_pnl_accounts=sum(r['gross_pnl']>0 for r in accounts),positive_net_pnl_accounts=sum(r['net_pnl']>0 for r in accounts),
            ending_equity_range=[min(r['ending_equity'] for r in accounts),max(r['ending_equity'] for r in accounts)],
            total_fee_range=[min(r['fees'] for r in accounts),max(r['fees'] for r in accounts)],
            mean_fee_per_trade_range=[min(r['fees_per_trade'] for r in accounts),max(r['fees_per_trade'] for r in accounts)]))
    failure_reasons=Counter()
    failed_symbols=Counter()
    for account in output:
        if not account['economic_metrics_valid']:
            for reason in account.get('missing') or [account.get('error') or account['status']]:
                failure_reasons[str(reason)]+=1
                if account.get('missing'):
                    failed_symbols[str(reason).split(':',1)[0]]+=1
    result=dict(experiment=request['experiment'],definition_sha256=summary['definition_sha256'],analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope=dict(planned_accounts=54,completed_accounts=len(valid),failed_or_incomplete_accounts=len(output)-len(valid),status_counts=dict(Counter(r['status'] for r in output)),
                           positive_accounts=sum(r['net_pnl']>0 for r in valid),zero_trade_accounts=sum(r['completed_trades']==0 for r in valid),positive_and_drawdown_within_30_percent=sum(r['positive_and_drawdown_within_30_percent'] for r in valid)),
                failure_groups=dict(reasons=failure_reasons.most_common(),symbols=failed_symbols.most_common()),accounts=output,paired_comparisons=pairs,contrast_summary=grouped,contrast_summary_by_profile=by_profile,cost_profile_readout=cost_readout,references=summary['references'],
                regime_context_source=dict(path=str(context_path.relative_to(REPO)),sha256=hashlib.sha256(context_path.read_bytes()).hexdigest(),cache_sha256=context['cache_sha256'],signal_definition_sha256=context['signal_definition_sha256']) if context else None,
                limitations=['All failed/incomplete accounts remain in the54-attempt denominator; partial-path economics are not presented as full-account results.',
                             'All dates were previously exposed; no untouched holdout, significance-adjusted winner or future profit claim.',
                             'Source-unit and action omissions, current-member survivorship and revised-vintage inputs remain unchanged.',
                             'Current tariffs are counterfactual and not all-in fees. Fixed fees affect accounting, not signal ranking.',
                             'Low drawdown with less exposure is not by itself greater predictive value. Positive net and30percent drawdown are necessary screens, not qualification.',
                             'Profit concentration is descriptive attribution, not an account rerun deleting best trades.',
                             'Regime exposure uses contemporaneous benchmark states; trade cohorts use signal-date states. Cohort PnL is descriptive attribution, not a separately tradable subaccount or an optimal selector.',
                             'Positive gross PnL is calculated on actual fee-affected positions; it is not a no-fee counterfactual account.',
                             'The thirty-percent owner loss preference is not enforced as an account stop in this research; catastrophic drawdowns are not viable deployment policies.'])
    (BASE/'economic-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    columns=['policy','horizon','cost_profile','status','error','economic_metrics_valid','ending_equity','total_return','max_drawdown','gross_pnl','net_pnl','fees','completed_trades','gross_expectancy_usd','net_expectancy_usd','gross_expectancy_trade_return','net_expectancy_trade_return','win_rate','profit_factor','mean_exposure_fraction','invested_session_fraction','annualized_turnover','median_entry_notional','fees_per_trade','median_round_trip_fee_fraction_of_entry','ending_equity_minus_spy','positive_and_drawdown_within_30_percent']
    with (BASE/'economic-results.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows({k:r.get(k) for k in columns} for r in output)
    lines=['# Strategy interaction economic results','',f"Completed {len(valid)} of 54 declared accounts; {len(output)-len(valid)} failed or incomplete. All results below use USD 2,000, every-session screening, next-close entries, and repeated 1/3/5-session holds from 2016-01-04 to 2026-09-18. These are exploratory current-member, revised-source simulations; no promotion or future-profit claim.",'',f"Positive accounts: {result['scope']['positive_accounts']} of 54. Positive accounts with modeled drawdown at most 30%: {result['scope']['positive_and_drawdown_within_30_percent']} of 54. These counts do not establish stability or source correctness.",'','## All policies and holding periods','','Each cell is net cumulative return / maximum drawdown. Failed paths remain labeled.','', '| Policy | Proportional 1 | Proportional 3 | Proportional 5 | Moomoo 1 | Moomoo 3 | Moomoo 5 |','|---|---:|---:|---:|---:|---:|---:|']
    for policy in request['policies']:
        cells=[]
        for profile in request['cost_profiles']:
            for hold in request['holding_sessions']:
                r=by_id[policy,hold,profile]
                cells.append(f"{r['total_return']:.1%} / {r['max_drawdown']:.1%}" if r['economic_metrics_valid'] else r['status'])
        lines.append('| '+policy+' | '+' | '.join(cells)+' |')
    lines+=['','## Predeclared paired contrasts','','The six primary contrasts each cover three holds and two fee profiles. The tables separate proportional strategy comparisons from the Moomoo minimum-fee depletion paths. Positive differences mean smaller losses here. Every detailed delta remains in the JSON.']
    for profile in request['cost_profiles']:
        lines+=['',f'### {profile}','','| New policy | Control | Better equity / 3 | Lower drawdown / 3 | Better net USD expectancy / 3 | Equity delta at 1 / 3 / 5 sessions, USD |','|---|---|---:|---:|---:|---:|']
        for g in by_profile:
            if g['cost_profile']!=profile:continue
            delta=' / '.join(f"{g['ending_equity_deltas_by_hold'][str(h)]:+.2f}" for h in request['holding_sessions']) if g['valid_pairs']==3 else 'incomplete; see JSON'
            lines.append(f"| {g['policy']} | {g['control']} | {g['improved_ending_equity_pairs']} | {g['lower_drawdown_pairs']} | {g['improved_net_expectancy_pairs']} | {delta} |")
    if failure_reasons:
        lines+=['','## Retained failures','','Full-account economic metrics are withheld for these paths; none enters positive-account or successful-pair counts. Common recorded constraints:','']
        lines += [f'- {reason}: {count} accounts' for reason,count in failure_reasons.most_common()]
    lines+=['','## Reading the evidence','','Gross and net expectancy, annual turnover, fee burden, all yearly/weekly/monthly returns, largest positive/negative contributors, and every failed path are retained in `economic-results.json`. The CSV contains one row for each of 54 accounts. No thresholds or running signals were adjusted from these results.','', 'Arithmetic checks independently verified complete flat accounts against initial capital plus net trade P&L, gross minus fees, daily compounding, period returns, drawdown, exposure and turnover. These checks do not resolve missing corporate actions, security mappings or executable price quality.','', 'The same-window SPY reference has substantially different exposure and holding duration; its return is a reference, not proof of equal-risk outperformance. First and last yearly/weekly/monthly periods may be partial.','', 'Evidence: `.qualification/strategy-interactions20260928/economic-results.json`, `economic-results.csv`, all 54 account JSONs and the frozen request/formula documentation. This draft records the complete comparison before selecting any follow-up experiment.','']
    (REPO/'docs/strategy-interaction-results.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(scope=result['scope'],contrasts=grouped)),flush=True)

if __name__=='__main__':main()

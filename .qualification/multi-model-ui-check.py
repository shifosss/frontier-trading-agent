import copy
import itertools
import json
from pathlib import Path

ns={}
exec(Path('.qualification/short-hold-ui-check.py').read_text('utf-8').split('\nreport =')[0],ns)
RUN=ns['RUN']
BASE_MODELS=['ridge','extra_trees','hist_gradient_boosting','multi_head_mlp']
LEARNED=BASE_MODELS+['equal_ensemble','calibrated_ensemble','diversified_ensemble']
RULES=['momentum','trend_pullback','mean_reversion','breakout','momentum_12_1']
MODELS=LEARNED+RULES+[name+'_market_trend' for name in RULES]+['relative_reversal_2','relative_reversal_5','relative_volume_continuation_5']
BUDGETS=[2000,10000]
COSTS=[20,40,100]


def fixture():
    source=ns['short_fixture']()
    result={**source,'study_mode':'multi_model','portfolios':[],'benchmarks':[],'walk_forward':[], 'model_diagnostics':[], 'latest_candidates':[]}
    result['methodology']={**source['methodology'],'version':'multi-model-browser-fixture','budgets':BUDGETS,'cost_bps':COSTS,'attempts':[{'strategy':model,'horizon':hold} for model,hold in itertools.product(MODELS,[1,3,5])]}
    for currency,budget,cost in itertools.product(['USD','CAD'],BUDGETS,COSTS):
        common=copy.deepcopy(next(r for r in source['walk_forward'] if (r['currency'],r['budget'],r['cost_bps'])==(currency,budget,cost)))
        common.pop('benchmark')
        common.pop('folds')
        for strategy,horizon in itertools.product(MODELS,[1,3,5]):
            row={**copy.deepcopy(common),'strategy':strategy,'horizon':horizon}
            if currency=='CAD' and strategy=='relative_reversal_5' and horizon==5:
                row.update(status='incomplete',missing=['WJX.TO:2005-06-15:mark'])
            if strategy=='hist_gradient_boosting' and horizon==1:
                row.update(total_return=0,annualized_return=0,maximum_drawdown=0,final_equity=budget)
                row['trade_metrics'].update(completed_trades=0,net_expectancy_native=None,net_expectancy_return=None,win_rate=None,annualized_turnover=0,mean_exposure_fraction=0,mean_holding_sessions=None,mean_holding_calendar_days=None,trades_per_week=0)
                for period in row['period_metrics'].values():
                    period.update(profitable_fraction=0,mean_return=0,median_return=0,worst_return=0)
            result['portfolios'].append(row)
        result['benchmarks'].extend(copy.deepcopy([r for r in source['benchmarks'] if (r['currency'],r['budget'],r['cost_bps'])==(currency,budget,cost)]))
    for currency in ['USD','CAD']:
        for year in [2024,2025]:
            result['model_diagnostics'].append({
                'currency':currency,'training_start':str(year-3)+'-01-03','training_end':str(year-2)+'-12-30',
                'calibration_start':str(year-1)+'-01-03','calibration_end':str(year-1)+'-12-30',
                'test_start':str(year)+'-01-03','test_end':str(year)+'-12-30',
                'fit_rows':123456,'calibration_rows':65432,'prediction_rows':22222,'excluded_label_rows':111,
                'calibration':{'baseline_mse':[.000004]*6,'model_mse':{'ridge':[.000003]*6,'extra_trees':[.000002]*6,'hist_gradient_boosting':[.000001]*6,'multi_head_mlp':[.000005]*6},'horizons':{
                    '1':{'weights':{'ridge':.2,'extra_trees':.3,'hist_gradient_boosting':.5,'multi_head_mlp':0},'equal_weight_fallback':False},
                    '3':{'weights':{'ridge':.25,'extra_trees':.25,'hist_gradient_boosting':.25,'multi_head_mlp':.25},'equal_weight_fallback':True},
                }},'warnings':['Synthetic calibration warning',{'model':'multi_head_mlp','category':'ConvergenceWarning','message':'Synthetic structured model warning'}]})
        for strategy,horizon in itertools.product(LEARNED[:-1],[1,3,5]):
            result['latest_candidates'].append({'currency':currency,'strategy':strategy,'horizon':horizon,'symbol':'TEST' if currency=='USD' else 'TEST.TO','session':'2026-09-18','rank':1,'price':12.34,'predicted_return':.008,'predicted_downside':.002,'score_40bps':.003})
    return result


result=fixture()
report={'kind':'synthetic multi-model UI integration fixture','widths':[],'states':[]}
with ns['namespace']['sync_playwright']() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    for width in [1440,768,390,320]:
        starts=[]
        page,panel,errors=ns['fresh_page'](browser,width,{'status':'completed','latest':{'run_id':RUN}},{RUN:result},starts)
        panel.get_by_role('heading',name='Rolling model study results',exact=True).wait_for()
        assert panel.get_by_label('Study to run').input_value()=='multi_model'
        assert panel.get_by_role('button',name='Run model study',exact=True).is_enabled()
        assert panel.get_by_role('heading',name='Training-only selection, tested on the following year',exact=True).count()==0
        assert panel.get_by_role('heading',name='All fixed strategies and benchmarks',exact=True).count()==0
        assert panel.get_by_label('Historical starting cash').locator('option').all_text_contents()==['2,000','10,000']
        checks=[]
        for currency,budget,cost in itertools.product(['USD','CAD'],BUDGETS,COSTS):
            panel.get_by_label('Historical currency').select_option(currency)
            panel.get_by_label('Historical starting cash').select_option(str(budget))
            panel.get_by_label('Historical round-trip cost').select_option(str(cost))
            selector=panel.get_by_label('Model or comparison portfolio')
            assert selector.locator('option').count()==len(MODELS)*3
            selector.select_option('calibrated_ensemble:3')
            assert panel.get_by_role('region',name='Short-hold trading statistics').count()==1
            assert panel.get_by_text('Same-period benchmark return:',exact=False).count()==1
            assert panel.locator('.chart-legend').get_by_text('calibrated ensemble',exact=True).count()==1
            table=panel.locator('table').last
            assert table.locator('tbody tr').count()==len(MODELS)*3+2
            calibrated=next(r for r in result['portfolios'] if (r['currency'],r['budget'],r['cost_bps'],r['strategy'],r['horizon'])==(currency,budget,cost,'calibrated_ensemble',3))
            summary=panel.locator('p').filter(has=page.locator('strong')).inner_text()
            assert ns['namespace']['rate'](calibrated['total_return']) in summary
            checks.append({'currency':currency,'budget':budget,'cost':cost,'selected_model':'calibrated_ensemble:3'})
        selector.select_option('hist_gradient_boosting:1')
        stats=panel.get_by_role('region',name='Short-hold trading statistics').inner_text()
        assert 'Completed round trips\n0\n0.00 per 5 sessions' in stats,stats
        assert 'Unavailable sessions' in stats and 'Unavailable calendar days' in stats,stats
        assert '0.00%' in stats and 'NaN' not in stats and 'Infinity' not in stats,stats
        assert panel.get_by_role('note').count()==0
        selector.select_option('calibrated_ensemble:3')
        diagnostics=panel.locator('details').filter(has=page.locator('summary',has_text='Model refits and calibration'))
        diagnostics.locator('summary').click()
        assert diagnostics.locator('table tbody tr').count()==2
        diag_text=diagnostics.inner_text()
        for text in ['123,456','65,432','22,222','111','ridge 20.00%','extra trees 30.00%','hist gradient boosting 50.00%','hist gradient boosting 25.00%','equal-weight fallback','0.00000400','0.00000300','Synthetic calibration warning','multi head mlp (ConvergenceWarning): Synthetic structured model warning']:
            assert text in diag_text,(text,diag_text)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        diagnostics.locator('summary').click()
        forecasts=panel.locator('details').filter(has=page.locator('summary',has_text='Latest research forecasts'))
        forecasts.locator('summary').click()
        assert 'not current quotes or qualified buy recommendations' in forecasts.inner_text()
        assert '40-bps scenario regardless of the cost filter' in forecasts.inner_text()
        cells=forecasts.locator('table tbody tr').first.locator('td').all_text_contents()
        assert cells==['1','TEST.TO','2026-09-18','12.34','0.80%','0.20%','0.30%'],cells
        forecasts.locator('summary').click()
        panel.get_by_label('Model or comparison portfolio').select_option('relative_reversal_5:5')
        assert panel.get_by_role('note').count()==1
        assert panel.get_by_text('Same-period benchmark return:',exact=False).count()==0
        assert panel.get_by_role('region',name='Short-hold trading statistics').count()==0
        assert 'WJX.TO · 2005-06-15 · mark' in panel.get_by_role('note').inner_text()
        panel.get_by_role('heading',name='Historical strategy development',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=f'.qualification/historical-ui/multi-model-{width}.png')
        assert not errors and not starts,(errors,starts)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        report['widths'].append({'width':width,'filter_checks':checks,'diagnostics_verified':True,'roster_families':len(MODELS),'zero_trade_verified':True,'incomplete_verified':True,'forecast_verified':True,'page_errors':errors})
        page.close()
    baseline=ns['namespace']['fixture']()
    starts=[]
    status={'status':'completed','latest':{'run_id':RUN}}
    page,panel,errors=ns['fresh_page'](browser,390,status,{RUN:baseline},starts)
    panel.get_by_role('heading',name='Baseline historical results',exact=True).wait_for()
    panel.get_by_role('button',name='Run model study',exact=True).click()
    panel.get_by_text('A new study is running.',exact=False).wait_for()
    assert starts==[{'study_mode':'multi_model','source_run_id':RUN}],starts
    assert panel.get_by_role('heading',name='Baseline historical results',exact=True).count()==1
    assert not errors
    report['states'].append('default model-mode request reuses prior capture and retains prior published baseline')
    page.close()
    status={'status':'running','study_mode':'multi_model','phase':'evaluation','stage':'ensemble_fit','currency':'USD','fold':4,'total_folds':23,'test_start':'2007-10-19','latest':{'run_id':RUN},'budget':10000}
    page,panel,errors=ns['fresh_page'](browser,320,status,{RUN:baseline},[])
    panel.get_by_text('Running rolling model forecasts with separate fitting, calibration and test windows.',exact=True).wait_for()
    progress=panel.get_by_role('status').inner_text()
    assert 'fold 4 / 23' in progress and 'test window starting 2007-10-19' in progress
    assert 'starting cash' not in progress
    assert not errors
    report['states'].append('actual mode/fitting fold progress shown without stale budget')
    browser.close()
Path('.qualification/historical-ui/multi-model-mock-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'filters':sum(len(row['filter_checks']) for row in report['widths']),'states':report['states'],'report':'.qualification/historical-ui/multi-model-mock-report.json'}))

import itertools
import json
import urllib.request
from pathlib import Path

ns = {}
exec(Path('.qualification/historical-ui-mock-check.py').read_text('utf-8').split('\nreport =')[0], ns)
BASE=ns['BASE']
ROOT=Path('.qualification/historical-ui')

def read(path):
    with urllib.request.urlopen(BASE + path) as response:
        return json.load(response)

def amount(value, decimals=2):
    return 'Unavailable' if value is None else f'{value:,.{decimals}f}'

def financial(row, key):
    return row.get(key) if row['status']=='complete' else None

status=read('/api/historical-lab/status')
if status['status'] != 'completed':
    raise SystemExit('Await completed study: ' + status['status'])
run_id=status['latest']['run_id']
result=read('/api/historical-lab/runs/' + run_id)
assert result['methodology']['version']=='daily-short-hold-v1'
(ROOT / 'short-hold-actual-api-result.json').write_text(json.dumps(result),encoding='utf-8')
report={'kind':'actual completed daily short-hold study','run_id':run_id,'capture':{k:v for k,v in result['capture'].items() if k not in {'failed','insufficient_symbols'}},'widths':[]}
with ns['sync_playwright']() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    for width in [1440,768,390,320]:
        page,errors,mutations=ns['open_page'](browser,width)
        panel=page.locator('.historical-research')
        panel.get_by_role('heading',name='Daily short-hold results',exact=True).wait_for()
        assert panel.get_by_role('button',name='Run short-hold study',exact=True).is_enabled()
        assert panel.get_by_role('link',name='Download historical evidence').get_attribute('href')=='/api/historical-lab/runs/'+run_id+'/download'
        checks=[]
        for currency,budget,cost in itertools.product(['USD','CAD'],ns['BUDGETS'],ns['COSTS']):
            panel.get_by_label('Historical currency').select_option(currency)
            panel.get_by_label('Historical starting cash').select_option(str(budget))
            panel.get_by_label('Historical round-trip cost').select_option(str(cost))
            matches=lambda row: row['currency']==currency and row['budget']==budget and row['cost_bps']==cost
            expected=[row for row in result['portfolios'] if matches(row)]+[row for row in result['benchmarks'] if matches(row)]
            fixed=panel.locator('table').last.locator('tbody tr')
            assert fixed.count()==len(expected)
            for index,row in enumerate(expected):
                cells=fixed.nth(index).locator('td').all_text_contents()
                assert cells[2]==row['status'].replace('_',' ')
                assert cells[3:6]==[ns['rate'](financial(row,key)) for key in ['total_return','max_drawdown','cagr']],cells
                metrics=row.get('trade_metrics') or {}
                assert cells[6]==amount(metrics.get('completed_trades',row['trades']),0),cells
                assert cells[7]==amount(row['fees']),cells
                available=lambda key: metrics.get(key) if row['status']=='complete' else None
                turnover=available('annualized_turnover')
                assert cells[8:]==[amount(available('mean_holding_sessions')),amount(available('net_expectancy_native')),ns['rate'](available('win_rate')),amount(turnover)+'×' if turnover is not None else 'Unavailable'],cells
            walk=next(row for row in result['walk_forward'] if matches(row))
            summary=panel.locator('p').filter(has=page.locator('strong')).inner_text()
            for key,label in [('total_return','total return'),('max_drawdown','maximum drawdown'),('cagr','annualized return')]:
                assert label+' '+ns['rate'](financial(walk,key)) in summary,summary
            metrics=walk.get('trade_metrics')
            statistics=panel.get_by_role('region',name='Short-hold trading statistics')
            if walk['status']=='complete' and metrics:
                assert statistics.count()==1
                values=statistics.locator('dl dd').all_text_contents()
                expected_values=[amount(metrics['completed_trades'],0),amount(metrics['mean_holding_sessions'])+' sessions',currency+' '+amount(metrics['net_expectancy_native']),ns['rate'](metrics['win_rate']),amount(metrics['annualized_turnover'])+'×',ns['rate'](metrics['mean_exposure_fraction'])]
                assert values==expected_values,(values,expected_values)
                assert amount(metrics['mean_holding_calendar_days'])+' calendar days' in statistics.inner_text()
                assert amount(metrics['trades_per_week'])+' per 5 sessions' in statistics.inner_text()
                period_rows=statistics.locator('table tbody tr')
                periods=walk.get('period_metrics',{})
                expected_periods=[(name,periods[name]) for name in ['weekly','monthly'] if name in periods]
                assert period_rows.count()==len(expected_periods)
                for index,(name,values) in enumerate(expected_periods):
                    assert period_rows.nth(index).locator('td').all_text_contents()==[name,amount(values['count'],0),ns['rate'](values['profitable_fraction']),ns['rate'](values['mean_return']),ns['rate'](values['median_return']),ns['rate'](values['worst_return'])]
            else:
                assert statistics.count()==0
                for missing in walk.get('missing',[]):
                    assert missing.replace(':',' · ') in panel.get_by_role('note').inner_text()
            benchmark=walk.get('benchmark',{})
            comparable=walk['status']=='complete' and benchmark.get('status')=='complete' and walk['first_session']==benchmark.get('first_session') and walk['last_session']==benchmark.get('last_session')
            comparison=panel.get_by_text('Same-period benchmark return:',exact=False)
            legend=panel.locator('.chart-legend').get_by_text('Buy and hold benchmark',exact=True)
            assert comparison.count()==int(comparable) and legend.count()==int(comparable)
            if comparable:
                assert ns['rate'](benchmark['total_return']) in comparison.inner_text()
            folds=panel.locator('table').filter(has=page.get_by_role('columnheader',name='Training interval',exact=True)).locator('tbody tr')
            assert folds.count()==len(walk.get('folds',[]))
            for index,fold in enumerate(walk.get('folds',[])):
                cells=folds.nth(index).locator('td').all_text_contents()
                assert cells[2]==fold['selected_strategy'].replace('_',' ')
                assert cells[3]==('Cash' if fold['selected_strategy']=='cash' else str(fold['selected_horizon'])+' sessions')
                assert cells[4]==ns['rate'](fold['test_return'])
            assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
            checks.append({'currency':currency,'budget':budget,'cost_bps':cost,'fixed_rows':len(expected),'walk_status':walk['status'],'metrics_match':True,'benchmark_comparable':comparable})
        panel.get_by_role('heading',name='Historical strategy development',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(ROOT / f'short-hold-actual-completed-{width}.png'))
        assert not errors and not mutations,(errors,mutations)
        report['widths'].append({'width':width,'filter_checks':checks,'page_errors':errors,'mutations':mutations,'overflow':False})
        print(json.dumps({'width':width,'verified_filters':len(checks)}),flush=True)
        page.close()
    browser.close()
request=urllib.request.Request(BASE+'/api/historical-lab/runs/'+run_id+'/download',headers={'Range':'bytes=0-0'})
with urllib.request.urlopen(request) as response:
    assert response.status in [200,206]
    assert response.read(1)==b'{'
    assert run_id in response.headers.get('Content-Disposition','')
    report['download']={'status':response.status,'content_disposition':response.headers.get('Content-Disposition'),'read_bytes':1}
(ROOT / 'short-hold-actual-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'run_id':run_id,'filter_checks':sum(len(row['filter_checks']) for row in report['widths']),'report':str(ROOT / 'short-hold-actual-report.json')}))

import itertools
import json
import urllib.request
from pathlib import Path

ns={}
exec(Path('.qualification/historical-ui-mock-check.py').read_text('utf-8').split('\nreport =')[0],ns)
BASE=ns['BASE']
OUT=Path('.qualification/historical-ui')
RUN='814780d48b4141b9a82a3fb917d1b85a'

def read(path):
    with urllib.request.urlopen(BASE+path) as response:
        return json.load(response)

def amount(value,decimals=2):
    return 'Unavailable' if value is None else f'{value:,.{decimals}f}'

def financial(row,key):
    return row.get(key) if row['status']=='complete' else None

def inspect_selected(page,panel,row,benchmark):
    selector=panel.get_by_label('Model or comparison portfolio')
    selector.select_option(row['strategy']+':'+str(row['horizon']))
    summary=panel.locator('p').filter(has=page.locator('strong')).inner_text()
    for key,label in [('total_return','total return'),('max_drawdown','maximum drawdown'),('cagr','annualized return')]:
        assert label+' '+ns['rate'](financial(row,key)) in summary,summary
    statistics=panel.get_by_role('region',name='Short-hold trading statistics')
    comparable=row['status']=='complete' and benchmark['status']=='complete' and all(row[k]==benchmark[k] for k in ('first_session','last_session'))
    comparison=panel.get_by_text('Same-period benchmark return:',exact=False)
    assert comparison.count()==int(comparable)
    if comparable:
        assert ns['rate'](benchmark['total_return']) in comparison.inner_text()
    if row['status']=='complete':
        assert statistics.count()==1 and panel.get_by_role('note').count()==0
        m=row['trade_metrics']
        expected=[amount(m['completed_trades'],0),amount(m['mean_holding_sessions'])+' sessions',row['currency']+' '+amount(m['net_expectancy_native']),ns['rate'](m['win_rate']),amount(m['annualized_turnover'])+'×',ns['rate'](m['mean_exposure_fraction'])]
        assert statistics.locator('dl dd').all_text_contents()==expected
        for period in ['weekly','monthly']:
            v=row['period_metrics'][period]
            cells=statistics.locator('table tbody tr').filter(has=page.get_by_role('cell',name=period,exact=True)).locator('td').all_text_contents()
            assert cells==[period,amount(v['count'],0),ns['rate'](v['profitable_fraction']),ns['rate'](v['mean_return']),ns['rate'](v['median_return']),ns['rate'](v['worst_return'])]
    else:
        assert statistics.count()==0
        for missing in row.get('missing',[]):
            assert missing.replace(':',' · ') in panel.get_by_role('note').inner_text()
    return comparable

status=read('/api/historical-lab/status')
assert status['status']=='completed' and status['latest']['run_id']==RUN
result=read('/api/historical-lab/runs/'+RUN)
assert result['study_mode']=='multi_model' and result['methodology']['version']=='daily-multi-model-v1'
assert len(result['portfolios'])==720
report={'kind':'actual completed multi-model UI checks','run_id':RUN,'widths':[]}
with ns['sync_playwright']() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    for width in [1440,768,390,320]:
        page,errors,mutations=ns['open_page'](browser,width)
        panel=page.locator('.historical-research')
        panel.get_by_role('heading',name='Rolling model study results',exact=True).wait_for()
        assert panel.get_by_role('button',name='Run model study',exact=True).is_enabled()
        assert panel.get_by_text('A new study is running.',exact=False).count()==0
        assert panel.get_by_role('link',name='Download historical evidence').get_attribute('href')=='/api/historical-lab/runs/'+RUN+'/download'
        checks=[]
        for currency,budget,cost in itertools.product(['USD','CAD'],[2000,10000],[20,40,100]):
            panel.get_by_label('Historical currency').select_option(currency)
            panel.get_by_label('Historical starting cash').select_option(str(budget))
            panel.get_by_label('Historical round-trip cost').select_option(str(cost))
            matches=lambda row:(row['currency'],row['budget'],row['cost_bps'])==(currency,budget,cost)
            portfolios=[r for r in result['portfolios'] if matches(r)]
            benchmarks=[r for r in result['benchmarks'] if matches(r)]
            expected=portfolios+benchmarks
            assert panel.get_by_label('Model or comparison portfolio').locator('option').count()==60
            actual=panel.locator('table').last.locator('tbody tr').evaluate_all('(rows)=>rows.map(r=>[...r.querySelectorAll("td")].map(c=>c.textContent))')
            assert len(actual)==62
            for row,cells in zip(expected,actual):
                assert cells[2]==row['status']
                assert cells[3:6]==[ns['rate'](financial(row,key)) for key in ['total_return','max_drawdown','cagr']],(row['currency'],row.get('strategy',row.get('symbol')),cells)
                m=row.get('trade_metrics') or {}
                assert cells[6]==amount(m.get('completed_trades',row['trades']),0)
                assert cells[7]==amount(row['fees'])
                available=lambda key:m.get(key) if row['status']=='complete' else None
                turnover=available('annualized_turnover')
                assert cells[8:]==[amount(available('mean_holding_sessions')),amount(available('net_expectancy_native')),ns['rate'](available('win_rate')),amount(turnover)+'×' if turnover is not None else 'Unavailable']
            selected=next(r for r in portfolios if r['strategy']=='hist_gradient_boosting' and r['horizon']==5)
            benchmark=next(r for r in benchmarks if r['symbol']!='CASH')
            comparable=inspect_selected(page,panel,selected,benchmark)
            failed=next((r for r in portfolios if r['status']!='complete'),None)
            if failed:
                inspect_selected(page,panel,failed,benchmark)
                inspect_selected(page,panel,selected,benchmark)
            assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
            checks.append({'currency':currency,'budget':budget,'cost_bps':cost,'account_table_rows_verified':len(portfolios),'benchmark_rows_verified':len(benchmarks),'selected_metrics_verified':True,'incomplete_detail_verified':failed is not None,'benchmark_comparison':comparable})
        diagnostics=panel.locator('details').filter(has=page.locator('summary',has_text='Model refits and calibration'))
        diagnostics.locator('summary').click()
        assert diagnostics.locator('table tbody tr').count()==23
        text=diagnostics.inner_text()
        for model in ['ridge','extra trees','hist gradient boosting','multi head mlp']:
            assert model in text
        assert 'equal-weight fallback' in text and 'ConvergenceWarning' in text and '[object Object]' not in text
        assert 'Maximum iterations (60)' in text
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        diagnostics.locator('summary').click()
        forecasts=panel.locator('details').filter(has=page.locator('summary',has_text='Latest research forecasts'))
        forecasts.locator('summary').click()
        expected=[r for r in result['latest_candidates'] if r['currency']=='CAD' and r['strategy']=='hist_gradient_boosting' and r['horizon']==5]
        actual=forecasts.locator('table tbody tr').evaluate_all('(rows)=>rows.map(r=>[...r.querySelectorAll("td")].map(c=>c.textContent))')
        assert len(actual)==len(expected)==10
        for row,cells in zip(expected,actual):
            assert cells==[amount(row['rank'],0),row['symbol'],row['session'],amount(row['price']),ns['rate'](row['predicted_return']),ns['rate'](row['predicted_downside']),ns['rate'](row['score_40bps'])]
        assert 'not current quotes or qualified buy recommendations' in forecasts.inner_text()
        forecasts.locator('summary').click()
        panel.get_by_role('heading',name='Historical strategy development',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT/f'multi-model-actual-completed-{width}.png'))
        assert not errors and not mutations,(errors,mutations)
        report['widths'].append({'width':width,'filter_checks':checks,'diagnostics_windows':23,'forecasts_verified':10,'page_errors':errors,'mutations':mutations,'overflow':False})
        print(json.dumps({'width':width,'verified_filter_contexts':len(checks),'portfolio_rows_verified':sum(c['account_table_rows_verified'] for c in checks)}),flush=True)
        page.close()
    browser.close()
request=urllib.request.Request(BASE+'/api/historical-lab/runs/'+RUN+'/download',headers={'Range':'bytes=0-0'})
with urllib.request.urlopen(request) as response:
    assert response.status==206
    assert response.read(1)==b'{'
    assert RUN in response.headers.get('Content-Disposition','')
    report['download']={'status':response.status,'content_range':response.headers.get('Content-Range'),'content_disposition':response.headers.get('Content-Disposition'),'read_bytes':1}
(OUT/'multi-model-actual-completed-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'report':str(OUT/'multi-model-actual-completed-report.json'),'filter_contexts':sum(len(w['filter_checks']) for w in report['widths']),'download':report['download']}))

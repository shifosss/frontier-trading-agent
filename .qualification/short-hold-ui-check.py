import copy
import itertools
import json
from pathlib import Path

namespace = {}
exec(Path('.qualification/historical-ui-mock-check.py').read_text('utf-8').split('\nreport =')[0], namespace)
BASE, RUN = namespace['BASE'], namespace['RUN']
ROOT = Path('.qualification/historical-ui')
NEW_RUN = 'e' * 32


def short_fixture():
    result = namespace['fixture']()
    result['study_mode'] = 'short_horizon'
    result['methodology'].update(version='daily-short-hold-v1', horizons=[1, 3, 5], screening_frequency='every_completed_session', execution='next_session_close')
    for collection in ['portfolios', 'walk_forward']:
        for row in result[collection]:
            row['horizon'] = {5: 1, 10: 3, 20: 5}[row.get('horizon', 5)]
            row['trade_metrics'] = {
                'completed_trades': row['budget'] // 10,
                'net_expectancy_native': -0.17,
                'net_expectancy_return': -0.004,
                'win_rate': 0.41,
                'annualized_turnover': 43.15,
                'mean_exposure_fraction': 0.135,
                'mean_holding_sessions': 2.74,
                'mean_holding_calendar_days': 3.91,
                'trades_per_week': 3.12,
            }
            row['period_metrics'] = {
                'weekly': {'count': 99, 'profitable_fraction': 0.34, 'mean_return': -0.002, 'median_return': 0, 'worst_return': -0.071},
                'monthly': {'count': 23, 'profitable_fraction': 0.43, 'mean_return': -0.004, 'median_return': -0.001, 'worst_return': -0.14},
            }
    return result


def fresh_page(browser, width, status, reports, starts):
    page = browser.new_page(viewport={'width': width, 'height': 1000})
    errors = []
    page.on('pageerror', lambda value: errors.append(str(value)))
    def route_handler(route):
        suffix = route.request.url.rsplit('/', 1)[-1]
        if suffix == 'status':
            route.fulfill(json=status)
        elif suffix == 'start':
            starts.append(route.request.post_data_json)
            status.update(status='running', phase='short_horizon', message='Synthetic in-progress fixture')
            route.fulfill(json=status)
        elif suffix in reports:
            route.fulfill(json=reports[suffix])
        else:
            route.abort()
    page.route('**/api/historical-lab/**', route_handler)
    page.goto(BASE, wait_until='networkidle')
    page.get_by_role('button', name='Strategy lab', exact=True).click()
    panel = page.locator('.historical-research')
    panel.wait_for()
    return page, panel, errors


report = {'kind': 'synthetic short-hold UI contract tests', 'widths': [], 'states': []}
with namespace['sync_playwright']() as playwright:
    browser = playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    result = short_fixture()
    for width in [1440, 768, 390, 320]:
        starts = []
        status = {'status': 'completed', 'latest': {'run_id': RUN}}
        page, panel, errors = fresh_page(browser, width, status, {RUN: result}, starts)
        panel.get_by_role('heading', name='Daily short-hold results', exact=True).wait_for()
        checks = []
        for currency, budget, cost in itertools.product(['USD', 'CAD'], namespace['BUDGETS'], namespace['COSTS']):
            panel.get_by_label('Historical currency').select_option(currency)
            panel.get_by_label('Historical starting cash').select_option(str(budget))
            panel.get_by_label('Historical round-trip cost').select_option(str(cost))
            statistics = panel.get_by_role('region', name='Short-hold trading statistics')
            text = statistics.inner_text()
            for expected in [f'{budget // 10:,}', '2.74 sessions', '3.91 calendar days', currency + ' -0.17', '-0.40%', '41.00%', '43.15×', '13.50%', '34.00%', '-7.10%', '43.00%', '-14.00%']:
                assert expected in text, (width, currency, budget, cost, expected, text)
            assert 'first and last partial calendar periods' in text
            fixed = panel.locator('table').last.locator('tbody tr')
            assert fixed.count() == 32
            cells = fixed.first.locator('td').all_text_contents()
            assert cells[1] == '1 sessions'
            assert cells[6] == f'{budget // 10:,}'
            assert cells[8:] == ['2.74', '-0.17', '41.00%', '43.15×'], cells
            assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
            checks.append({'currency': currency, 'budget': budget, 'cost': cost})
        panel.screenshot(path=str(ROOT / f'short-hold-complete-{width}.png'))
        assert not errors and not starts, (errors, starts)
        report['widths'].append({'width': width, 'filter_checks': checks, 'page_errors': errors, 'overflow': False})
        page.close()

    incomplete = copy.deepcopy(result)
    for collection in ['portfolios', 'walk_forward']:
        for row in incomplete[collection]:
            row.update(status='incomplete', missing=['CRON.TO:2018-05-24:mark'])
            # Deliberately retain stale finite financial metrics to verify UI masks incomplete results.
    page, panel, errors = fresh_page(browser, 390, {'status': 'completed', 'latest': {'run_id': RUN}}, {RUN: incomplete}, [])
    panel.get_by_text('50 completed round trips before this test stopped.', exact=False).wait_for()
    assert panel.get_by_role('region', name='Short-hold trading statistics').count() == 0
    assert panel.get_by_text('Same-period benchmark return:', exact=False).count() == 0
    assert panel.get_by_text('CRON.TO · 2018-05-24 · mark', exact=True).count() == 1
    cells = panel.locator('table').last.locator('tbody tr').first.locator('td').all_text_contents()
    assert cells[3:6] == ['Unavailable'] * 3 and cells[8:] == ['Unavailable'] * 4, cells
    assert not errors
    panel.screenshot(path=str(ROOT / 'short-hold-incomplete-390.png'))
    report['states'].append('incomplete financial metrics and benchmark suppressed; actual count retained')
    page.close()

    baseline = namespace['fixture']()
    starts = []
    status = {'status': 'completed', 'latest': {'run_id': RUN}}
    newer = {**result, 'run_id': NEW_RUN}
    page, panel, errors = fresh_page(browser, 390, status, {RUN: baseline, NEW_RUN: newer}, starts)
    panel.get_by_role('heading', name='Baseline historical results', exact=True).wait_for()
    assert panel.get_by_label('Study to run').input_value() == 'short_horizon'
    assert panel.get_by_label('Reuse the saved histories from the result below').is_checked()
    panel.get_by_role('button', name='Run short-hold study', exact=True).click()
    panel.get_by_text('A new study is running.', exact=False).wait_for()
    assert starts == [{'study_mode': 'short_horizon', 'source_run_id': RUN}], starts
    assert panel.get_by_role('heading', name='Baseline historical results', exact=True).count() == 1
    assert panel.get_by_role('button', name='Historical study running', exact=True).is_disabled()
    status.update(status='completed', latest={'run_id': NEW_RUN})
    panel.get_by_role('button', name='Refresh historical status', exact=True).click()
    panel.get_by_role('heading', name='Daily short-hold results', exact=True).wait_for()
    assert panel.get_by_role('heading', name='Baseline historical results', exact=True).count() == 0
    assert NEW_RUN in panel.get_by_role('link', name='Download historical evidence').get_attribute('href')
    panel.get_by_label('Study to run').select_option('legacy')
    panel.get_by_label('Reuse the saved histories from the result below').uncheck()
    panel.get_by_role('button', name='Run baseline study', exact=True).click()
    panel.get_by_role('button', name='Historical study running', exact=True).wait_for()
    assert starts[-1] == {'study_mode': 'legacy'}, starts
    assert not errors
    report['states'].append('short-hold request, explicit capture reuse, retained old result, publication swap, legacy fresh-capture request')
    page.close()

    starts = []
    page, panel, errors = fresh_page(browser, 320, {'status': 'idle'}, {}, starts)
    panel.get_by_role('button', name='Run short-hold study', exact=True).click()
    panel.get_by_role('button', name='Historical study running', exact=True).wait_for()
    assert starts == [{'study_mode': 'short_horizon'}]
    assert not errors
    report['states'].append('first-run default short-hold request without nonexistent source')
    browser.close()
(ROOT / 'short-hold-mock-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'filter_combinations': sum(len(row['filter_checks']) for row in report['widths']), 'states': report['states'], 'report': str(ROOT / 'short-hold-mock-report.json')}))

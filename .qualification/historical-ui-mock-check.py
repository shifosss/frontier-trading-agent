import copy
import itertools
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path('.qualification/historical-ui')
ROOT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8765'
RUN = 'f' * 32
BUDGETS = [500, 2000, 10000, 100000]
COSTS = [20, 40, 100]
FAMILIES = ['momentum', 'trend_pullback', 'mean_reversion', 'breakout', 'momentum_12_1']
FAMILIES += [family + '_market_trend' for family in FAMILIES]


def rate(value):
    return 'Unavailable' if value is None else f'{value * 100:,.2f}%'


def fixture():
    result = {'run_id': RUN, 'created_at': '2026-09-18T21:00:00Z',
        'capture': {'discovered': 8434, 'usable': 8300, 'rows': 25000000, 'failed': [],
                    'markets': [{'currency': currency, 'first_session': '2000-01-03', 'last_session': '2026-09-18', 'rows': 12500000} for currency in ['USD', 'CAD']]},
        'methodology': {'attempts': list(range(30)), 'limitations': ['Browser fixture only; these are synthetic test values.']},
        'portfolios': [], 'benchmarks': [], 'walk_forward': []}
    for currency, budget, cost in itertools.product(['USD', 'CAD'], BUDGETS, COSTS):
        seed = (0.02 if currency == 'CAD' else 0) + BUDGETS.index(budget) * 0.01 + cost / 10000
        common = {'currency': currency, 'budget': budget, 'cost_bps': cost, 'status': 'complete',
                  'first_session': '2000-10-17', 'last_session': '2026-09-18',
                  'total_return': 0.05 + seed, 'max_drawdown': 0.1 + seed,
                  'cagr': 0.01 + seed, 'ending_equity': budget * (1.05 + seed), 'trades': 12, 'fees': budget * 0.001,
                  'monthly_equity_curve': [{'session': '2025-12-31', 'equity': budget, 'cash': 0}, {'session': '2026-06-30', 'equity': budget * 0.95, 'cash': 0}, {'session': '2026-09-18', 'equity': budget * (1.05 + seed), 'cash': budget * (1.05 + seed)}]}
        for strategy, horizon in itertools.product(FAMILIES, [5, 10, 20]):
            result['portfolios'].append({**common, 'strategy': strategy, 'horizon': horizon})
        benchmark = {**common, 'symbol': 'SPY' if currency == 'USD' else 'XIU.TO'}
        result['benchmarks'].extend([benchmark, {**common, 'symbol': 'CASH', 'total_return': 0, 'max_drawdown': 0, 'cagr': 0, 'trades': 0, 'fees': 0}])
        result['walk_forward'].append({**common, 'benchmark': benchmark, 'folds': [{'training_start': '2022-01-03', 'training_end': '2024-12-31', 'test_start': '2025-01-02', 'test_end': '2025-12-31', 'selected_strategy': 'cash', 'selected_horizon': 5, 'test_return': common['total_return']}]})
    return result


def route_fixture(page, result):
    def serve(route):
        url = route.request.url
        if url.endswith('/status'):
            route.fulfill(json={'status': 'completed', 'phase': 'complete', 'latest': {'run_id': RUN}})
        elif url.endswith('/' + RUN):
            route.fulfill(json=result)
        else:
            route.abort()
    page.route('**/api/historical-lab/**', serve)


def open_page(browser, width, mocked=None):
    page = browser.new_page(viewport={'width': width, 'height': 1000})
    errors, mutations = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: mutations.append(request.method + ' ' + request.url) if request.url.startswith(BASE + '/') and request.method not in {'GET', 'HEAD'} else None)
    if mocked is not None:
        route_fixture(page, mocked)
    page.goto(BASE, wait_until='networkidle')
    page.get_by_role('button', name='Strategy lab', exact=True).click()
    page.locator('.historical-research').wait_for()
    return page, errors, mutations


def check_filters(page, result):
    panel = page.locator('.historical-research')
    panel.get_by_label('Historical currency').wait_for()
    checks = []
    for currency, budget, cost in itertools.product(['USD', 'CAD'], BUDGETS, COSTS):
        panel.get_by_label('Historical currency').select_option(currency)
        panel.get_by_label('Historical starting cash').select_option(str(budget))
        panel.get_by_label('Historical round-trip cost').select_option(str(cost))
        match = lambda row: row['currency'] == currency and row['budget'] == budget and row['cost_bps'] == cost
        expected = [row for row in result['portfolios'] if match(row)] + [row for row in result['benchmarks'] if match(row)]
        table = panel.locator('table').last
        rows = table.locator('tbody tr')
        assert rows.count() == len(expected), (currency, budget, cost, rows.count(), len(expected))
        for index, entry in enumerate(expected):
            cells = rows.nth(index).locator('td').all_text_contents()
            assert cells[2] == entry['status'].replace('_', ' '), cells
            assert cells[3:6] == [rate(entry[key]) for key in ('total_return', 'max_drawdown', 'cagr')], (cells, entry)
            assert cells[6] == f"{entry['trades']:,}", cells
            assert cells[7] == f"{entry['fees']:,.2f}", cells
        walk = next((row for row in result['walk_forward'] if match(row)), None)
        if walk:
            summary = panel.locator('p').filter(has=page.locator('strong')).inner_text()
            for value in ['total return ' + rate(walk['total_return']), 'maximum drawdown ' + rate(walk['max_drawdown']), 'annualized return ' + rate(walk['cagr'])]:
                assert value in summary, (summary, value)
            benchmark = walk.get('benchmark', {})
            comparable = (walk['status'] == 'complete' and benchmark.get('status') == 'complete'
                          and walk['first_session'] == benchmark.get('first_session')
                          and walk['last_session'] == benchmark.get('last_session'))
            comparison = panel.get_by_text('Same-period benchmark return:', exact=False)
            legend = panel.locator('.chart-legend').get_by_text('Buy and hold benchmark', exact=True)
            if comparable:
                assert comparison.count() == 1 and legend.count() == 1
                assert rate(benchmark['total_return']) in comparison.inner_text()
            else:
                assert comparison.count() == 0 and legend.count() == 0
            if walk['status'] != 'complete':
                note = panel.get_by_role('note')
                assert 'Full-period returns, drawdowns, and benchmark comparisons are unavailable.' in note.inner_text()
                for missing in walk.get('missing', []):
                    assert missing.replace(':', ' · ') in note.inner_text()
            fold_rows = panel.locator('table').first.locator('tbody tr')
            assert fold_rows.count() == len(walk['folds'])
            for index, fold in enumerate(walk['folds']):
                cells = fold_rows.nth(index).locator('td').all_text_contents()
                assert cells[2] == fold['selected_strategy'].replace('_', ' ')
                assert cells[3] == ('Cash' if fold['selected_strategy'] == 'cash' else str(fold['selected_horizon']) + ' sessions')
                assert cells[4] == rate(fold['test_return'])
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        checks.append({'currency': currency, 'budget': budget, 'cost_bps': cost, 'rows': len(expected)})
    return checks


report = {'kind': 'synthetic browser fixtures', 'widths': [], 'states': []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    result = fixture()
    for width in [1440, 768, 390, 320]:
        page, errors, mutations = open_page(browser, width, result)
        checks = check_filters(page, result)
        page.locator('.historical-research').screenshot(path=str(ROOT / f'mock-completed-{width}.png'))
        assert not errors and not mutations, (errors, mutations)
        report['widths'].append({'width': width, 'filter_checks': checks, 'page_errors': errors, 'mutations': mutations, 'overflow': False})
        page.close()
    incomplete = copy.deepcopy(result)
    for collection in ['portfolios', 'walk_forward', 'benchmarks']:
        for row in incomplete[collection]:
            row.update(status='incomplete', total_return=None, max_drawdown=None, cagr=None, monthly_equity_curve=[])
    page, errors, mutations = open_page(browser, 390, incomplete)
    page.get_by_text('All fixed strategies and benchmarks', exact=True).wait_for()
    text = page.locator('.historical-research').inner_text()
    assert 'Unavailable' in text and 'incomplete' in text
    page.locator('.historical-research').screenshot(path=str(ROOT / 'mock-incomplete-390.png'))
    report['states'].append({'state': 'incomplete', 'errors': errors, 'mutations': mutations, 'text': text[:2500]})
    assert not errors and not mutations
    page.close()
    empty = copy.deepcopy(result)
    empty.update(portfolios=[], benchmarks=[], walk_forward=[])
    page, errors, mutations = open_page(browser, 320, empty)
    page.get_by_text('No rolling test is available for this selection.', exact=True).wait_for()
    assert page.get_by_text('No records for this study.', exact=True).count() >= 1
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    report['states'].append({'state': 'empty', 'errors': errors, 'mutations': mutations, 'overflow': False})
    assert not errors and not mutations
    browser.close()
(ROOT / 'mock-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'widths': len(report['widths']), 'filter_combinations': sum(len(row['filter_checks']) for row in report['widths']), 'states': [row['state'] for row in report['states']], 'report': str(ROOT / 'mock-report.json')}))

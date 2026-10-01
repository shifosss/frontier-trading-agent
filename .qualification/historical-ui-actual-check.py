import json
import urllib.request
from pathlib import Path

namespace = {}
exec(Path('.qualification/historical-ui-mock-check.py').read_text('utf-8').split('\nreport =')[0], namespace)
base = namespace['BASE']
with urllib.request.urlopen(base + '/api/historical-lab/status') as response:
    status = json.load(response)
if status['status'] != 'completed' or not status.get('latest'):
    raise SystemExit('Historical run is not completed yet: ' + json.dumps(status))
run_id = status['latest']['run_id']
with urllib.request.urlopen(base + '/api/historical-lab/runs/' + run_id) as response:
    result = json.load(response)
assert result['run_id'] == run_id
report = {'kind': 'actual completed study', 'run_id': run_id, 'capture': result['capture'], 'widths': []}
print(json.dumps({'stage': 'actual_filter_verification', 'run_id': run_id}), flush=True)
with namespace['sync_playwright']() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    for width in (1440, 390):
        page, errors, mutations = namespace['open_page'](browser, width)
        checks = namespace['check_filters'](page, result)
        panel = page.locator('.historical-research')
        link = panel.get_by_role('link', name='Download historical evidence')
        assert link.get_attribute('href') == '/api/historical-lab/runs/' + run_id + '/download'
        panel.get_by_role('heading', name='Historical strategy development', exact=True).scroll_into_view_if_needed()
        page.screenshot(path=f'.qualification/historical-ui/actual-completed-{width}.png')
        region = panel.get_by_role('region', name='Scrollable historical equity chart')
        if region.count():
            region.evaluate("element=>element.scrollIntoView({block:'center'})")
            page.screenshot(path=f'.qualification/historical-ui/actual-chart-{width}.png')
        assert not errors and not mutations
        report['widths'].append({'width': width, 'filter_checks': checks, 'page_errors': errors, 'app_mutations': mutations, 'overflow': False})
        page.close()
    browser.close()
request = urllib.request.Request(base + '/api/historical-lab/runs/' + run_id + '/download', headers={'Range': 'bytes=0-0'})
with urllib.request.urlopen(request) as response:
    headers = dict(response.headers)
    first = response.read(1)
    assert response.status in (200, 206)
    assert first == b'{'
    assert 'attachment' in response.headers.get('Content-Disposition', '')
    assert run_id in response.headers.get('Content-Disposition', '')
    report['download'] = {'status': response.status, 'headers': headers, 'read_bytes': 1}
Path('.qualification/historical-ui/actual-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'run_id': run_id, 'actual_filter_combinations': sum(len(row['filter_checks']) for row in report['widths']), 'download': report['download'], 'report': '.qualification/historical-ui/actual-report.json'}))

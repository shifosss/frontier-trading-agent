import json
import urllib.request
from pathlib import Path

ns = {}
exec(Path('.qualification/historical-ui-mock-check.py').read_text('utf-8').split('\nreport =')[0], ns)
BASE = ns['BASE']

def read(path):
    with urllib.request.urlopen(BASE + path) as response:
        return json.load(response)

status = read('/api/historical-lab/status')
assert status['status'] == 'running' and status['study_mode'] == 'multi_model'
assert status['run_id'] == '814780d48b4141b9a82a3fb917d1b85a'
previous = status['latest']['run_id']
assert previous == '90af4c840aad48f7ab58fba7a682f96a'
result = read('/api/historical-lab/runs/' + previous)
report = {'kind': 'actual running multi-model study', 'run_id': status['run_id'], 'published_run_id': previous, 'status': {k:v for k,v in status.items() if k != 'latest'}, 'widths': []}
with ns['sync_playwright']() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    for width in [1440, 768, 390, 320]:
        page, errors, mutations = ns['open_page'](browser, width)
        panel=page.locator('.historical-research')
        panel.get_by_role('heading', name='Daily short-hold results', exact=True).wait_for()
        panel.get_by_text('Running rolling model forecasts with separate fitting, calibration and test windows.', exact=True).wait_for()
        assert panel.get_by_role('button', name='Historical study running', exact=True).is_disabled()
        assert panel.get_by_label('Study to run').is_disabled()
        assert panel.get_by_label('Reuse the saved histories from the result below').is_disabled()
        assert panel.get_by_text('A new study is running.', exact=False).count() == 1
        assert panel.get_by_role('link', name='Download historical evidence').get_attribute('href') == '/api/historical-lab/runs/' + previous + '/download'
        assert panel.get_by_label('Study to run').input_value() == 'multi_model'
        assert panel.get_by_role('heading',name='Rolling model study results',exact=True).count() == 0
        assert panel.get_by_text('Published ',exact=False).count() >= 1
        checks=[]
        for currency in ['USD','CAD']:
            panel.get_by_label('Historical currency').select_option(currency)
            panel.get_by_label('Historical starting cash').select_option('2000')
            panel.get_by_label('Historical round-trip cost').select_option('40')
            assert panel.get_by_role('region',name='Short-hold trading statistics').count() == 1
            checks.append({'currency':currency,'budget':2000,'cost':40,'published_mode':'short_horizon'})
        panel.get_by_role('heading', name='Historical strategy development', exact=True).scroll_into_view_if_needed()
        page.screenshot(path=f'.qualification/historical-ui/multi-model-actual-running-{width}.png')
        live=panel.get_by_role('status').inner_text()
        assert status['run_id'] in live
        assert not errors and not mutations, (errors,mutations)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        report['widths'].append({'width':width, 'status_text':live, 'filter_checks':checks, 'page_errors':errors,'mutations':mutations,'overflow':False})
        print(json.dumps({'width':width,'verified_filters':len(checks),'status':live[:350]}),flush=True)
        page.close()
    browser.close()
Path('.qualification/historical-ui/multi-model-actual-running-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'run_id':status['run_id'],'filter_checks':sum(len(w['filter_checks']) for w in report['widths']),'report':'.qualification/historical-ui/multi-model-actual-running-report.json'}))

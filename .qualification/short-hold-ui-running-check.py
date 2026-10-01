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
assert status['status'] == 'running' and status['study_mode'] == 'short_horizon'
assert status['run_id'] == '90af4c840aad48f7ab58fba7a682f96a'
previous = status['latest']['run_id']
assert previous == '577a24e71a844022b3ac86ca66e32c34'
result = read('/api/historical-lab/runs/' + previous)
report = {'kind': 'actual running daily short-hold study', 'run_id': status['run_id'], 'published_run_id': previous, 'status': {k:v for k,v in status.items() if k != 'latest'}, 'widths': []}
with ns['sync_playwright']() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    for width in [1440, 768, 390, 320]:
        page, errors, mutations = ns['open_page'](browser, width)
        panel=page.locator('.historical-research')
        panel.get_by_role('heading', name='Baseline historical results', exact=True).wait_for()
        panel.get_by_text('Running daily screening with 1 / 3 / 5-session holds.', exact=True).wait_for()
        assert panel.get_by_role('button', name='Historical study running', exact=True).is_disabled()
        assert panel.get_by_label('Study to run').is_disabled()
        assert panel.get_by_label('Reuse the saved histories from the result below').is_disabled()
        assert panel.get_by_text('A new study is running.', exact=False).count() == 1
        assert panel.get_by_role('link', name='Download historical evidence').get_attribute('href') == '/api/historical-lab/runs/' + previous + '/download'
        checks=ns['check_filters'](page,result)
        panel.get_by_role('heading', name='Historical strategy development', exact=True).scroll_into_view_if_needed()
        page.screenshot(path=f'.qualification/historical-ui/short-hold-actual-running-{width}.png')
        live=panel.get_by_role('status').inner_text()
        assert status['run_id'] in live
        assert not errors and not mutations, (errors,mutations)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        report['widths'].append({'width':width, 'status_text':live, 'filter_checks':checks, 'page_errors':errors,'mutations':mutations,'overflow':False})
        print(json.dumps({'width':width,'verified_filters':len(checks),'status':live[:350]}),flush=True)
        page.close()
    browser.close()
Path('.qualification/historical-ui/short-hold-actual-running-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'run_id':status['run_id'],'filter_checks':sum(len(w['filter_checks']) for w in report['widths']),'report':'.qualification/historical-ui/short-hold-actual-running-report.json'}))

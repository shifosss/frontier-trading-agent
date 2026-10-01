import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
saved=json.loads(Path('artifacts/final-validation.json').read_text(encoding='utf-8'))
report={"pages":[],"errors":[],"failed_requests":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1000},device_scale_factor=1)
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.on('response',lambda r: report['failed_requests'].append({'url':r.url,'status':r.status}) if r.status>=400 else None)
    page.goto('http://127.0.0.1:8765',wait_until='networkidle')
    run=page.get_by_role('button',name=re.compile('^Run study'))
    expect(run).to_be_enabled()
    with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST',timeout=60000) as response:
        run.click()
    assert response.value.status==200
    record=response.value.json()['record']
    report['browser_run_id']=record['id']
    expect(run).to_be_enabled(timeout=20000)
    rerun=page.get_by_role('button',name='Rerun saved settings',exact=True)
    with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST',timeout=60000) as rerun_response:
        rerun.click()
    assert rerun_response.value.status==200
    assert rerun_response.value.json()['record']['config']==record['config']
    report['rerun_id']=rerun_response.value.json()['record']['id']
    expect(rerun).to_be_enabled(timeout=20000)
    page.get_by_role('tab',name='Fills',exact=True).click()
    page.screenshot(path='.qualification/frontier-study.png',full_page=False)
    with page.expect_response(lambda r:r.url.endswith('/api/frozen') and r.request.method=='POST') as response:
        page.get_by_role('button',name='Freeze for observation',exact=True).click()
    assert response.value.status==200
    report['browser_frozen_id']=response.value.json()['frozen_id']
    page.get_by_role('button',name='Research',exact=True).click()
    campaign=page.get_by_role('combobox',name='Campaign',exact=True)
    expect(campaign).to_be_visible(timeout=20000)
    campaign.select_option('787940fbcd694c7194724efd76324925')
    expect(page.get_by_text('2 accepted replays',exact=True)).to_be_visible()
    page.get_by_text('Recorded model usage',exact=True).first.click()
    page.screenshot(path='.qualification/frontier-research.png',full_page=False)
    page.get_by_role('button',name='Inspect replay',exact=True).first.click()
    earlier=page.get_by_text('Saved with an earlier research version.',exact=False)
    expect(earlier).to_be_visible(timeout=20000)
    rerun_old=page.get_by_role('button',name='Rerun saved settings',exact=True)
    expect(rerun_old).to_be_enabled(timeout=20000)
    with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST',timeout=60000) as updated:
        rerun_old.click()
    assert updated.value.status==200
    report['earlier_version_rerun_id']=updated.value.json()['record']['id']
    expect(rerun_old).to_be_enabled(timeout=20000)
    expect(earlier).to_have_count(0)
    page.get_by_role('button',name='Research',exact=True).click()
    frozen=page.get_by_role('combobox',name='Frozen configuration',exact=True)
    expect(frozen).to_be_visible(timeout=20000)
    frozen.select_option(saved['observation']['frozen_id'])
    page.get_by_role('combobox',name='New dataset version',exact=True).select_option('3c041e7b3772e7662ec019cf4fb4101e2020695169dd7f6164e54d3431259e5a')
    observe=page.get_by_role('button',name='Record observation',exact=True)
    expect(observe).to_be_enabled()
    with page.expect_response(lambda r:r.url.endswith('/api/observations') and r.request.method=='POST') as response:
        observe.click()
    assert response.value.status==200,response.value.text()
    report['observation']=response.value.json()['classification']
    assert response.value.json()['observation_id']==saved['observation']['observation_id']
    expect(observe).to_be_enabled(timeout=20000)
    for name in ['Study','Data','Research','Experiments','Operations']:
        page.get_by_role('button',name=name,exact=True).click()
        page.wait_for_load_state('networkidle')
        report['pages'].append({'page':name,'width':1440,'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
    page.set_viewport_size({'width':390,'height':844})
    for name in ['Study','Research','Data','Experiments','Operations']:
        page.get_by_role('button',name=name,exact=True).click()
        page.wait_for_load_state('networkidle')
        report['pages'].append({'page':name,'width':390,'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
        if name=='Research':
            page.screenshot(path='.qualification/frontier-mobile.png',full_page=False)
    assert not report['errors'],report['errors']
    assert not report['failed_requests'],report['failed_requests']
    assert all(not item['overflow'] for item in report['pages']),report['pages']
    browser.close()
Path('artifacts/browser-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

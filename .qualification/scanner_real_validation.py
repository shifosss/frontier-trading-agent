import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path('.qualification/scanner-real-validation')
root.mkdir(parents=True,exist_ok=True)
report={'fixture':False,'errors':[],'http_errors':[],'pages':[]}
base='http://127.0.0.1:8765'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    page.on('response',lambda response: report['http_errors'].append({'url':response.url,'status':response.status}) if response.status>=400 else None)
    page.goto(base,wait_until='networkidle')
    expect(page.get_by_role('heading',name='Market scanner',exact=True)).to_be_visible()
    expect(page.get_by_label('Simulated USD cash',exact=True)).to_have_value('0')
    expect(page.get_by_label('Simulated CAD cash',exact=True)).to_have_value('700')
    artifact=json.loads((root/'downloaded-scan.json').read_text('utf-8'))
    report['submission_note']='Fresh browser POST and exact download completed in preceding run; this pass checks the saved artifact and correct Assumptions-tab selector without another source fetch.'
    report['scan_id']=artifact['scan_id']
    report['capture_id']=artifact['source']['capture_id']
    report['source']=artifact['source']
    report['summary']=artifact['study']['summary']
    report['selected']=artifact['scan']['selected']
    expect(page.get_by_role('combobox',name='Saved market scan',exact=True)).to_have_value(artifact['scan_id'])
    expect(page.get_by_role('button',name='Run market scan',exact=True)).to_be_enabled(timeout=30000)
    assert artifact['scan']['cash_by_currency']=={'USD':0.0,'CAD':700.0}
    assert artifact['study']['summary']['USD']['status']=='unfunded'
    assert artifact['study']['summary']['USD']['cohort_count']==0
    expect(page.get_by_text('No simulated cash in this currency; no funded comparison was run.',exact=True)).to_be_visible()
    with page.expect_download() as download_info:
        page.get_by_role('button',name='Download scan and evidence',exact=True).click()
    download_path=root/'downloaded-scan.json'
    download_info.value.save_as(download_path)
    assert json.loads(download_path.read_text('utf-8'))==artifact
    report['download_exact']=True
    page.get_by_text('Inspect all 41 instruments',exact=True).click()
    expect(page.get_by_text('Canadian Natural Resources',exact=True)).to_be_visible()
    for width,height in [(1440,1000),(768,1024),(390,844),(320,750)]:
        page.set_viewport_size({'width':width,'height':height})
        for name in ['Scanner','Study','Research','Data','Experiments','Operations']:
            page.get_by_role('button',name=name,exact=True).click()
            page.wait_for_load_state('networkidle')
            report['pages'].append({'page':name,'width':width,'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth')})
            if name=='Scanner':
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=str(root/f'scanner-{width}.png'))
    repaired=json.loads(Path('artifacts/dividend-remediation-study.json').read_text('utf-8'))
    page.set_viewport_size({'width':1440,'height':1000})
    page.goto(base+'/?study='+repaired['run_id'],wait_until='networkidle')
    expect(page.get_by_role('heading',name='Research study',exact=True)).to_be_visible()
    expect(page.get_by_text('Exploratory return',exact=True)).to_be_visible()
    page.get_by_role('tab',name='Assumptions',exact=True).click()
    expect(page.get_by_text('Gross dividends earned: 7.61 USD / 0.00 CAD.',exact=False)).to_be_visible()
    page.screenshot(path=str(root/'repaired-study-1440.png'))
    report['repaired_study_id']=repaired['run_id']
    browser.close()
assert not report['errors'],report['errors']
assert not report['http_errors'],report['http_errors']
assert not any(item['overflow'] for item in report['pages']),report['pages']
Path('artifacts/scanner-browser-validation.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report,indent=2))

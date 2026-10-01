import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base='http://127.0.0.1:8765'
root=Path('.qualification/usd-funding-ui')
root.mkdir(parents=True,exist_ok=True)
report={'errors':[],'http_errors':[],'views':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.on('response',lambda r:report['http_errors'].append({'url':r.url,'status':r.status}) if r.status>=400 else None)
    page.goto(base,wait_until='networkidle')
    expect(page.get_by_role('heading',name='Market scanner',exact=True)).to_be_visible()
    page.get_by_label('Simulated USD cash',exact=True).fill('0')
    page.get_by_label('Simulated CAD cash',exact=True).fill('700')
    page.get_by_label('CAD to convert (simulation)',exact=True).fill('700')
    with page.expect_response(lambda r:r.url==base+'/api/scans' and r.request.method=='POST',timeout=180000) as pending:
        page.get_by_role('button',name='Run market scan',exact=True).click()
    response=pending.value
    assert response.status==200,response.text()
    scan=response.json()
    report['scan_id']=scan['scan_id']
    report['funding']=scan['funding']
    report['request']=response.request.post_data_json
    report['summary']=scan['study']['summary']
    assert report['request']=={'refresh':True,'initial_cash_usd':0,'initial_cash_cad':700,'convert_cad':700}
    assert scan['funding']['cash_before']=={'USD':0,'CAD':700}
    assert scan['funding']['cash_after']=={'CAD':0,'USD':492.92}
    assert scan['scan']['cash_by_currency']==scan['funding']['cash_after']
    assert scan['study']['summary']['CAD']['status']=='unfunded'
    assert scan['study']['summary']['USD']['status']=='studied'
    expect(page.get_by_role('combobox',name='Saved market scan',exact=True)).to_have_value(scan['scan_id'])
    expect(page.get_by_role('heading',name='Simulated CAD-to-USD funding',exact=True)).to_be_visible()
    expect(page.get_by_text('before broker spread and account charges.',exact=False).first).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role('button',name='Download scan and evidence',exact=True).click()
    target=root/'downloaded-scan.json'
    download.value.save_as(target)
    assert json.loads(target.read_text('utf-8'))==scan
    report['download_exact']=True
    # Reopening saved conversion restores original balances, not the already converted ones.
    for scan_id,conversion in [('a7f07d83bbc44f0c90d23704a4d994c7','0'),(scan['scan_id'],'700')]:
        page.get_by_role('combobox',name='Saved market scan',exact=True).select_option(scan_id)
        expect(page.get_by_label('Simulated CAD cash',exact=True)).to_have_value('700')
        expect(page.get_by_label('Simulated USD cash',exact=True)).to_have_value('0')
        expect(page.get_by_label('CAD to convert (simulation)',exact=True)).to_have_value(conversion)
    page.reload(wait_until='networkidle')
    expect(page.get_by_label('CAD to convert (simulation)',exact=True)).to_have_value('700')
    for width in [1440,768,390,320]:
        page.set_viewport_size({'width':width,'height':1000})
        overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not overflow,width
        report['views'].append({'width':width,'overflow':overflow})
        page.screenshot(path=str(root/f'scanner-{width}.png'))
    browser.close()
assert not report['errors'],report
assert not report['http_errors'],report
Path('artifacts/usd-funding-browser-validation.json').write_text(json.dumps(report,indent=2),'utf-8')
Path('artifacts/usd-funding-study.json').write_text(json.dumps(scan,indent=2),'utf-8')
print(json.dumps(report,indent=2))

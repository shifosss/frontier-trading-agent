import json,re
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8765',wait_until='networkidle')
    with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST',timeout=60000) as response:
        page.get_by_role('button',name=re.compile('^Run study')).click()
    result=response.value.json()
    print('run_status',response.value.status)
    print('summary',json.dumps(result.get('record',{}).get('summary'),ensure_ascii=True))
    page.get_by_role('tab',name='Fills',exact=True).wait_for()
    page.screenshot(path='.qualification/workstation-result.png',full_page=True)
    print('buttons',page.get_by_role('button').all_text_contents())
    page.get_by_role('tab',name='Fills',exact=True).click()
    print('fills_visible',page.locator('body').inner_text()[-4500:])
    page.get_by_role('button',name='Experiments',exact=True).click()
    print('experiments',page.locator('body').inner_text()[:2500])
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Study',exact=True).click()
    page.screenshot(path='.qualification/workstation-mobile.png',full_page=False)
    print('mobile_overflow',page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    print('page_errors',errors)
    browser.close()

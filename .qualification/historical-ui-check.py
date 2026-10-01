import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('.qualification/historical-ui'); root.mkdir(exist_ok=True)
report=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    for width in (1440,768,390,320):
        page=browser.new_page(viewport={'width':width,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8765',wait_until='networkidle')
        page.get_by_role('button',name='Strategy lab',exact=True).click()
        page.get_by_role('heading',name='Historical strategy development',exact=True).wait_for()
        page.wait_for_timeout(500)
        overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        page.screenshot(path=str(root/f'capture-{width}.png'),full_page=False)
        report.append({'width':width,'overflow':overflow,'errors':errors,'historical':page.locator('.historical-research').inner_text()[:1400]})
        assert not errors and not overflow,report[-1]
        page.close()
    browser.close()
(root/'capture-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

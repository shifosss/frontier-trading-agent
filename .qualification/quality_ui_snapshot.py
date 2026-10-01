import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
phase=sys.argv[1]
root=Path('.qualification')/f'quality-ui-{phase}'
root.mkdir(exist_ok=True)
report={'phase':phase,'errors':[],'pages':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto('http://127.0.0.1:8765',wait_until='networkidle')
    for width,height in [(1440,1000),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        for name in ['Study','Research','Data','Experiments','Operations']:
            page.get_by_role('button',name=name,exact=True).click()
            page.wait_for_load_state('networkidle')
            if name=='Research':
                expect(page.get_by_role('button',name='Refresh saved research',exact=True)).to_be_enabled(timeout=20000)
            page.screenshot(path=str(root/f'{name}-{width}.png'))
            text=page.locator('body').inner_text()
            (root/f'{name}-{width}.txt').write_text(text,encoding='utf-8')
            report['pages'].append({'page':name,'width':width,'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
    browser.close()
assert not report['errors'],report
assert not any(p['overflow'] for p in report['pages']),report
(root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

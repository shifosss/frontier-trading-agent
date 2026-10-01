from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
    page.goto('http://127.0.0.1:8765',wait_until='networkidle')
    page.screenshot(path='.qualification/workstation-first.png',full_page=True)
    print(page.locator('body').inner_text()[:7500])
    browser.close()

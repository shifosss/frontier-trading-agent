import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(".qualification/operator-ui-actual")
root.mkdir(exist_ok=True)
report = {"fixture": False, "broker_contacted": False, "errors": [], "http_errors": [], "widths": []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":1000})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on("response", lambda response: report["http_errors"].append({"url":response.url,"status":response.status}) if response.status >= 400 else None)
    page.goto("http://127.0.0.1:8765/",wait_until="networkidle")
    expect(page.get_by_role("heading",name="Trading desk",exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="Paper account setup needed",exact=True)).to_be_visible()
    status = page.request.get("http://127.0.0.1:8765/api/operator/status").json()
    assert status["status"] == "setup_required" and status["account"] is None and status["orders"] == []
    for width,height in ((1440,1000),(768,1024),(390,844),(320,750)):
        page.set_viewport_size({"width":width,"height":height})
        page.get_by_role("button",name="Refresh desk",exact=True).click()
        expect(page.get_by_role("button",name="Refresh desk",exact=True)).to_be_enabled()
        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        report["widths"].append({"width":width,"overflow":overflow})
        page.screenshot(path=str(root / f"desk-{width}.png"),full_page=True)
    page.set_viewport_size({"width":1440,"height":1000})
    page.get_by_role("button",name=re.compile("Scanner")).click()
    expect(page.get_by_role("heading",name="Market scanner",exact=True)).to_be_visible()
    report["scanner_navigation"] = True
    page.get_by_role("button",name=re.compile("Trading desk")).click()
    expect(page.get_by_role("heading",name="Trading desk",exact=True)).to_be_visible()
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("heading",name="Paper account setup needed",exact=True)).to_be_visible()
    report["reload"] = True
    assert not report["errors"] and not report["http_errors"] and not any(x["overflow"] for x in report["widths"]),report
    browser.close()
(root / "report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))

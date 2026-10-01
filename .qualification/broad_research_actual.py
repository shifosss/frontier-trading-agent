import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(".qualification/broad-research-ui")
root.mkdir(exist_ok=True)
report={"fixture":False,"errors":[],"http_errors":[],"requests":[],"widths":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1000})
    page.on("pageerror",lambda e:report["errors"].append(str(e)))
    page.on("request",lambda r:report["requests"].append({"method":r.method,"url":r.url}) if "/api/" in r.url else None)
    page.on("response",lambda r:report["http_errors"].append({"url":r.url,"status":r.status}) if r.status>=400 else None)
    page.goto("http://127.0.0.1:8765/",wait_until="networkidle")
    page.get_by_role("button",name=re.compile("Strategy lab")).click()
    expect(page.get_by_role("heading",name="A broader search for useful strategies",exact=True)).to_be_visible()
    expect(page.get_by_role("button",name="Refresh status",exact=True)).to_be_enabled()
    status=page.request.get("http://127.0.0.1:8765/api/research-lab/status").json()
    report["saved_status"]={key:status.get(key) for key in ["status","phase","discovered","requested","attempted","cached","usable","failed"]}
    for width in [1440,768,390,320]:
        page.set_viewport_size({"width":width,"height":1000})
        page.get_by_role("button",name="Refresh status",exact=True).click()
        expect(page.get_by_role("button",name="Refresh status",exact=True)).to_be_enabled()
        report["widths"].append({"width":width,"overflow":page.evaluate("document.documentElement.scrollWidth > innerWidth")})
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(root/f"actual-{width}.png"),full_page=True)
    assert all(r["method"]=="GET" for r in report["requests"]),report
    assert not report["errors"] and not report["http_errors"] and not any(x["overflow"] for x in report["widths"]),report
    browser.close()
(root/"actual-report.json").write_text(json.dumps(report,indent=2),encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k!="requests"},indent=2))

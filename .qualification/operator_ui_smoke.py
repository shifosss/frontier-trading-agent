import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(".qualification/operator-ui-smoke")
root.mkdir(exist_ok=True)
setup = dict(mode="paper",initialized=False,status="setup_required",message="No dedicated paper account has been configured.",account=None,policy=None,latest_cycle=None,orders=[],requirements=["Paper connection has not been validated. Live mode is unavailable."])
ready = dict(setup,initialized=True,status="ready",message="Saved paper workflow is ready for its next scheduled cycle.",account=dict(account_id="ui-fixture-paper-account",initial_cash_usd=500,last_snapshot=dict(account=dict(cash="425.12",equity="501.20",currency="USD"),positions=[dict(symbol="EXAMPLE",qty="2",market_value="76.08",avg_entry_price="37.44")]),risk=dict(equity_cad=690.15,unit_nav=1.0024,high_watermark=1.0024,drawdown=0,halted=False)),latest_cycle=dict(session="2026-09-18",created_at="2026-09-18T14:00:00Z",status="completed",plan=dict(source_session="2026-09-17",decision_at="2026-09-18T13:00:00Z",eligible_at="2026-09-18T13:30:00Z",expires_at="2026-09-18T20:00:00Z",regime=dict(symbol="SPY",status="risk_on",reason="UI fixture trend filter permits entries"),decisions=[dict(symbol="EXAMPLE",action="buy",reason="UI fixture selection for a bounded cash allocation.")],intents=[dict(symbol="EXAMPLE",side="buy",qty="2",type="limit",limit_price="37.50",time_in_force="day",reason="UI fixture")])),orders=[dict(id="ui-fixture-order",session="2026-09-18",payload=dict(symbol="EXAMPLE",side="buy",qty="2",type="limit",limit_price="37.50"),state="acknowledged",broker=dict(status="filled",filled_qty="2",filled_avg_price="37.44"))])
report = dict(fixture=True,errors=[],requests=[],states=[])
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
    page = browser.new_page(viewport=dict(width=1440,height=1000))
    page.on("pageerror",lambda error:report["errors"].append(str(error)))
    current = setup
    def status(route):
        report["requests"].append(dict(method=route.request.method,url=route.request.url))
        route.fulfill(json=current)
    page.route("**/api/operator/status",status)
    page.goto("http://127.0.0.1:8765",wait_until="networkidle")
    expect(page.get_by_role("heading",name="Trading desk",exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="Paper account setup needed",exact=True)).to_be_visible()
    expect(page.get_by_text("FRONTIER_ALPACA_PAPER_SECRET",exact=True)).to_be_visible()
    for width,height in [(1440,1000),(768,1024),(390,844),(320,750)]:
        page.set_viewport_size(dict(width=width,height=height))
        for state,title in [(setup,"Paper account setup needed"),(ready,"Local paper workflow ready"),(dict(ready,status="paused"),"Paper workflow paused"),(dict(ready,status="recovery_required"),"Reconciliation required"),(dict(ready,status="risk_halted",latest_cycle=dict(ready["latest_cycle"],plan=dict(ready["latest_cycle"]["plan"],regime="risk_halted"))),"Risk limit reached")]:
            current = state
            page.get_by_role("button",name="Refresh desk",exact=True).click()
            expect(page.get_by_role("heading",name=title,exact=True)).to_be_visible()
            expect(page.get_by_role("button",name="Refresh desk",exact=True)).to_be_enabled()
            report["states"].append(dict(status=state["status"],width=width,overflow=page.evaluate("document.documentElement.scrollWidth > innerWidth")))
            if state["status"] in {"setup_required","ready"}:
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(root/f"{state['status']}-{width}.png"))
        expect(page.get_by_text("501.20",exact=True)).to_be_visible()
        expect(page.get_by_role("columnheader",name="Broker state",exact=True)).to_be_visible()
        expect(page.get_by_role("cell",name="filled",exact=True)).to_be_visible()
    assert all(request["method"] == "GET" for request in report["requests"]),report
    assert not report["errors"],report
    assert not any(state["overflow"] for state in report["states"]),report
    browser.close()
(root/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))

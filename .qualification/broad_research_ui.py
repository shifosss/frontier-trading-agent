import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(".qualification/broad-research-ui")
root.mkdir(exist_ok=True)
strategies = ["momentum", "trend_pullback", "mean_reversion", "breakout"]
run_id = "a" * 32
result = {
    "run_id": run_id, "created_at": "2026-09-18T19:00:00Z",
    "capture": {"discovered": 5640, "requested": 5640, "usable": 5000, "rows": 5000000, "failed": []},
    "forward_observation": {"status":"pending","planned_cohorts":96,"tracked_cohorts":96, "pending_count":95,"complete_count":0,"incomplete_count":0,"version_mismatch_count":1,"snapshot_recorded_at":"2026-09-18T19:00:00Z","evaluation_path":"forward-studies/evaluations/fixture.json"},
    "summaries": [{"currency": currency, "strategy": family, "horizon": horizon, "budget": budget,
        "period": period, "cost_bps": cost, "scheduled_cohorts": 24, "complete_cohorts": 20,
        "incomplete_cohorts": 1, "purged_cohorts": 1, "pending_cohorts": 2,
        "cash_only_cohorts": 8 if budget == 500 else 0, "mean_return": budget/1000000,
        "mean_benchmark_return": 0.01, "mean_excess_return": budget/1000000-0.01,
        "mean_invested_fraction": 0.3 if budget == 500 else 0.85}
        for currency in ["CAD", "USD"] for family in strategies for horizon in [5,10,20]
        for budget in [500,2000,10000,100000] for period in ["development","validation","evaluation"]
        for cost in [20,40,100]],
    "latest_candidates": [{"currency": currency, "strategy": family, "symbol": f"TEST{rank}",
        "session": "2026-09-17", "rank": rank, "price": 500 if rank == 1 else 25,
        "average_dollar_volume_20": 10000000,
        "quantities_by_budget": {"500": 0 if rank == 1 else 2, "2000": 4, "10000": 10, "100000": 20}}
        for currency in ["CAD","USD"] for family in strategies for rank in [1,2]],
    "methodology": {"kind": "cohorts", "entry": "Next session close", "sizing": "Whole shares",
        "costs": "20/40/100 bps", "benchmark": "SPY and XIU.TO", "partition": "60/20/20",
        "missing_data": "Incomplete pairs excluded", "budgets": [500,2000,10000,100000],
        "periods": {currency: {period: {"first_session":"2025-01-01","last_session":"2026-09-17"}
            for period in ["development","validation","evaluation"]} for currency in ["CAD","USD"]},
        "limitations": ["Current membership bias", "Not account profit and loss"]}}
current = {"status":"idle","phase":"not_started","latest":None}
report = {"fixture": True,"errors":[],"requests":[],"widths":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1000})
    page.on("pageerror",lambda e:report["errors"].append(str(e)))
    def handle(route):
        report["requests"].append({"method":route.request.method,"url":route.request.url})
        if route.request.url.endswith("/status"):route.fulfill(json=current)
        elif route.request.url.endswith("/start"):route.fulfill(json={"status":"starting","pid":123})
        else:route.fulfill(json=result)
    page.route("**/api/research-lab/**",handle)
    page.goto("http://127.0.0.1:8765/",wait_until="networkidle")
    page.get_by_role("button",name=re.compile("Strategy lab")).click()
    expect(page.get_by_role("heading",name="Ready to start",exact=True)).to_be_visible()
    assert all(x["method"] == "GET" for x in report["requests"])
    count=len(report["requests"])
    page.wait_for_timeout(5300)
    assert len(report["requests"])==count, "Idle status should not poll"
    page.get_by_role("button",name="Run broad research",exact=True).click()
    expect(page.get_by_role("heading",name="Starting research worker",exact=True)).to_be_visible()
    current={"status":"running","phase":"capture","discovered":5640,"requested":5640,
        "cached":50,"attempted":100,"usable":148,"failed":2,"updated_at":"2026-09-18T19:00:00Z"}
    page.wait_for_timeout(5300)
    expect(page.get_by_role("heading",name="Research is running",exact=True)).to_be_visible()
    report["active_polling_verified"]=True
    for width in [1440,768,390,320]:
        page.set_viewport_size({"width":width,"height":1000})
        for status,title in [("running","Research is running"),("failed","Research needs attention"),
            ("interrupted","Research was interrupted"),("completed","Research completed")]:
            current={**current,"status":status,"latest":{"run_id":run_id,"created_at":result["created_at"]}}
            page.get_by_role("button",name="Refresh status",exact=True).click()
            expect(page.get_by_role("heading",name=title,exact=True)).to_be_visible()
            expect(page.get_by_role("heading",name="Latest completed comparison",exact=True)).to_be_visible()
            assert page.get_by_role("cell",name="Momentum",exact=True).count()==1
            expect(page.get_by_role("heading",name="Forward observations",exact=True)).to_be_visible()
            expect(page.get_by_text("Blocked by version",exact=True)).to_be_visible()
            expect(page.get_by_text("Snapshot plans",exact=True)).to_be_visible()
            expect(page.get_by_role("link",name="Download forward observations",exact=True)).to_be_visible()
            report["widths"].append({"width":width,"status":status,
                "overflow":page.evaluate("document.documentElement.scrollWidth > innerWidth")})
        page.get_by_label("Simulated budget",exact=True).select_option("100000")
        expect(page.get_by_role("cell",name="10.00%",exact=True).first).to_be_visible()
        page.get_by_label("Simulated budget",exact=True).select_option("500")
        assert page.get_by_role("cell",name="TEST1",exact=True).count()==0
        expect(page.get_by_role("cell",name="TEST2",exact=True)).to_be_visible()
        page.get_by_role("checkbox").uncheck()
        expect(page.get_by_role("cell",name="TEST1",exact=True)).to_be_visible()
        page.get_by_role("checkbox").check()
        page.get_by_label("Market currency",exact=True).select_option("CAD")
        page.get_by_label("Strategy family",exact=True).select_option("breakout")
        expect(page.get_by_role("columnheader",name="Close · CAD",exact=True)).to_be_visible()
        page.get_by_label("Market currency",exact=True).select_option("USD")
        page.get_by_label("Strategy family",exact=True).select_option("momentum")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(root/f"completed-{width}.png"),full_page=True)
    assert len([x for x in report["requests"] if x["method"]=="POST"])==1
    assert not report["errors"],report
    assert not any(x["overflow"] for x in report["widths"]),report
    browser.close()
(root/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({key:value for key,value in report.items() if key != "requests"},indent=2))

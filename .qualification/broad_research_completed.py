import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(".qualification/broad-research-ui")
root.mkdir(exist_ok=True)
report={"fixture":False,"errors":[],"http_errors":[],"requests":[],"widths":[],"filters":[],"downloads":{}}
run_id="114df178722046bebaca0db1e3c7d8e7"
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1000})
    page.on("pageerror",lambda e:report["errors"].append(str(e)))
    page.on("request",lambda r:report["requests"].append({"method":r.method,"url":r.url}) if "/api/" in r.url else None)
    page.on("response",lambda r:report["http_errors"].append({"url":r.url,"status":r.status}) if r.status>=400 else None)
    page.goto("http://127.0.0.1:8765/",wait_until="networkidle")
    page.get_by_role("button",name=re.compile("Strategy lab")).click()
    expect(page.get_by_role("heading",name="Research completed",exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="Latest completed comparison",exact=True)).to_be_visible()
    status=page.request.get("http://127.0.0.1:8765/api/research-lab/status").json()
    assert status["latest"]["run_id"]==run_id,status
    report["saved_status"]={key:status.get(key) for key in ["status","phase","discovered","requested","attempted","cached","usable","failed"]}
    saved=page.request.get(f"http://127.0.0.1:8765/api/research-lab/runs/{run_id}").json()
    assert "cohorts" not in saved
    assert len(saved["summaries"])==864 and len(saved["attempts"])==12
    report["run_id"]=run_id
    report["summary_count"]=len(saved["summaries"])
    report["forward"]=saved["forward_observation"]
    for endpoint in ["download","forward"]:
        url=f"http://127.0.0.1:8765/api/research-lab/runs/{run_id}/{endpoint}"
        response=page.request.get(url)
        assert response.status==200,(url,response.status)
        assert "attachment" in response.headers.get("content-disposition",""),response.headers
        document=response.json()
        report["downloads"][endpoint]={"status":response.status,"bytes":len(response.body()),
            "content_disposition":response.headers.get("content-disposition"),"keys":list(document)}
        if endpoint=="download":
            assert document["run_id"]==run_id and len(document["cohorts"])==11840
            report["downloads"][endpoint]["cohort_count"]=len(document["cohorts"])
        else:
            assert len(document["cohorts"])==96
            assert all(row["status"]=="pending" for row in document["cohorts"])
            report["downloads"][endpoint]["pending_cohorts"]=96
    for width in [1440,768,390,320]:
        page.set_viewport_size({"width":width,"height":1000})
        for currency,budget,horizon,cost in [("USD",500,10,40),("USD",100000,10,40),
            ("CAD",500,5,20),("CAD",100000,20,100)]:
            page.get_by_label("Market currency",exact=True).select_option(currency)
            page.get_by_label("Simulated budget",exact=True).select_option(str(budget))
            page.get_by_label("Holding period",exact=True).select_option(str(horizon))
            page.get_by_label("Round-trip costs",exact=True).select_option(str(cost))
            expected=next(row for row in saved["summaries"] if row["currency"]==currency
                and row["budget"]==budget and row["horizon"]==horizon and row["cost_bps"]==cost
                and row["period"]=="evaluation" and row["strategy"]=="momentum")
            row=page.get_by_role("row").filter(has=page.get_by_role("cell",name="Momentum",exact=True))
            assert row.count()==1
            cells=row.get_by_role("cell").all_text_contents()
            value=expected["mean_return"]
            mean="Insufficient observations" if value is None else f"{value*100:,.2f}%"
            assert cells[1]==mean,(width,currency,budget,horizon,cost,cells,mean)
            assert cells[5]==f'{expected["complete_cohorts"]:,}'
            report["filters"].append({"width":width,"currency":currency,"budget":budget,
                "horizon":horizon,"cost_bps":cost,"momentum_mean_return":cells[1],
                "complete_cohorts":expected["complete_cohorts"]})
        expect(page.get_by_role("heading",name="Forward observations",exact=True)).to_be_visible()
        expect(page.get_by_text("Blocked by version",exact=True)).to_be_visible()
        expect(page.get_by_role("link",name="Download forward observations",exact=True)).to_be_visible()
        for title in ["Momentum","Trend pullback","Mean reversion","Breakout"]:
            assert page.get_by_role("cell",name=title,exact=True).count()==1
        page.get_by_label("Market currency",exact=True).select_option("USD")
        page.get_by_label("Simulated budget",exact=True).select_option("500")
        page.get_by_label("Holding period",exact=True).select_option("10")
        page.get_by_label("Round-trip costs",exact=True).select_option("40")
        report["widths"].append({"width":width,"overflow":page.evaluate("document.documentElement.scrollWidth > innerWidth")})
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(root/f"completed-actual-{width}.png"),full_page=True)
        if width in [1440,320]:
            page.screenshot(path=str(root/f"completed-viewport-{width}.png"))
            page.get_by_role("heading",name="Latest completed comparison",exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(root/f"completed-comparison-{width}.png"))
    assert all(r["method"]=="GET" for r in report["requests"]),report
    assert not report["errors"] and not report["http_errors"] and not any(x["overflow"] for x in report["widths"]),report
    browser.close()
(root/"completed-actual-report.json").write_text(json.dumps(report,indent=2),encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k!="requests"},indent=2))

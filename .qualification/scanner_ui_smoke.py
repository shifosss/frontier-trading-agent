import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(".qualification/scanner-ui-smoke")
root.mkdir(exist_ok=True)
row = dict(symbol="EXAMPLE.TO", name="UI fixture stock", currency="CAD", group="sample", asset_type="stock", status="selected", reasons=["Positive 20 and 60 session momentum; sufficient daily turnover."], last_session="2026-09-17", expected_session="2026-09-17", price=80, momentum_20=.05, momentum_60=.11, annualized_volatility=.2, average_dollar_volume_20=10000000, score=.4, rank=1, quantity=2, estimated_notional=160, estimated_cost=1.08, allocation_fraction=.16, sizing_reason="Whole shares within the position cap.")
excluded = dict(row, symbol="ETF.TO", name="UI fixture benchmark", asset_type="etf", status="excluded", reasons=["ETF used as benchmark context only."], quantity=0, estimated_notional=0, estimated_cost=0, allocation_fraction=0)
summary = dict(cohort_count=30, paired_cohort_count=30, candidate_count=75, mean_return=.01, median_return=.006, win_rate=.53, mean_benchmark_return=.012, mean_excess_return=-.002, mean_stressed_return=.008)
artifact = dict(scan_id="ui-fixture", created_at="2026-09-18T01:00:00Z", source=dict(name="UI fixture source", as_of="2026-09-18T01:00:00Z", capture_id="ui-fixture", succeeded=2, failed=[], cached=False), scan=dict(as_of="2026-09-18T01:00:00Z", status="watchlist", universe_size=2, rows=[row, excluded], selected=[row], cash_by_currency=dict(USD=0,CAD=700), unallocated_cash=dict(USD=0,CAD=538.92), limitations=["UI fixture, not a market result."]), study=dict(policy=dict(diagnostic_holding_sessions=5,diagnostic_entry="next-session close",diagnostic_round_trip_cost_bps=20,diagnostic_stressed_cost_bps=40),summary=dict(USD=summary,CAD=summary),limitations=["UI fixture diagnostic."]),readiness=dict(status="research_only",reasons=["Active capital awaits confirmation; no automatic currency conversion."]))
report = dict(fixture=True, errors=[], pages=[], submitted=[])
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
    page = browser.new_page(viewport=dict(width=1440,height=1000))
    page.on("pageerror",lambda e:report["errors"].append(str(e)))
    def scans(route):
        if route.request.method == "POST":
            report["submitted"].append(route.request.post_data_json)
            route.fulfill(json=dict(artifact,scan_id="ui-fixture-new",created_at="2026-09-18T02:00:00Z"))
        else:
            route.fulfill(json=[artifact])
    page.route("**/api/scans",scans)
    page.goto("http://127.0.0.1:8765",wait_until="networkidle")
    expect(page.get_by_role("heading",name="Market scanner",exact=True)).to_be_visible()
    expect(page.get_by_label("Simulated USD cash",exact=True)).to_have_value("0")
    expect(page.get_by_label("Simulated CAD cash",exact=True)).to_have_value("700")
    expect(page.get_by_role("heading",name="Current simulated basket",exact=True)).to_be_visible()
    page.get_by_role("button",name="Run market scan",exact=True).click()
    expect(page.get_by_role("combobox",name="Saved market scan",exact=True)).to_have_value("ui-fixture-new")
    expect(page.get_by_role("button",name="Run market scan",exact=True)).to_be_enabled(timeout=30000)
    assert report["submitted"] == [dict(refresh=True, initial_cash_usd=0, initial_cash_cad=700)], report
    page.get_by_text("Inspect all 2 instruments",exact=True).click()
    expect(page.get_by_text("UI fixture benchmark",exact=True)).to_be_visible()
    for width,height in [(1440,1000),(768,1024),(390,844),(320,750)]:
        page.set_viewport_size(dict(width=width,height=height))
        for name in ["Scanner","Study","Research","Data","Experiments","Operations"]:
            page.get_by_role("button",name=name,exact=True).click()
            page.wait_for_load_state("networkidle")
            report["pages"].append(dict(page=name,width=width,overflow=page.evaluate("document.documentElement.scrollWidth > innerWidth")))
            if name == "Scanner":
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(root/f"scanner-{width}.png"))
    completed = next(run for run in page.request.get("http://127.0.0.1:8765/api/runs").json() if run["status"] == "COMPLETED")
    page.goto(f"http://127.0.0.1:8765/?study={completed['id']}",wait_until="networkidle")
    expect(page.get_by_role("heading",name="Research study",exact=True)).to_be_visible()
    expect(page.get_by_text("Saved study",exact=False).first).to_be_visible()
    report["deep_link_study"] = completed["id"]
    browser.close()
assert not report["errors"],report
assert not any(page["overflow"] for page in report["pages"]),report
(root/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))

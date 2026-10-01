"""Synthetic integration only: input clocks to two-head forecasts to all20 cash paths."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
for folder in (ROOT/"models",ROOT/"accounts",ROOT/"model-inputs"):
    sys.path.insert(0,str(folder))
from event_inputs import prepare_events, extract_labels
from earnings_models import fit_fold, predict_events, save_bundle, load_bundle
from account_adapter import run_account, RECIPES, COST_PROFILES
from frontier.historical_settlement import build_settlement_indices


def test_synthetic_inputs_models_and_twenty_cash_accounts(tmp_path):
    source=json.loads((ROOT.parent/"post-filing-strategy20260928/calendar.json").read_text())
    calendar={"sessions":[r for r in source["sessions"] if "2016-01-04" <= r["session"] <= "2021-01-29"]}
    days=[r["session"] for r in calendar["sessions"]]
    symbols=[f"S{i:02}" for i in range(25)]+["SPY"]
    shape=(len(days),len(symbols))
    market={"sessions":days,"symbols":symbols,"benchmark":25,"dates":np.array(days,dtype="datetime64[D]"),
            "close":np.full(shape,20.),"adjusted":np.full(shape,20.),"atr":np.full(shape,.25),
            "vendor_quote_close":np.full(shape,20.),"vendor_quote_volume":np.full(shape,1000000.),
            "settlement_index":build_settlement_indices(days,"USD")}
    cohort={"selected":[{"symbol":s,"cik":str(j+1).zfill(10)} for j,s in enumerate(symbols[:-1])]}
    events=[]
    for year,count,issuers in ((2017,256,25),(2020,64,16),(2021,3,3)):
        base=next(i for i,d in enumerate(days) if d[:4]==str(year))
        for n in range(count):
            j=n%issuers;e=base+10*(n//issuers);end=e+5
            day=days[e];decision=datetime.fromisoformat(day+"T09:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
            event={"symbol":symbols[j],"cik":str(j+1).zfill(10),"accession":f"synthetic-{year}-{n:04}",
                   "filing_date":days[e-1],"S":str(1.2+(n%5)*.1),"Q":"0.01",
                   "feature_status":"qualified","q_status":"qualified","joint_feature_status":"qualified",
                   "strategy_source_status":"qualified","execution_status":"qualified",
                   "decision_time":decision.isoformat(),"availability_floor":decision.replace(hour=1).isoformat(),
                   "entry_session":day,"exit_session":days[end],"entry_time":calendar["sessions"][e]["close"],
                   "exit_time":calendar["sessions"][end]["close"],"source_sha256":"synthetic-source"}
            events.append(event)
            for key in ("close","adjusted","vendor_quote_close"):
                market[key][e:end+1,j]=20*(1+.02*np.arange(6))
    prepared=prepare_events(market,events,cohort,calendar)["rows"]
    assert len(prepared)==323 and all(r["model_input_status"]=="qualified" for r in prepared)
    old=[r for r in prepared if r["entry_session"][:4] in ("2017","2020")]
    test=[r for r in prepared if r["entry_session"][:4]=="2021"]
    labels=extract_labels(market,old)
    assert len(labels)==320 and all(r["status"]=="qualified" for r in labels.values())
    fold={"fit_decision_years":[2017,2018,2019],"calibration_decision_year":2020,"test_decision_year":2021}
    bundles=fit_fold(prepared,labels,fold,days)
    predictions={}
    for family,bundle in bundles.items():
        assert bundle.available,bundle.audit
        predicted=predict_events(bundle,test)
        assert len(predicted["forecasts"])==3 and all(r["status"]=="predicted" for r in predicted["forecasts"])
        folder=tmp_path/family;save_bundle(bundle,folder)
        assert predict_events(load_bundle(folder),test)==predicted
        predictions[family]=predicted
    # Test labels are accessed only after both families' exact forecasts were retained/reloaded.
    test_labels=extract_labels(market,test)
    assert len(test_labels)==3
    reports=[];first=days.index("2020-12-31");last=len(days)-1
    for recipe in RECIPES:
        for capital in (10000,2000):
            for cost in COST_PROFILES:
                kwargs={}
                if recipe in predictions:
                    record=predictions[recipe]
                    kwargs={"forecasts":{r["event_id"]:r for r in record["forecasts"]},
                            "forecast_identity":hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()}
                report=run_account(market,prepared,recipe=recipe,cost_profile=cost,capital=capital,
                                   first=first,last=last,**kwargs)
                assert report["status"]=="complete"
                assert len(report["trade_records"])==3
                assert len(report["event_decisions"])==323
                assert report["synthetic_interval_override"] is True
                assert len(report["weekly_objective"]["targets"])==3
                assert not report["final_state"]["held"]
                for trade in report["trade_records"]:
                    assert trade["entry_notional"]+trade["entry_fee"] <= trade["reserved_cash"]+1e-7
                reports.append(report)
    assert len(reports)==20

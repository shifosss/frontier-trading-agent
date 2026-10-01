"""Independent post-run timing check; no Frontier financial imports."""
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert read(ROOT/"status.json")["phase"]=="complete"
    summary=read(ROOT/"summary.json")
    context=read(ROOT/"regime-context.json")
    sessions=[r["session"] for r in context["rows"]]
    position={s:i for i,s in enumerate(sessions)}
    cohorts=read(ROOT/"selected-cohorts.json")
    dates=defaultdict(dict)
    for cohort in cohorts:
        dates[cohort["policy"]][sessions[cohort["signal_index"]]]={"planned":len(cohort["selected"]),"values":[]}
    chosen={}
    outcomes_rows=0
    with (ROOT/"event-outcomes.csv").open(encoding="utf-8",newline="") as source:
        for row in csv.DictReader(source):
            outcomes_rows+=1
            key=(row["policy"],row["horizon"])
            identity="|".join(row[k] for k in ("policy","signal_session","symbol","horizon"))
            rank=hashlib.sha256(identity.encode()).hexdigest()
            if key not in chosen or rank<chosen[key][0]:
                chosen[key]=(rank,row)
            if row["horizon"]=="1":
                value=float(row["entry_intraday_log"]) if row["entry_intraday_log"] else None
                dates[row["policy"]][row["signal_session"]]["values"].append(value)
    maximum_aggregation_error=0.0
    for policy,by_date in dates.items():
        complete=[]
        valid=attempted=active=0
        for session,row in by_date.items():
            assert len(row["values"])==row["planned"]
            attempted+=row["planned"]
            active+=row["planned"]>0
            known=[v for v in row["values"] if v is not None]
            valid+=len(known)
            if row["planned"] and len(known)==row["planned"]:
                complete.append(math.fsum(known)/len(known))
        result=summary["primary"][policy]
        assert attempted==result["attempted_events"] and valid==result["valid_events"]
        assert len(complete)==result["complete_active_date_log"]["count"]
        assert active==result["selection"]["active_dates"]
        assert len(by_date)-active==result["selection"].get("no_selected_candidate_dates",0)
        if complete:
            for name,value in (("mean",math.fsum(complete)/len(complete)),("median",statistics.median(complete))):
                error=abs(value-result["complete_active_date_log"][name])
                maximum_aggregation_error=max(maximum_aggregation_error,error)
                assert error<1e-12
    records={r["symbol"]:r for r in read(REPO/"artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/capture-index.json")}
    source_cache={}
    maximum_log_error=maximum_simple_error=0.0
    audited=[]
    for _,row in chosen.values():
        symbol=row["symbol"]
        record=records[symbol]
        if symbol not in source_cache:
            path=REPO/"data/historical/capture-workspace"/record["path"]
            assert digest(path)==record["sha256"]
            item=read(path)["chart"]["result"][0]
            lookup={datetime.fromtimestamp(t,ZoneInfo("America/Toronto")).date().isoformat():i for i,t in enumerate(item["timestamp"])}
            source_cache[symbol]=(item,lookup)
        item,lookup=source_cache[symbol]
        quote=item["indicators"]["quote"][0]
        adj=item["indicators"]["adjclose"][0]["adjclose"]
        t=position[row["signal_session"]]
        e,x=t+1,t+1+int(row["horizon"])
        with localcontext() as ctx:
            ctx.prec=50
            def bar(index):
                raw=lookup[sessions[index]]
                c=Decimal(str(quote["close"][raw])); a=Decimal(str(adj[raw]))
                o=Decimal(str(quote["open"][raw]))
                return a,o*a/c,(c/o).ln()
            signal,entry,exit_=bar(t),bar(e),bar(x)
            logs=[(exit_[0]/entry[1]).ln(),(exit_[0]/entry[0]).ln(),(exit_[1]/entry[1]).ln()]
            log_fields=["next_open_same_exit_log","next_close_log","next_open_to_open_log"]
            simple_fields=["next_open_same_exit_simple","next_close_simple","next_open_to_open_simple"]
            for value,name in zip(logs,log_fields):
                error=abs(float(value)-float(row[name])); maximum_log_error=max(maximum_log_error,error)
                assert error<1e-12
            for value,name in zip(logs,simple_fields):
                expected=float(value.exp()-1)
                error=abs(expected-float(row[name])); maximum_simple_error=max(maximum_simple_error,error)
                assert error<1e-12+2e-12*abs(expected)
            for value,name in ((entry[2],"entry_intraday_log"),((entry[1]/signal[0]).ln(),"overnight_gap_log")):
                error=abs(float(value)-float(row[name])); maximum_log_error=max(maximum_log_error,error)
                assert error<1e-12
        audited.append({"policy":row["policy"],"horizon":int(row["horizon"]),"signal_session":row["signal_session"],"symbol":symbol,"source_sha256":record["sha256"]})
    result={"status":"passed","primary_policies_checked":len(dates),"all_event_horizon_csv_rows":outcomes_rows,
            "sampled_policy_horizon_cells":len(audited),"independent_raw_sources":len(source_cache),
            "maximum_primary_aggregation_error":maximum_aggregation_error,"maximum_decimal_log_error":maximum_log_error,
            "maximum_decimal_simple_return_error":maximum_simple_error,"sample":audited,
            "qualification":"Arithmetic validation of saved source observations,not source-action completeness or executable profitability."}
    (ROOT/"independent-audit.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="sample"},indent=2))

if __name__=="__main__":
    main()

"""Synthetic execution boundaries; these tests contain no economic study outcomes."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from hashlib import sha256

import numpy as np
import pytest

from account_adapter import event_rankings, run_account
from frontier.execution_costs import get_cost_profile
from frontier.historical_settlement import build_settlement_indices
from frontier.short_horizon_study import _simulate_daily

CALENDAR = json.loads((Path(__file__).parents[2] /
    "post-filing-strategy20260928/calendar.json").read_text())["sessions"]


def market(symbols=("A",), start="2024-06-03", end="2024-07-19"):
    sessions = [row["session"] for row in CALENDAR if start <= row["session"] <= end]
    shape = len(sessions), len(symbols)
    return {"symbols": list(symbols), "sessions": sessions,
            "dates": np.array(sessions, dtype="datetime64[D]"),
            "close": np.full(shape, 100.), "adjusted": np.full(shape, 100.),
            "atr": np.full(shape, 1.), "settlement_index": build_settlement_indices(sessions, "USD")}


def event(m, symbol="A", entry=1, score="2", q="0.02", accession=None):
    day = m["sessions"][entry]
    decision = datetime.fromisoformat(day+"T09:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
    accession = accession or f"synthetic-{symbol}-{day}"
    return {"symbol": symbol, "cik": "0000000001", "accession": accession, "event_id": accession,
            "filing_date": m["sessions"][entry-1], "feature_status": "qualified",
            "joint_feature_status": "qualified", "strategy_source_status": "qualified",
            "execution_status": "qualified", "model_input_status": "qualified",
            "model_inputs": [float(score), float(q), 0., 1., 0.],
            "S": score, "Q": q, "decision_time": decision.isoformat(),
            "decision_timestamp": decision.isoformat(), "availability_floor": decision.replace(hour=1).isoformat(),
            "entry_session": day, "exit_session": m["sessions"][entry+5],
            "prior_price_index": entry-1, "entry_index": entry, "planned_label_end_index": entry+5,
            "planned_label_end_session": m["sessions"][entry+5]}


def forecasts(events, mu=.05, downside=.01):
    return {e["event_id"]: {"event_id": e["event_id"], "status": "predicted",
             "raw": [mu, downside], "uncalibrated": [mu, downside],
             "corrected": [mu, downside], "reasons": []} for e in events}


def run(m, events, recipe="filing_control", profile="proportional_40bps", capital=2000, predictions=None):
    # Attach the same mandatory source metadata emitted by the model adapter to handwritten fixtures.
    predictions = deepcopy(predictions)
    by_id = {e["event_id"]: e for e in events}
    for key, record in (predictions or {}).items():
        event_row = by_id[key]
        record.setdefault("event_id", key)
        record.setdefault("cik", event_row["cik"])
        record.setdefault("prepared_row_sha256", sha256(json.dumps(
            event_row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())
    kwargs = {"forecasts": predictions, "forecast_identity": "full-five-fold-synthetic"} if recipe in (
        "ridge", "hist_gradient_boosting") else {}
    return run_account(m, events, recipe=recipe, cost_profile=profile, capital=capital,
                       first=0, last=len(m["sessions"])-1, **kwargs)


def test_second_idle_day_screens_and_positions_exit_independently():
    m = market(("A", "B"))
    report = run(m, [event(m, "A", entry=2), event(m, "B", entry=4)])
    assert report["status"] == "complete"
    assert [(t["entry_session"], t["exit_session"], t["holding_sessions"]) for t in report["trade_records"]] == [
        (m["sessions"][2], m["sessions"][7], 5), (m["sessions"][4], m["sessions"][9], 5)]
    assert len(report["daily_state"][7]["held"]) == 1
    assert report["intents"][0]["prior_price_session"] == m["sessions"][1]


@pytest.mark.parametrize("recipe", ["filing_control", "ridge"])
def test_upward_gap_cannot_spend_another_reservation(recipe):
    m=market(); e=event(m); m["close"][1:]=125.; m["adjusted"][1:]=125.
    report=run(m,[e],recipe,predictions=forecasts([e]) if recipe=="ridge" else None)
    intent, trade=report["intents"][0],report["trade_records"][0]
    assert intent["original_quantity"]==3
    assert intent["reserved_cash"]==pytest.approx(300.6)
    assert trade["quantity"]==2 and intent["reservation_capped_quantity"]==2
    assert trade["entry_notional"]+trade["entry_fee"] <= intent["reserved_cash"]


def test_downward_gap_never_increases_quantity():
    m=market();e=event(m);m["close"][1:]=50.;m["adjusted"][1:]=50.
    report=run(m,[e],"ridge",predictions=forecasts([e]))
    assert report["intents"][0]["original_quantity"]==report["trade_records"][0]["quantity"]==3


def test_year_boundary_does_not_reset_cash_or_flatten_existing_position():
    m=market(("A","B"),"2024-12-20","2025-01-24")
    late=m["sessions"].index("2024-12-30");new=m["sessions"].index("2025-01-02")
    events=[event(m,"A",late),event(m,"B",new)]
    predictions=forecasts(events);predictions[events[1]["event_id"]]={"status":"unavailable","reasons":["insufficient_fit"]}
    report=run(m,events,"ridge",predictions=predictions)
    assert report["trades"]==1 and report["trade_records"][0]["exit_session"]==m["sessions"][late+5]
    assert report["trade_records"][0]["exit_session"]>"2025-01-01"
    assert len(report["daily_state"][new]["held"])==1
    assert report["equity_curve"][new]["equity"]<2000
    assert report["event_decisions"][1]["status"]=="forecast_abstention"
    assert run(m,events)["trades"]==2


@pytest.mark.parametrize("missing",["entry","mark"])
def test_missing_future_price_invalidates_and_retains_prefix(missing):
    m=market();events=[event(m)]
    if missing=="entry":m["close"][1,0]=np.nan
    else:m["adjusted"][4,0]=np.nan
    report=run(m,events,"ridge",predictions=forecasts(events))
    assert report["status"]=="incomplete" and report["total_return"] is None
    assert len(report["intents"])==1 and report["event_decisions"][0]["status"]=="candidate"
    assert report["missing"][0].endswith(":"+missing)
    assert report["weekly_objective"]["status"]=="unavailable_for_incomplete_account"
    if missing=="mark":assert len(report["final_state"]["held"])==1


def test_cash_backing_rule_is_strict_and_control_population_is_shared():
    m=market(("A","B","C"))
    events=[event(m,"A",score="1",q="0"),event(m,"B",score=".9999999999999999999"),
            event(m,"C",score="1",q=".01")]
    assert run(m,events)["trades"]==3
    assert run(m,events,"income_surprise")["trades"]==2
    assert [t["symbol"] for t in run(m,events,"income_cash_confirmation")["trade_records"]]==["C"]
    events[2]["model_input_status"]="unavailable";events[2]["model_input_reasons"]=["price_history"]
    assert run(m,events,"income_cash_confirmation")["trades"]==0


def test_same_forecast_costs_change_utility_without_changing_forecast():
    m=market();events=[event(m)]; predictions=forecasts(events,mu=.01,downside=0)
    saved=deepcopy(predictions)
    prop=run(m,events,"ridge",predictions=predictions)
    broker=run(m,events,"ridge",profile="moomoo_ca_us_plus_40bps",predictions=predictions)
    assert prop["trades"]==1 and broker["trades"]==0 and predictions==saved
    decision=next(row for row in broker["policy_audit"] if row["phase"]=="full_selection")["decisions"][0]
    assert decision["reason"]=="nonpositive_utility" and decision["utility"]<0
    assert decision["event_id"]==events[0]["event_id"]


def test_fill_rechecks_original_forecast_without_reranking_or_replacement():
    m=market();events=[event(m)];m["close"][1:]=200.;m["adjusted"][1:]=200.
    report=run(m,events,"ridge",profile="moomoo_ca_us_plus_40bps",
               predictions=forecasts(events,mu=.02,downside=0))
    assert len(report["intents"])==1 and report["trades"]==0
    intent=report["intents"][0]
    assert intent["reference_projection"]["utility"]>0
    assert intent["fill_check"]["reason"]=="nonpositive_utility"
    assert intent["fill_check"]["original_quantity"]==3
    assert intent["fill_check"]["quantity"]==1
    assert intent["fill_check"]["projection"]["mu"]==.02


def test_sale_proceeds_wait_for_historical_settlement():
    m=market(("A","B","C","D","E","F"))
    m["close"][:,:5]=1.;m["adjusted"][:,:5]=1.;m["atr"][:,:5]=.001
    events=[event(m,s) for s in m["symbols"][:5]]+[event(m,"F",6),event(m,"F",7)]
    report=run(m,events)
    later=[t for t in report["trade_records"] if t["symbol"]=="F"]
    assert len(later)==1 and later[0]["entry_session"]==m["sessions"][7]
    assert report["equity_curve"][6]["settled_cash"]<100
    assert report["equity_curve"][6]["unsettled_cash"]>1900


def test_duplicate_same_issuer_decision_is_explicit_not_overwritten():
    m=market();events=[event(m),event(m,accession="second-original")]
    with pytest.raises(ValueError,match="collision"):run(m,events)


def test_decision_year_not_filing_year_defines_entry_period():
    m=market(start="2025-12-22",end="2026-01-23")
    e=event(m,entry=m["sessions"].index("2026-01-02"));e["filing_date"]="2025-12-31"
    report=run(m,[e])
    assert report["trades"]==0 and report["event_decisions"][0]["status"]=="outside_entry_period"


def test_invalid_and_missing_forecasts_abstain_but_controls_continue():
    m=market(("A","B"));events=[event(m,"A"),event(m,"B")]
    report=run(m,events,"ridge",predictions={events[0]["event_id"]:{"status":"predicted","corrected":[-1,0]}})
    assert report["trades"]==0 and len(report["event_decisions"])==2
    assert [e["reasons"] for e in report["event_decisions"]]==[["invalid_forecast"],["missing_forecast"]]
    assert run(m,events)["trades"]==2


def test_shared_engine_cash_curve_is_unchanged_without_binding_reservation():
    m=market();events=[event(m),event(m,entry=12)]
    rank,counts,_,_=event_rankings(m,events,"filing_control")
    direct=_simulate_daily(m,"filing_control",5,2000,40,0,len(m["sessions"])-1,audit=True,
                           signal_ranking=rank,signal_counts=counts,cost_model=get_cost_profile("proportional",40))
    adapted=run(m,events)
    np.testing.assert_allclose([r["equity"] for r in adapted["equity_curve"]],direct["equity"],rtol=0,atol=1e-10)


def test_missing_source_qualification_cannot_be_relaxed_for_a_recipe():
    m=market();e=event(m);e["strategy_source_status"]="unavailable"
    with pytest.raises(ValueError,match="source qualification"):run(m,[e])


def test_weekly_target_denominator_keeps_idle_and_losing_weeks():
    m=market(); report=run(m,[event(m)])
    weeks=report["period_returns"]["weekly"]; target=report["weekly_objective"]
    assert any(row["return"]==0 for row in weeks) and any(row["return"]<0 for row in weeks)
    assert target["count"]==len(weeks)
    assert all(value["hits"]==0 and value["denominator"]==len(weeks) for value in target["targets"].values())
    assert target["longest_losing_streak"]==2


def test_information_after_nine_is_not_traded():
    m=market();e=event(m)
    e["availability_floor"]=(datetime.fromisoformat(e["decision_timestamp"])+timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError,match="public availability"):run(m,[e])


def test_default_evaluation_keeps_all_idle_years_and_tail():
    m=market(start="2020-12-31",end="2026-01-16")
    report=run_account(m,[],recipe="filing_control",cost_profile="proportional_40bps")
    assert report["status"]=="complete" and report["trades"]==0
    assert report["equity_curve"][0]["session"]=="2020-12-31"
    assert report["equity_curve"][-1]["session"]=="2026-01-16"
    assert report["weekly_objective"]["count"]>260
    assert report["synthetic_interval_override"] is False


def test_large_drawdown_is_reported_without_inventing_an_entry_halt():
    m=market(("A","B","C","D","E","F"))
    m["close"][:,:5]=1.;m["adjusted"][:,:5]=1.;m["atr"][:,:5]=.001
    m["close"][2:,:5]=.4;m["adjusted"][2:,:5]=.4
    events=[event(m,s) for s in m["symbols"][:5]]+[event(m,"F",7)]
    report=run(m,events)
    assert report["status"]=="complete" and report["trades"]==6
    assert any(t["symbol"]=="F" for t in report["trade_records"])
    assert min(p["equity"] for p in report["equity_curve"])<2000*.7
    assert report["drawdown_interpretation"]=="30% qualification limit; no automatic drawdown halt"


def test_unavailable_forecast_reasons_remain_specific():
    m=market();events=[event(m)]
    predictions={events[0]["event_id"]:{"status":"unavailable","reasons":["insufficient_fit","insufficient_issuers"]}}
    report=run(m,events,"ridge",predictions=predictions)
    assert report["event_decisions"][0]["reasons"]==["insufficient_fit","insufficient_issuers"]


def test_malformed_model_numbers_abstain_instead_of_entering():
    m=market();events=[event(m)]
    predictions={events[0]["event_id"]:{"status":"predicted","corrected":["invalid",0]}}
    report=run(m,events,"ridge",predictions=predictions)
    assert report["trades"]==0
    assert report["event_decisions"][0]["reasons"]==["invalid_forecast"]


def test_week_straddling_entry_period_and_tail_is_labelled_both():
    m=market(start="2025-12-22",end="2026-01-16")
    report=run(m,[])
    weeks=report["period_returns"]["weekly"]
    mixed=[row for row in weeks if row["interval_role"]=="mixed"]
    assert len(mixed)==1
    assert mixed[0]["interval_roles"]==["entry_period","liquidation_tail"]


def test_missing_decision_retains_clock_failure_instead_of_outside_period():
    m=market();e=event(m);e["decision_timestamp"]=None;e["decision_time"]=None
    e["model_input_status"]="unavailable";e["model_input_reasons"]=["missing_public_clock"]
    report=run(m,[e])
    assert report["event_decisions"][0]["status"]=="unavailable"
    assert report["event_decisions"][0]["reasons"]==["missing_decision_timestamp","missing_public_clock"]


def test_prepared_row_digest_binds_unselected_fields_and_original_source_clocks():
    m=market();e=event(m)
    e.update(registry_acceptance_utc="2024-06-03T22:00:00+00:00",
             acceptance_et="2024-06-03T18:00:00-04:00",source_sha256="original-source-identity",
             arbitrary_preserved_history=["original-1","original-2"])
    first=run(m,[e]);changed=deepcopy(e);changed["arbitrary_preserved_history"][0]="changed"
    second=run(m,[changed])
    assert first["event_decisions"][0]["prepared_event_sha256"] != second["event_decisions"][0]["prepared_event_sha256"]
    for key in ("registry_acceptance_utc","acceptance_et","source_sha256"):
        assert first["intents"][0][key]==e[key]
        assert first["trade_records"][0][key]==e[key]


@pytest.mark.parametrize("field,value", [
    ("event_id","another-original"), ("cik","0000000009"), ("prepared_row_sha256","wrong-source-row")])
def test_misbound_forecast_cannot_trade_another_event(field,value):
    m=market();events=[event(m)];prediction=forecasts(events)
    prediction[events[0]["event_id"]][field]=value
    with pytest.raises(ValueError,match="Forecast identity"):
        run(m,events,"ridge",predictions=prediction)


def test_absent_forecast_source_binding_is_refused():
    m=market();events=[event(m)]
    with pytest.raises(ValueError,match="Forecast identity"):
        run_account(m,events,recipe="ridge",cost_profile="proportional_40bps",
                    capital=2000,forecasts=forecasts(events),forecast_identity="unbound",
                    first=0,last=len(m["sessions"])-1)

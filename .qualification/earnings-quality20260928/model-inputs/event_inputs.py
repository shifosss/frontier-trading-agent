"""Five causal filing inputs; future price labels are an explicitly separate call."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import numpy as np

FEATURE_NAMES = ["S", "Q", "prior_relative_return_5", "prior_dollar_activity_ratio_20",
                 "prior_spy_sma200_distance"]


def _positive(values):
    return bool(np.isfinite(values).all() and (values > 0).all())


def prepare_events(market, events, cohort, calendar):
    """Keep every original event and field; append eligibility using only p or earlier."""
    sessions, symbols = market["sessions"], market["symbols"]
    if sessions != [row["session"] for row in calendar["sessions"]]:
        raise ValueError("Market and official calendar session identities differ")
    if len(set(sessions)) != len(sessions) or sessions != sorted(sessions):
        raise ValueError("Session order must be strictly increasing")
    if len(set(symbols)) != len(symbols) or symbols[market["benchmark"]] != "SPY":
        raise ValueError("Distinct symbols and an explicit SPY benchmark required")
    expected = {row["symbol"]: row["cik"] for row in cohort["selected"]}
    if len(expected) != len(cohort["selected"]) or len(set(expected.values())) != len(expected):
        raise ValueError("Cohort symbol/CIK identities must be unique")
    shape = (len(sessions), len(symbols))
    for key in ("adjusted", "vendor_quote_close", "vendor_quote_volume"):
        if market[key].shape != shape:
            raise ValueError("Market array shape differs: " + key)
    session_index = {day: i for i, day in enumerate(sessions)}
    symbol_index = {symbol: j for j, symbol in enumerate(symbols)}
    benchmark = market["benchmark"]
    seen, output = set(), []
    for event in events:
        symbol, cik, accession = event["symbol"], event["cik"], event["accession"]
        if expected.get(symbol) != cik:
            raise ValueError("Event is outside the fixed symbol/CIK cohort")
        event_id = cik + ":" + accession
        if event_id in seen:
            raise ValueError("Duplicate original event identity: " + event_id)
        seen.add(event_id)
        row = dict(event)
        reasons, values = [], [None] * 5
        row.update(event_id=event_id, decision_timestamp=event.get("decision_time"),
                   prior_price_index=None, entry_index=None, planned_label_end_index=None,
                   planned_label_end_session=event.get("exit_session"))
        for key in ("feature_status", "q_status", "execution_status", "strategy_source_status"):
            if event.get(key) != "qualified":
                reasons.append(key + ":" + str(event.get(key, "unavailable")))
        for k, key in enumerate(("S", "Q")):
            try:
                value = Decimal(str(event.get(key)))
                number = float(value)
                if not value.is_finite() or not np.isfinite(number):
                    raise ValueError("Nonfinite numeric feature")
                values[k] = number
            except (InvalidOperation, ValueError, OverflowError):
                reasons.append(key + ":unavailable_or_nonfinite")
        entry = session_index.get(event.get("entry_session"))
        clock_ok = event.get("execution_status") == "qualified"
        if clock_ok:
            try:
                decision = datetime.fromisoformat(event["decision_time"])
                floor = datetime.fromisoformat(event["availability_floor"])
                if decision.tzinfo is None or floor.tzinfo is None or decision < floor:
                    raise ValueError("Invalid availability clock")
                local = decision.astimezone(ZoneInfo("America/New_York"))
                if (local.hour, local.minute, local.second, local.microsecond) != (9, 0, 0, 0):
                    raise ValueError("Decision is not at09:00ET")
                if entry is None or entry < 1 or entry + 5 >= len(sessions):
                    raise ValueError("Scheduled entry/exit is outside the calendar")
                if local.date().isoformat() != sessions[entry] or event["exit_session"] != sessions[entry+5]:
                    raise ValueError("Event entry/exit differs from five-session schedule")
                for key, index in (("entry_time", entry), ("exit_time", entry+5)):
                    if datetime.fromisoformat(event[key]) != datetime.fromisoformat(calendar["sessions"][index]["close"]):
                        raise ValueError("Scheduled fill differs from the official close")
            except (KeyError, TypeError, ValueError):
                reasons.append("execution_clock:inconsistent")
                clock_ok = False
        if clock_ok:
            p = entry - 1
            row.update(prior_price_index=p, entry_index=entry, planned_label_end_index=entry+5,
                       planned_label_end_session=sessions[entry+5])
            j = symbol_index.get(symbol)
            if j is None:
                reasons.append("price_symbol:unavailable")
            else:
                if p < 5:
                    reasons.append("prior_relative_return_5:insufficient_history")
                else:
                    stock = market["adjusted"][p-5:p+1, j]
                    spy = market["adjusted"][p-5:p+1, benchmark]
                    if _positive(stock) and _positive(spy):
                        values[2] = float(stock[-1]/stock[0] - spy[-1]/spy[0])
                    else:
                        reasons.append("prior_relative_return_5:missing_or_invalid_close")
                if p < 20:
                    reasons.append("prior_dollar_activity_ratio_20:insufficient_history")
                else:
                    close = market["vendor_quote_close"][p-20:p+1, j]
                    volume = market["vendor_quote_volume"][p-20:p+1, j]
                    with np.errstate(over="ignore", invalid="ignore"):
                        activity = close * volume
                    if (_positive(close) and np.isfinite(volume).all() and (volume >= 0).all()
                            and np.isfinite(activity).all() and np.median(activity[:-1]) > 0):
                        values[3] = float(activity[-1]/np.median(activity[:-1]))
                    else:
                        reasons.append("prior_dollar_activity_ratio_20:missing_or_invalid_activity")
            if p < 199:
                reasons.append("prior_spy_sma200_distance:insufficient_history")
            else:
                spy = market["adjusted"][p-199:p+1, benchmark]
                if _positive(spy):
                    values[4] = float(spy[-1]/spy.mean() - 1)
                else:
                    reasons.append("prior_spy_sma200_distance:missing_or_invalid_close")
        if any(value is None or not np.isfinite(value) for value in values):
            reasons.append("five_finite_inputs:unavailable")
        row.update(model_inputs=values, model_input_status="unavailable" if reasons else "qualified",
                   model_input_reasons=reasons)
        output.append(row)
    output.sort(key=lambda row: (row.get("decision_timestamp") or "", row["cik"], row["accession"]))
    return {"feature_names": FEATURE_NAMES, "rows": output}


def extract_labels(market, rows):
    """Call separately for explicitly selected fit/cal rows, or after test forecasts persist."""
    labels = {}
    for row in rows:
        entry, end = row.get("entry_index"), row.get("planned_label_end_index")
        reasons, targets = [], None
        if entry is None or end != entry + 5 or row["symbol"] not in market["symbols"]:
            reasons.append("scheduled_label_interval:unavailable")
        else:
            j = market["symbols"].index(row["symbol"])
            prices = market["adjusted"][entry:end+1, j]
            if len(prices) != 6 or not _positive(prices):
                reasons.append("label_closes:missing_or_invalid")
            else:
                moves = prices[1:]/prices[0] - 1
                targets = [float(moves[-1]), float(max(0, -moves.min()))]
        labels[row["event_id"]] = {"status": "unavailable" if reasons else "qualified",
                                  "targets": targets, "reasons": reasons,
                                  "entry_session": row.get("entry_session"),
                                  "label_end_session": row.get("planned_label_end_session")}
    return labels

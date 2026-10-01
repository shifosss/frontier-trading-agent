"""Unfunded filing-event descriptions; never selects or changes an account order."""
from collections import Counter, defaultdict
from math import isfinite
from statistics import fmean

METRICS = ("stock_gross_return", "benchmark_gross_return", "stock_minus_benchmark")


def summarize(rows):
    matched = [r for r in rows if r["status"] == "matched"]
    dates = defaultdict(list)
    for row in matched:
        dates[row["entry_session"]].append(row)
    return {
        "eligible_events": len(rows), "matched_events": len(matched),
        "unmatched_events": len(rows) - len(matched), "matched_entry_dates": len(dates),
        "available_stock_returns": sum(r["stock_gross_return"] is not None for r in rows),
        "available_benchmark_returns": sum(r["benchmark_gross_return"] is not None for r in rows),
        "unavailable_endpoint_counts": dict(Counter(p for r in rows for p in r["unavailable_endpoints"])),
        "identity_issue_counts": dict(Counter(p for r in rows for p in r["identity_issues"])),
        "equal_event_mean": {key: fmean(r[key] for r in matched) if matched else None for key in METRICS},
        "equal_entry_date_mean": {
            key: fmean(fmean(r[key] for r in group) for group in dates.values()) if dates else None
            for key in METRICS
        },
    }


def build_event_reference(market, events):
    sessions = {str(s): i for i, s in enumerate(market["sessions"])}
    symbols = {str(s): i for i, s in enumerate(market["symbols"])}
    benchmark = market["benchmark"]
    prices = market["adjusted"]
    if (len(sessions) != len(market["sessions"]) or len(symbols) != len(market["symbols"])
            or prices.shape != (len(sessions), len(symbols)) or not 0 <= benchmark < len(symbols)):
        raise ValueError("Market identities, benchmark or price shape do not agree")

    def price(session_index, symbol_index):
        if session_index is None or symbol_index is None:
            return None
        value = float(prices[session_index, symbol_index])
        return value if isfinite(value) and value > 0 else None

    rows, exclusions = [], []
    in_period = 0
    for number, event in enumerate(events):
        filing = event.get("filing_date") or ""
        reason = None
        if not "2017-01-01" <= filing <= "2025-12-31":
            reason = "filing_date_outside_2017_2025_or_missing"
        else:
            in_period += 1
            if event.get("feature_status") != "qualified":
                reason = "feature_not_qualified"
            elif event.get("execution_status") != "qualified":
                reason = "execution_not_qualified"
        identity = {"input_row": number, "symbol": event.get("symbol"), "accession": event.get("accession"),
                    "filing_date": filing}
        if reason:
            exclusions.append(dict(identity, reason=reason))
            continue
        # This population is fixed before looking at any outcome endpoint.
        entry, exit_ = event.get("entry_session"), event.get("exit_session")
        first, last, column = sessions.get(entry), sessions.get(exit_), symbols.get(event["symbol"])
        issues = []
        if first is None:
            issues.append("entry_session_missing")
        if last is None:
            issues.append("exit_session_missing")
        if column is None:
            issues.append("stock_symbol_missing")
        if first is not None and last is not None and last - first != 5:
            issues.append("not_five_market_sessions")
        endpoints = {"stock_entry": price(first, column), "stock_exit": price(last, column),
                     "benchmark_entry": price(first, benchmark), "benchmark_exit": price(last, benchmark)}
        unavailable = [key for key, value in endpoints.items() if value is None]
        stock = reference = None
        if not issues:
            if endpoints["stock_entry"] is not None and endpoints["stock_exit"] is not None:
                stock = endpoints["stock_exit"] / endpoints["stock_entry"] - 1
            if endpoints["benchmark_entry"] is not None and endpoints["benchmark_exit"] is not None:
                reference = endpoints["benchmark_exit"] / endpoints["benchmark_entry"] - 1
        excess = stock - reference if stock is not None and reference is not None else None
        rows.append({**identity, "selected": event.get("selected") is True,
                     "entry_session": entry, "exit_session": exit_, "holding_sessions": 5,
                     "entry_year": entry[:4] if entry else "unavailable", "adjusted_endpoints": endpoints,
                     "identity_issues": issues, "unavailable_endpoints": unavailable,
                     "status": "matched" if excess is not None else "unavailable",
                     "stock_gross_return": stock, "benchmark_gross_return": reference,
                     "stock_minus_benchmark": excess})

    selected = [r for r in rows if r["selected"]]
    matched_selected = [r for r in selected if r["status"] == "matched"]
    issuer_count = len({r["symbol"] for r in matched_selected})
    year_count = len({r["entry_year"] for r in matched_selected})
    gates = []
    if len(matched_selected) < 30:
        gates.append("fewer_than_30_matched_selected_events")
    if issuer_count < 4:
        gates.append("fewer_than_4_matched_selected_issuers")
    if year_count < 5:
        gates.append("fewer_than_5_matched_selected_entry_years")

    def groups(field):
        grouped = defaultdict(list)
        for row in rows:
            grouped[row[field]].append(row)
        return {key: {"all_eligible": summarize(group), "selected": summarize([r for r in group if r["selected"]])}
                for key, group in sorted(grouped.items())}

    return {
        "kind": "unfunded_descriptive_event_reference", "benchmark_symbol": market["symbols"][benchmark],
        "return_convention": "Adjusted close-to-close gross returns over five market sessions; stock minus simultaneous benchmark return",
        "aggregation": "Both mean conventions use stock/benchmark matched events only. Equal-event weights every event equally; equal-entry-date first averages each date's matched events, then gives each observed date equal weight.",
        "scope_counts": {"input_events": len(events), "filed_in_2017_2025": in_period,
                         "outside_filing_period": len(events) - in_period, "structurally_eligible": len(rows),
                         "structurally_ineligible_in_period": in_period - len(rows)},
        "rows": rows, "exclusions": exclusions, "all_eligible": summarize(rows), "selected": summarize(selected),
        "by_issuer": groups("symbol"), "by_entry_year": groups("entry_year"),
        "sample_support": {"matched_selected_events": len(matched_selected),
                           "matched_selected_issuers": issuer_count, "matched_selected_entry_years": year_count,
                           "failed_gates": gates, "sufficient_descriptive_sample": not gates,
                           "establishes_profitability": False},
        "limitations": ["No costs, share quantities, cash constraints, tax or portfolio equity are included.",
                        "Overlapping events and current surviving issuers are not independent or representative trials.",
                        "Adjusted-source returns do not establish corporate-action completeness or executable fills.",
                        "Missing future endpoints remain in eligibility counts and never alter candidate selection."]}

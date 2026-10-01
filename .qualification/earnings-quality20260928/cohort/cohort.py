"""Source-only cohort construction; no financial-fact or strategy-outcome inputs."""
import argparse
import hashlib
import json
import math
import re
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
COMMON = re.compile(r"\bcommon\s+(?:stock|shares?)\b", re.I)
EXCLUDED = re.compile(r"\b(?:adr|ads|depositary|depository|preferred|units?|warrants?|rights?|fund|funds|reit|etf|etn|notes?|bonds?)\b|\bshares? of beneficial interest\b", re.I)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cik10(value):
    text = str(value)
    if not text.isdigit() or len(text) > 10 or int(text) == 0:
        raise ValueError("Invalid CIK")
    return text.zfill(10)


def title_reason(spec):
    if spec.get("currency") != "USD" or spec.get("asset_type") != "stock":
        return "outside_usd_stock_listing"
    if spec.get("is_test") is not False or spec.get("is_etf") is not False or spec.get("next_shares") is not False:
        return "excluded_or_unresolved_exchange_flags"
    title = spec.get("name", "")
    if EXCLUDED.search(title):
        return "security_title_excluded"
    if not COMMON.search(title):
        return "common_share_title_not_explicit"
    return None


def liquidity_2016(payload, symbol, calendar):
    result = payload["chart"]["result"][0]
    if result["meta"].get("symbol") != symbol or result["meta"].get("currency") != "USD":
        raise ValueError("Source symbol/currency differs from declared security")
    sessions = set(calendar)
    quote = result["indicators"]["quote"][0]
    observed, seen, duplicates, outside = {}, set(), set(), set()
    for i, timestamp in enumerate(result["timestamp"]):
        day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if not day.startswith("2016-"):
            continue
        if day not in sessions:
            outside.add(day)
            continue
        if day in seen:
            duplicates.add(day)
        seen.add(day)
        close = quote["close"][i] if i < len(quote["close"]) else None
        volume = quote["volume"][i] if i < len(quote["volume"]) else None
        if not isinstance(close, (int, float)) or not isinstance(volume, (int, float)):
            continue
        if not math.isfinite(close) or close <= 0 or not math.isfinite(volume) or volume < 0:
            continue
        activity = close * volume
        if math.isfinite(activity):
            observed[day] = activity
    return {"status": "invalid_duplicate_session" if duplicates else "usable",
            "observations": len(observed), "calendar_sessions": len(sessions),
            "median_dollar_activity": statistics.median(observed.values()) if observed else None,
            "unavailable_sessions": sorted(sessions - observed.keys()),
            "duplicate_sessions": sorted(duplicates), "noncalendar_2016_sessions": sorted(outside)}


def make_screening_pool(instruments, ticker_exchange, liquidity, rules):
    mapping = defaultdict(list)
    for row_number, values in enumerate(ticker_exchange["data"]):
        row = dict(zip(ticker_exchange["fields"], values, strict=True))
        mapping[row["ticker"]].append({**row, "cik": cik10(row["cik"]), "source_row": row_number})
    requested, excluded, candidates = [], [], []
    for spec in instruments:
        if spec.get("currency") != "USD" or spec.get("asset_type") != "stock":
            continue
        symbol = spec["symbol"]
        requested.append(symbol)
        reason = title_reason(spec)
        matches = mapping.get(symbol, [])
        ciks = {m["cik"] for m in matches}
        metric = liquidity.get(symbol, {})
        if not reason and not ciks:
            reason = "exact_cik_mapping_absent"
        if not reason and len(ciks) != 1:
            reason = "ambiguous_cik_mapping"
        if not reason and metric.get("status") != "usable":
            reason = "liquidity_source_unavailable_or_invalid"
        if not reason and metric["observations"] < rules["minimum_observations"]:
            reason = "insufficient_2016_observations"
        if not reason and metric["median_dollar_activity"] < rules["minimum_median_dollar_activity"]:
            reason = "below_2016_liquidity_threshold"
        if reason:
            excluded.append({"symbol": symbol, "reason": reason, "listing": spec,
                             "exact_mapping_rows": matches, "liquidity": metric})
            continue
        cik = next(iter(ciks))
        candidates.append({"cik": cik, "symbol": symbol, "listing": spec, "liquidity": metric,
                           "exact_mapping_rows": matches,
                           "selection_hash": hashlib.sha256((rules["hash_seed"] + cik).encode("utf-8")).hexdigest()})
    if len(requested) != len(set(requested)):
        raise ValueError("Duplicate requested listing symbols")
    grouped = defaultdict(list)
    for row in candidates:
        grouped[row["cik"]].append(row)
    representatives = []
    for rows in grouped.values():
        ranked = sorted(rows, key=lambda r: (-r["liquidity"]["median_dollar_activity"], r["symbol"]))
        representatives.append(ranked[0])
        excluded.extend({**r, "reason": "another_qualifying_share_class_selected"} for r in ranked[1:])
    ranked = sorted(representatives, key=lambda r: (r["selection_hash"], r["cik"]))
    limit = rules["discovery_pool_limit"]
    excluded.extend({**r, "reason": "outside_frozen_discovery_pool"} for r in ranked[limit:])
    return {"kind": "current_member_source_classification_pool", "requested_symbols": requested,
            "requested_count": len(requested), "liquid_unique_ciks": len(ranked),
            "members": ranked[:limit], "excluded": sorted(excluded, key=lambda r: r["symbol"]),
            "exclusion_counts": dict(Counter(r["reason"] for r in excluded)),
            "discovery_pool_refilled": False, "financial_facts_or_returns_used": False}


def profile_reasons(member, profile):
    if profile is None:
        return ["submissions_profile_unavailable"]
    reasons = []
    try:
        if cik10(profile.get("cik")) != member["cik"]:
            reasons.append("submissions_cik_mismatch")
    except ValueError:
        reasons.append("submissions_cik_missing_or_invalid")
    if member["symbol"] not in profile.get("tickers", []):
        reasons.append("exact_ticker_missing_from_submissions")
    if profile.get("entityType") != "operating":
        reasons.append("entity_not_operating")
    if profile.get("stateOfIncorporation") not in STATES:
        reasons.append("incorporation_not_50_states_or_dc")
    sic = str(profile.get("sic", ""))
    if not sic.isdigit() or len(sic) > 4:
        reasons.append("sic_missing_or_invalid")
    elif not (100 <= int(sic) <= 5999 or 7000 <= int(sic) <= 8999):
        reasons.append("sic_outside_declared_operating_ranges")
    return reasons


def qualify_pool(pool, profiles, rules):
    classified, qualified = [], []
    for member in pool["members"]:
        profile = profiles.get(member["cik"])
        reasons = profile_reasons(member, profile)
        classified.append({"cik": member["cik"], "symbol": member["symbol"], "reasons": reasons,
                           "current_metadata": None if profile is None else {k: profile.get(k) for k in
                           ("cik", "entityType", "sic", "sicDescription", "stateOfIncorporation", "stateOfIncorporationDescription", "tickers")}})
        if not reasons:
            qualified.append(member)
    selected = qualified[:rules["target_issuers"]]
    return {"status": "ready_for_cohort_freeze" if len(selected) == rules["target_issuers"] else "insufficient_qualified_issuers",
            "selected": selected, "classification": classified, "qualified_count": len(qualified),
            "discovery_pool_refilled": False, "classification_vintage": "current source capture, not historical eligibility"}


def verify_inputs(inputs):
    for name, expected in inputs.items():
        if sha(REPO / name) != expected:
            raise ValueError("Frozen input changed: " + name)


def write_new(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def run_pool(definition_path):
    definition_path = Path(definition_path).resolve()
    definition_hash = sha(definition_path)
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    inputs = definition["inputs"]
    paths = definition["paths"]
    required = {str(Path(__file__).relative_to(REPO)).replace("\\", "/"),
                str(HERE.joinpath("test_cohort.py").relative_to(REPO)).replace("\\", "/"),
                *[paths[k] for k in ("criteria", "listing", "capture_index", "calendar", "ticker_exchange")]}
    if required - inputs.keys():
        raise ValueError("Definition omits required frozen cohort inputs")
    verify_inputs(inputs)
    completion = HERE / "pool-completion.json"
    if completion.exists():
        saved = json.loads(completion.read_text())
        if saved["definition_sha256"] != definition_hash:
            raise ValueError("Existing pool belongs to a different definition")
        verify_inputs(saved["outputs"])
        print(json.dumps({"status": "reused", **saved}), flush=True)
        return
    attempt = HERE / "attempts" / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    write_new(attempt / "attempt.json", {"definition_sha256": definition_hash, "paths": paths, "inputs": inputs})
    rules = json.loads((REPO / paths["criteria"]).read_text())
    listing = json.loads((REPO / paths["listing"]).read_text())["instruments"]
    index = json.loads((REPO / paths["capture_index"]).read_text())
    records = {r["symbol"]: r for r in index}
    if len(records) != len(index):
        raise ValueError("Frozen capture index has duplicate symbols")
    calendar_data = json.loads((REPO / paths["calendar"]).read_text())
    calendar_rows = calendar_data["sessions"] if isinstance(calendar_data, dict) else calendar_data
    calendar = [r["session"] if isinstance(r, dict) else r for r in calendar_rows]
    calendar = [d for d in calendar if d.startswith("2016-")]
    if len(calendar) != 252 or len(set(calendar)) != 252:
        raise ValueError("Frozen 2016 US calendar differs from the declared 252 sessions")
    liquidity, source_inputs = {}, dict(inputs)
    selected_specs = [s for s in listing if title_reason(s) is None]
    try:
        for number, spec in enumerate(selected_specs, 1):
            symbol = spec["symbol"]
            record = records.get(symbol)
            if record is None:
                liquidity[symbol] = {"status": "frozen_capture_record_absent"}
                continue
            raw = (REPO / paths["capture_workspace"] / record["path"]).resolve()
            workspace = (REPO / paths["capture_workspace"]).resolve()
            if not raw.is_relative_to(workspace):
                raise ValueError("Raw source escapes declared capture workspace")
            if not raw.exists():
                liquidity[symbol] = {"status": "frozen_raw_file_absent", "raw_path": str(raw), "expected_sha256": record["sha256"]}
                continue
            if sha(raw) != record["sha256"]:
                raise ValueError("Frozen raw source hash changed: " + symbol)
            relative = raw.relative_to(REPO).as_posix()
            source_inputs[relative] = record["sha256"]
            try:
                metric = liquidity_2016(json.loads(raw.read_text()), symbol, calendar)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                metric = {"status": "raw_source_unusable", "error": type(exc).__name__ + ": " + str(exc)}
            liquidity[symbol] = {**metric, "raw_path": relative, "sha256": record["sha256"],
                                 "captured_at": record["captured_at"], "url": record["url"]}
            if number % 250 == 0:
                print(json.dumps({"phase": "liquidity_2016", "processed": number, "requested": len(selected_specs)}), flush=True)
        mapping = json.loads((REPO / paths["ticker_exchange"]).read_text())
        pool = make_screening_pool(listing, mapping, liquidity, rules)
        verify_inputs(source_inputs)
        if sha(definition_path) != definition_hash:
            raise ValueError("Cohort definition changed during generation")
        for name, value in [("liquidity.json", liquidity), ("pool.json", pool), ("source-inputs.json", source_inputs)]:
            write_new(attempt / name, value)
        outputs = {p.relative_to(REPO).as_posix(): sha(p) for p in attempt.glob("*.json")}
        result = {"status": "classification_pool_complete", "definition_sha256": definition_hash,
                  "attempt": attempt.relative_to(REPO).as_posix(), "members": len(pool["members"]),
                  "requested_symbols": pool["requested_count"], "liquid_unique_ciks": pool["liquid_unique_ciks"],
                  "exclusion_counts": pool["exclusion_counts"], "outputs": outputs,
                  "network_requests": 0, "financial_facts_or_returns_used": False}
        write_new(completion, result)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        write_new(attempt / "failure.json", {"type": type(exc).__name__, "error": str(exc), "definition_sha256": definition_hash})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", required=True)
    run_pool(parser.parse_args().definition)

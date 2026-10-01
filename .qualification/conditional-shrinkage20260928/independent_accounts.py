"""Independent six-account ledger checks; no fitting, replay or live status reads."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.with_name("conditional-selection20260928")
REPO = ROOT.parents[1]
spec = importlib.util.spec_from_file_location("original_independent_accounts", SOURCE / "independent_accounts.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
read, sha = original.read, original.sha


def main():
    definition = read(ROOT / "definition.json")
    definition_sha = sha(ROOT / "definition.json")
    request = read(ROOT / "request.json")
    assert sha(ROOT / "request.json") == definition["request_sha256"]
    source_definition_sha = sha(SOURCE / "definition.json")
    assert definition["original_definition_sha256"] == source_definition_sha
    for group in ("files", "inputs"):
        for name, expected in definition[group].items():
            assert sha(REPO / name) == expected, name
    for name, expected in read(SOURCE / "definition.json")["files"].items():
        assert sha(REPO / name) == expected, name
    assert request["capital_usd"] == 2000 and request["round_trip_bps"] == 40
    assert request["holding_sessions"] == [1, 3, 5]
    assert set(request["cost_profiles"]) == {"proportional", "moomoo_ca_us"}
    names = [f"conditional_shrinkage_dollars-{hold}-{profile}.json" for hold in request["holding_sessions"] for profile in request["cost_profiles"]]
    paths = sorted((ROOT / "account-manifests").glob("*.json"))
    assert {p.name for p in paths} == set(names), "All six committed account manifests required"
    snapshots = [(p, p.read_bytes()) for p in paths]
    cache = SOURCE / "preparation/market-features.joblib"
    assert sha(cache) == definition["preparation_cache_sha256"]
    forecast_manifest = read(ROOT / "forecast-manifest.json")
    forecast_path = ROOT / "corrected-forecasts.npy"
    assert forecast_manifest["definition_sha256"] == definition_sha
    assert sha(forecast_path) == forecast_manifest["sha256"]
    market, _ = joblib.load(cache, mmap_mode="r")
    forecast = np.load(forecast_path, mmap_mode="r")
    boundaries = [b["test_start"] for b in read(SOURCE / "preparation/coverage-preflight.json")["blocks"]][1:]
    records = []
    for path, raw_manifest in snapshots:
        print(json.dumps({"independent_account": path.name, "phase": "source_ledger_reconstruction"}), flush=True)
        manifest = json.loads(raw_manifest)
        account_path = ROOT / "accounts" / path.name
        raw = account_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
        account = json.loads(raw)
        assert account["definition_sha256"] == manifest["definition_sha256"] == definition_sha
        assert account["forecast_identity"] == manifest["forecast_identity"] == forecast_manifest["sha256"]
        assert account["status"] == manifest["status"]
        assert account["policy"] == "conditional_shrinkage_dollars"
        control_name = f"conditional_net_dollars-{account['horizon']}-{account['cost_profile']}.json"
        control_pointer = SOURCE / "account-manifests" / control_name
        control_manifest = read(control_pointer)
        control_path = SOURCE / "accounts" / control_name
        assert sha(control_path) == control_manifest["sha256"]
        assert control_manifest["definition_sha256"] == source_definition_sha
        control = read(control_path)
        if account["status"] == "complete":
            try:
                result = original.audit_account(account, market, forecast, boundaries)
            except Exception as error:
                result = {"status": "audit_failed", "error": f"{type(error).__name__}: {error}"}
        else:
            result = {"status": "retained_incomplete_account", "account_status": account["status"], "account_error": account.get("error")}
        if result["status"] == "passed" and control["status"] == "complete":
            result["paired_control_deltas"] = {key: account[key] - control[key] for key in ("ending_equity", "total_return", "max_drawdown", "fees", "trades")}
        records.append({"account_path": account_path.relative_to(REPO).as_posix(),
                        "account_sha256": manifest["sha256"], "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                        "control_path": control_path.relative_to(REPO).as_posix(), "control_sha256": sha(control_path),
                        "control_manifest_sha256": sha(control_pointer), **result})
    now = datetime.now(timezone.utc)
    result = {"reviewed_at": now.isoformat(), "planned_accounts": 6, "snapshot_accounts": len(records),
              "definition_sha256": definition_sha, "original_definition_sha256": source_definition_sha,
              "script_sha256": sha(Path(__file__)), "original_checker_sha256": sha(SOURCE / "independent_accounts.py"),
              "forecast_identity": forecast_manifest["sha256"], "records": records,
              "qualification": ["Full source-price/cash/settlement/fee reconstruction reuses the independently verified arithmetic checker.",
                                "Every executed learned forecast matches the new frozen signal-date map exactly.",
                                "Original dollar controls are hash-bound; failed accounts remain visible in the six-path denominator.",
                                "Source consistency and declared fee arithmetic do not establish action completeness or real execution.",
                                "No account replay, model fitting, broker operations or live status-file reads."]}
    output = ROOT / ("independent-account-audit-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "accounts": len(records),
                      "audit_failures": sum(r["status"] == "audit_failed" for r in records),
                      "retained_incomplete": sum(r["status"] == "retained_incomplete_account" for r in records),
                      "trades": sum(r.get("trades", 0) for r in records)}), flush=True)


if __name__ == "__main__":
    main()

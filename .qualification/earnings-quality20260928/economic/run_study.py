"""One immutable offline execution of the predeclared earnings comparison."""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import sys
import traceback
from uuid import uuid4

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = STUDY.parents[1]
for directory in ("model-inputs", "models", "accounts", "qualification"):
    sys.path.insert(0, str(STUDY / directory))
import event_inputs
import earnings_models as models
import account_adapter as accounts
import run_qualification as qualification
from frontier.historical_study import _metrics
from frontier.short_horizon_study import _period_returns

PACKAGES = ("numpy", "pandas", "scikit-learn", "scipy", "joblib", "threadpoolctl", "exchange-calendars")
PATH_KEYS = ("source_root", "qualification_definition", "qualification_summary",
             "terminal_events", "qualification_source_inputs", "issuer_status", "cohort",
             "calendar", "market_completion", "market_inputs", "market_arrays", "specification")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def resolve(name):
    path = Path(name)
    return path if path.is_absolute() else REPO / path


def runtime_dependencies():
    return {name: importlib.metadata.version(name) for name in PACKAGES}


def required_code_paths():
    paths = [Path(__file__), Path(event_inputs.__file__), Path(models.__file__),
             Path(accounts.__file__), Path(qualification.__file__)]
    # Bind all loaded Frontier modules used by the reused fit, planning and cash interfaces.
    paths.extend(Path(module.__file__) for name, module in sys.modules.items()
                 if name.startswith("frontier.") and getattr(module, "__file__", "").endswith(".py"))
    return sorted({path.resolve().relative_to(REPO).as_posix() for path in paths})


def verify_identities(identities):
    for name, expected in identities.items():
        path = resolve(name)
        actual = sha(path) if path.is_file() else None
        if actual != expected:
            raise ValueError("Bound source/code changed: " + name)


@contextmanager
def read_lock(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Required source lock does not exist: " + str(path))
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        connection.execute("BEGIN")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        yield
    finally:
        connection.rollback()
        connection.close()


@contextmanager
def study_locks(source):
    with ExitStack() as stack:
        stack.enter_context(read_lock(source / "capture.lock.sqlite"))
        stack.enter_context(read_lock(source.parent / "sec-source.lock.sqlite"))
        connection = sqlite3.connect(REPO / "data/historical/worker.lock.sqlite", timeout=0)
        try:
            connection.execute("BEGIN EXCLUSIVE")
            yield
        finally:
            connection.rollback()
            connection.close()


def validate_definition(path):
    definition = read(path)
    if definition.get("schema") != 1 or definition.get("reviewed_for_execution") is not True:
        raise ValueError("Root-reviewed execution definition is required")
    if set(PATH_KEYS) - definition.get("paths", {}).keys():
        raise ValueError("Definition omits mandatory paths")
    if definition.get("rerun_of") and not definition.get("reviewed_rerun_reason"):
        raise ValueError("A repeated economic attempt needs an explicit reviewed reason")
    inputs, paths = definition["inputs"], definition["paths"]
    needed = set(required_code_paths()) | {paths[key] for key in PATH_KEYS if key != "source_root"}
    needed |= {str(Path(paths["source_root"]) / name).replace("\\", "/")
               for name in ("request.json", "implementation.json", "registry.json", "completion.json")}
    normalized = {str(resolve(name).resolve()) for name in inputs}
    if {str(resolve(name).resolve()) for name in needed} - normalized:
        raise ValueError("Definition omits mandatory code/source identities")
    if definition.get("dependencies") != runtime_dependencies():
        raise ValueError("Frozen dependency identities differ")
    verify_identities(inputs)
    if sha(resolve(paths["specification"])) != models.SPEC_SHA256:
        raise ValueError("Specification differs from the frozen 20-account declaration")
    return definition


def validate_terminal(definition):
    paths = {key: resolve(value) for key, value in definition["paths"].items()}
    source = paths["source_root"]
    if (source / "STOP.json").exists():
        raise ValueError("Unresolved source STOP")
    completion = read(source / "completion.json")
    if completion.get("status") not in ("captured", "captured_with_coverage_review_needed", "incomplete"):
        raise ValueError("Source completion is not terminal")
    request = qualification.verify_source(source)
    registry = read(source / "registry.json")
    cohort = read(paths["cohort"])
    expected = [(row["symbol"], row["cik"]) for row in cohort["selected"]]
    if (len(expected) != 100 or len(set(expected)) != 100
            or [(row["symbol"], row["cik"]) for row in request["issuers"]] != expected
            or [(row["issuer"]["symbol"], row["issuer"]["cik"]) for row in registry["issuers"]] != expected):
        raise ValueError("Terminal cohort order differs")
    summary = read(paths["qualification_summary"])
    if summary.get("status") != "complete" or summary["definition_sha256"] != sha(paths["qualification_definition"]):
        raise ValueError("Terminal qualification is not completed under its bound definition")
    for key, filename in (("terminal_events", "events.json"), ("qualification_source_inputs", "source-inputs.json"),
                          ("issuer_status", "issuer-status.json")):
        if sha(paths[key]) != summary["files"][filename]:
            raise ValueError("Terminal qualification artifact differs: " + key)
    source_inputs = read(paths["qualification_source_inputs"])
    if source_inputs["definition_sha256"] != summary["definition_sha256"]:
        raise ValueError("Source-input definition differs")
    verify_identities(source_inputs["files"])
    events = read(paths["terminal_events"])
    if len(events) != summary["events"] or summary["retained_original_records"] != len(events):
        raise ValueError("Retained original-event denominator differs")
    market_meta, market_done = read(paths["market_inputs"]), read(paths["market_completion"])
    if (market_done.get("status") != "complete"
            or market_done["outputs"]["market-inputs.json"] != sha(paths["market_inputs"])
            or market_done["outputs"]["market-arrays.npz"] != sha(paths["market_arrays"])
            or market_meta["arrays_sha256"] != sha(paths["market_arrays"])):
        raise ValueError("Frozen source-only market attempt differs")
    if [(r["symbol"], r["cik"]) for r in market_meta["cohort_order"]] != expected:
        raise ValueError("Market/cohort identity differs")
    verify_identities(market_meta["source_inputs"])
    calendar = read(paths["calendar"])
    if market_meta["sessions"] != [row["session"] for row in calendar["sessions"]]:
        raise ValueError("Market and calendar differ")
    with np.load(paths["market_arrays"], allow_pickle=False) as payload:
        market = {key: payload[key].copy() for key in payload.files}
    market.update(symbols=market_meta["symbols"], sessions=market_meta["sessions"],
                  benchmark=market_meta["benchmark"], dates=np.array(market_meta["sessions"], dtype="datetime64[D]"))
    identities = dict(source_inputs["files"])
    identities.update(market_meta["source_inputs"])
    return market, events, cohort, calendar, identities


class FoldLabels:
    """Outcome lookup after the reviewed model partition gate, with a second clock assertion."""
    def __init__(self, market, rows, fold, sessions):
        self.market, self.rows, self.fold = market, {r["event_id"]: r for r in rows}, fold
        self.boundaries = {
            "fit": next(s for s in sessions if int(s[:4]) == fold["calibration_decision_year"]),
            "calibration": next(s for s in sessions if int(s[:4]) == fold["test_decision_year"]),
        }
        self.values, self.accesses = {}, []

    def get(self, event_id, default=None):
        row = self.rows[event_id]
        year = models._decision(row).year
        partition = ("fit" if year in self.fold["fit_decision_years"] else
                     "calibration" if year == self.fold["calibration_decision_year"] else None)
        if (partition is None or row["model_input_status"] != "qualified"
                or row["planned_label_end_session"] >= self.boundaries[partition]):
            raise AssertionError("Premature, unavailable or purged label access: " + event_id)
        if event_id not in self.values:
            self.values.update(event_inputs.extract_labels(self.market, [row]))
        self.accesses.append({"event_id": event_id, "partition": partition,
                              "label_end": row["planned_label_end_session"],
                              "strictly_before": self.boundaries[partition]})
        return self.values.get(event_id, default)


def error_metrics(actual, predicted):
    if not actual:
        return {"count": 0, "mae": None, "mse": None, "mean_error": None}
    residual = np.asarray(predicted) - np.asarray(actual)
    return {"count": len(actual), "mae": float(np.mean(abs(residual))),
            "mse": float(np.mean(residual ** 2)), "mean_error": float(np.mean(residual))}


def diagnostics(bundle, prediction, labels):
    """Read saved predictions and only subsequently acquired labels; never modify a forecast."""
    output = {"family": bundle.family, "year": prediction["test_decision_year"],
              "requested_test_rows": len(prediction["forecasts"]),
              "predicted_rows": sum(r["status"] == "predicted" for r in prediction["forecasts"]),
              "joint_label_available": sum(labels.get(r["event_id"], {}).get("status") == "qualified"
                                           for r in prediction["forecasts"]),
              "model_status": bundle.audit["status"], "heads": {},
              "interpretation": "Repeated retrospective tests with overlapping events and issuer clustering; no independent-event significance claim"}
    for head, name in enumerate(models.HEAD_NAMES):
        report = {}
        for layer in ("raw", "corrected", "training_mean"):
            actual, predicted, bins = [], [], defaultdict(lambda: {"actual": [], "predicted": [], "missing_labels": 0})
            edges = bundle.quantile_edges.get(layer, [[], []])[head] if layer != "training_mean" else None
            numeric_forecasts = 0
            for row in prediction["forecasts"]:
                values = bundle.training_mean if layer == "training_mean" else row.get(layer)
                if layer == "training_mean" and row.get("raw") is None:
                    continue
                if values is None:
                    continue
                value = float(values[head])
                if not np.isfinite(value):
                    continue
                numeric_forecasts += 1
                label = labels.get(row["event_id"], {})
                bin_number = int(np.searchsorted(edges, value, side="right")) if edges is not None else None
                if label.get("status") != "qualified":
                    if bin_number is not None:
                        bins[bin_number]["missing_labels"] += 1
                    continue
                target = label["targets"][head]
                actual.append(target)
                predicted.append(value)
                if bin_number is not None:
                    bins[bin_number]["actual"].append(target)
                    bins[bin_number]["predicted"].append(value)
            report[layer] = dict(error_metrics(actual, predicted), numeric_forecasts=numeric_forecasts,
                                 missing_labels=numeric_forecasts-len(actual))
            if layer != "training_mean":
                baseline = [] if bundle.training_mean is None else [float(bundle.training_mean[head])] * len(actual)
                report[layer]["training_mean_on_same_rows"] = error_metrics(actual, baseline) if baseline else error_metrics([], [])
            if edges is not None:
                report[layer]["calibration_only_edges"] = edges
                report[layer]["bins"] = [
                    {"bin": index, "missing_labels": bins[index]["missing_labels"],
                     "mean_prediction": float(np.mean(bins[index]["predicted"])) if bins[index]["predicted"] else None,
                     "mean_target": float(np.mean(bins[index]["actual"])) if bins[index]["actual"] else None,
                     **error_metrics(bins[index]["actual"], bins[index]["predicted"])}
                    for index in range(len(edges)+1)]
        output["heads"][name] = report
    return output



def event_clustering(rows):
    eligible = [row for row in rows if row.get("model_input_status") == "qualified"]
    by_cik = Counter(row["cik"] for row in eligible)
    by_day = Counter(row["decision_timestamp"][:10] for row in eligible)
    intervals = sorted((row["entry_index"], row["planned_label_end_index"], row["cik"], row["event_id"])
                       for row in eligible)
    active, overlaps, same_issuer = [], 0, 0
    for start, end, cik, event_id in intervals:
        active = [row for row in active if row[0] >= start]
        overlaps += len(active)
        same_issuer += sum(row[1] == cik for row in active)
        active.append((end, cik, event_id))
    return {"causally_eligible_rows": len(eligible), "distinct_ciks": len(by_cik),
            "counts_by_cik": dict(sorted(by_cik.items())), "counts_by_decision_date": dict(sorted(by_day.items())),
            "overlapping_closed_label_interval_pairs": overlaps, "same_issuer_overlapping_pairs": same_issuer,
            "interpretation": "Scheduled interval overlap, including shared endpoints; counts do not assert independent samples or valid future prices"}


def declared_attempts():
    return {"models": [{"family": family, "test_decision_year": fold["test_decision_year"], "status": "declared"}
                       for fold in models.specification()["chronology"]["folds"] for family in models.FAMILIES],
            "accounts": [{"recipe": recipe, "starting_capital": capital, "cost_profile": cost, "status": "declared"}
                         for recipe in accounts.RECIPES for capital in (10000, 2000) for cost in accounts.COST_PROFILES]}

def run_folds(market, rows, calendar, destination):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    combined = {family: [] for family in models.FAMILIES}
    model_rows, diagnostic_rows, all_test_labels = [], [], {}
    spec = models.specification()
    sessions = [row["session"] for row in calendar["sessions"]]
    for fold in spec["chronology"]["folds"]:
        year = fold["test_decision_year"]
        directory = destination / str(year)
        directory.mkdir()
        labels = FoldLabels(market, rows, fold, sessions)
        test_rows = []
        for row in rows:
            try:
                if models._decision(row).year == year:
                    test_rows.append(row)
            except ValueError:
                pass  # The full structural row remains in every model's saved source/disposition audit.
        write(directory / "test-event-clustering.json", event_clustering(test_rows))
        bundles, predictions = {}, {}
        for family in models.FAMILIES:
            bundle = models.fit_family_fold(family, rows, labels, fold, sessions)
            path = directory / family
            models.save_bundle(bundle, path)
            bundle = models.load_bundle(path)
            prediction = models.predict_events(bundle, test_rows)
            write(path / "forecasts.json", prediction)
            bundles[family], predictions[family] = bundle, prediction
            combined[family].extend(dict(row, family=family, test_decision_year=year,
                model_attempt_id=prediction["model_attempt_id"]) for row in prediction["forecasts"])
            model_rows.append({"family": family, "test_decision_year": year, "status": bundle.audit["status"],
                               "attempt_id": bundle.audit["attempt_id"], "samples": {
                                   part: {key: sample[key] for key in ("rows", "distinct_ciks")}
                                   for part, sample in bundle.audit["samples"].items()},
                               "reasons": bundle.audit["reasons"], "warnings": bundle.audit["warnings"],
                               "manifest_sha256": sha(path / "manifest.json"),
                               "forecasts_sha256": sha(path / "forecasts.json")})
        write(directory / "fit-calibration-labels.json", {"labels": labels.values, "accesses": labels.accesses})
        # This durable barrier is written before the first test-outcome access for this year.
        barrier = {family: sha(directory / family / "forecasts.json") for family in models.FAMILIES}
        write(directory / "forecasts-persisted.json", {"fold": fold, "forecast_sha256": barrier})
        test_labels = event_inputs.extract_labels(market, test_rows)
        write(directory / "test-labels.json", test_labels)
        all_test_labels.update(test_labels)
        for family in models.FAMILIES:
            value = diagnostics(bundles[family], predictions[family], test_labels)
            write(directory / family / "diagnostics.json", value)
            diagnostic_rows.append(value)
    for family, forecasts in combined.items():
        if len({row["event_id"] for row in forecasts}) != len(forecasts):
            raise ValueError("Duplicate event ID across model-year forecasts")
        write(destination / (family + "-all-forecasts.json"), {"family": family, "forecasts": forecasts})
    write(destination / "model-attempts.json", model_rows)
    write(destination / "diagnostics.json", diagnostic_rows)
    return combined, model_rows, all_test_labels


def denominators(rows, forecasts, labels, cohort):
    grouped = defaultdict(list)
    for row in rows:
        try:
            year = str(models._decision(row).year)
        except ValueError:
            year = "unassigned"
        grouped[(row["symbol"], row["cik"], year)].append(row)
    for member in cohort["selected"]:
        for year in range(2012, 2026):
            grouped.setdefault((member["symbol"], member["cik"], str(year)), [])
    by_family = {family: {r["event_id"]: r for r in values} for family, values in forecasts.items()}
    output = []
    for (symbol, cik, year), group in sorted(grouped.items()):
        output.append({"symbol": symbol, "cik": cik, "decision_year": year, "structural": len(group),
            **{key: sum(r.get(key) == "qualified" for r in group) for key in
               ("feature_status", "q_status", "joint_feature_status", "strategy_source_status",
                "execution_status", "model_input_status")},
            "test_label_available": sum(labels.get(r["event_id"], {}).get("status") == "qualified" for r in group),
            "test_labels_accessed": sum(r["event_id"] in labels for r in group),
            "predicted": {family: sum(values.get(r["event_id"], {}).get("status") == "predicted" for r in group)
                          for family, values in by_family.items()}})
    return {"requested_issuers": len(cohort["selected"]), "retained_events": len(rows),
            "by_issuer_year": output,
            "issuers_without_events": [r for r in cohort["selected"] if not any(e["cik"] == r["cik"] for e in rows)],
            "missing_reason_counts": dict(Counter(reason for row in rows for reason in row["model_input_reasons"]))}


def references(market):
    first = next(i for i, day in enumerate(market["sessions"]) if day >= "2021-01-01") - 1
    last = market["sessions"].index("2026-01-16")
    sessions = market["sessions"][first:last+1]
    prices = market["adjusted"][first:last+1, market["benchmark"]]
    valid = bool(np.isfinite(prices).all() and (prices > 0).all())
    result = {}
    for capital in (10000, 2000):
        equity = capital * prices / prices[0] if valid else np.full(len(sessions), np.nan)
        simulation = {"equity": equity, "cash": np.zeros(len(sessions)), "fees": 0, "trades": 0,
                      "status": "complete" if valid else "incomplete",
                      "missing": [] if valid else ["SPY required adjusted marks missing"]}
        metrics = _metrics(simulation, sessions, capital)
        if valid:
            metrics["period_returns"] = _period_returns(equity, sessions, capital)
        metrics["convention"] = "Costless fully invested SPY adjusted-price reference; fractional notional, no broker cash/dividend ledger or tax/FX/fees"
        result[str(capital)] = {"cash": {"total_return": 0.0, "interest_assumed": 0.0,
                                           "first_session": sessions[0], "last_session": sessions[-1]}, "SPY": metrics}
    return result


def run_accounts(market, rows, forecasts, model_directory, destination):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    summary = []
    for recipe in accounts.RECIPES:
        kwargs = {}
        if recipe in models.FAMILIES:
            kwargs = {"forecasts": {row["event_id"]: row for row in forecasts[recipe]},
                      "forecast_identity": sha(Path(model_directory) / (recipe + "-all-forecasts.json"))}
        for capital in (10000, 2000):
            for cost in accounts.COST_PROFILES:
                name = f"{recipe}-{capital}-{cost}"
                path = destination / (name + ".json")
                try:
                    result = accounts.run_account(market, rows, recipe=recipe, cost_profile=cost,
                                                  capital=capital, **kwargs)
                    write(path, result)
                    summary.append({key: result.get(key) for key in
                        ("recipe", "cost_profile", "starting_capital", "status", "total_return",
                         "ending_equity", "max_drawdown", "fees", "trades", "trade_metrics", "weekly_objective")})
                except Exception as error:
                    failure = {"recipe": recipe, "cost_profile": cost, "starting_capital": capital,
                               "status": "failed", "error_type": type(error).__name__, "error": str(error),
                               "traceback": traceback.format_exc()}
                    write(path.with_name(name + "-failure.json"), failure)
                    summary.append(failure)
    write(destination / "summary.json", summary)
    return summary


def run(definition_path):
    definition_path = Path(definition_path).resolve()
    definition = validate_definition(definition_path)
    definition_sha = sha(definition_path)
    source = resolve(definition["paths"]["source_root"])
    with study_locks(source):
        # Exclusive claim prevents two jobs or unreviewed replay of a finished/failed definition.
        claims = HERE / "claims"
        claims.mkdir(exist_ok=True)
        attempt = HERE / "attempts" / uuid4().hex
        claim = {"definition_sha256": definition_sha, "attempt": str(attempt),
                 "started_at": datetime.now(timezone.utc).isoformat()}
        write(claims / (definition_sha + ".json"), claim)
        attempt.mkdir(parents=True)
        write(attempt / "attempt.json", dict(claim, definition=definition, status="running"))
        try:
            write(attempt / "declared-attempts.json", declared_attempts())
            market, events, cohort, calendar, discovered = validate_terminal(definition)
            bound = dict(definition["inputs"])
            bound[str(definition_path)] = definition_sha
            for name, digest in discovered.items():
                if name in bound and bound[name] != digest:
                    raise ValueError("Conflicting source identity: " + name)
                bound[name] = digest
            write(attempt / "bound-inputs.json", bound)
            prepared = event_inputs.prepare_events(market, events, cohort, calendar)
            write(attempt / "prepared-events.json", prepared)
            forecasts, model_rows, labels = run_folds(market, prepared["rows"], calendar, attempt / "models")
            write(attempt / "denominators.json", denominators(prepared["rows"], forecasts, labels, cohort))
            reports = run_accounts(market, prepared["rows"], forecasts, attempt / "models", attempt / "accounts")
            write(attempt / "references.json", references(market))
            verify_identities(bound)
            if definition["dependencies"] != runtime_dependencies():
                raise ValueError("Dependency identity changed during execution")
            outputs = {path.relative_to(attempt).as_posix(): sha(path) for path in attempt.rglob("*") if path.is_file()}
            write(attempt / "completion.json", {"status": "complete", "completed_at": datetime.now(timezone.utc).isoformat(),
                "definition_sha256": definition_sha, "scheduled_family_year_attempts": len(model_rows),
                "model_status_counts": dict(Counter(row["status"] for row in model_rows)),
                "account_status_counts": dict(Counter(row["status"] for row in reports)),
                "account_paths": len(reports), "outputs": outputs, "promotion": False,
                "interpretation": "Exploratory fixed-current-member original-filing comparison; completion is not economic qualification"})
        except BaseException as error:
            write(attempt / "failure.json", {"status": "failed", "failed_at": datetime.now(timezone.utc).isoformat(),
                  "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()})
            raise
    return attempt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    print(run(parser.parse_args().definition), flush=True)

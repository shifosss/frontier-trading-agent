"""Frozen deterministic exploratory tournament; every attempted trial is retained."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from frontier.data import load_dataset
from frontier.domain import RunConfig, StrategyConfig
from frontier.replay import code_identity, replay_dataset, run_research, save_json


def run_campaign(
    dataset_id,
    data_root,
    registry,
    artifact_root,
    strategy_configs=None,
    allow_incomplete_actions=False,
):
    dataset = load_dataset(data_root, dataset_id)
    campaign_id = uuid.uuid4().hex
    directory = Path(artifact_root) / campaign_id
    strategies = strategy_configs or [
        StrategyConfig(family="cash", name="cash"),
        StrategyConfig(family="passive", name="passive"),
        *[
            StrategyConfig(family=family, name=f"{family}-{lookback}", lookback=lookback)
            for family in ("trend", "reversion")
            for lookback in (10, 20, 40)
        ],
    ]
    configs = [
        RunConfig(
            dataset_id=dataset_id,
            strategy=strategy,
            allow_incomplete_actions=allow_incomplete_actions,
        )
        for strategy in strategies
    ]
    # One declared stress trial per non-cash family; identical data, doubled fixed costs.
    if strategy_configs is None:
        configs += [
            RunConfig(
                dataset_id=dataset_id,
                strategy=StrategyConfig(family=family, name=f"{family}-cost-stress"),
                commission_per_order=2,
                slippage_bps=10,
                allow_incomplete_actions=allow_incomplete_actions,
            )
            for family in ("passive", "trend", "reversion")
        ]
    created = datetime.now(timezone.utc).isoformat()
    frozen = {
        "campaign_id": campaign_id,
        "dataset_id": dataset_id,
        "frozen_at": created,
        "code_identity": code_identity(),
        "candidate_count": len(configs),
        "configs": [config.model_dump(mode="json") for config in configs],
        "dataset": dataset.manifest.model_dump(mode="json"),
        "promotion_policy": "No automatic promotion; in-sample exploratory tournament",
    }
    save_json(directory / "frozen_candidates.json", frozen)
    overlaps = registry.record_evaluation_access(
        dataset_id,
        dataset.manifest.start.isoformat(),
        dataset.manifest.end.isoformat(),
        campaign_id,
        "full exploratory tournament",
    )
    ranking, trials, run_ids = [], [], []
    for config in configs:
        before = {row["id"] for row in registry.list_runs()}
        try:
            record = run_research(config, data_root, registry, artifact_root)
        except Exception as exc:
            records = [
                r
                for r in registry.list_runs()
                if r["id"] not in before and r["config"] == config.model_dump(mode="json")
            ]
            if not records:
                raise RuntimeError("Trial failed without durable registry record") from exc
            record = records[0]
        run_ids.append(record["id"])
        summary = record["summary"] or {}
        entry = {
            "run_id": record["id"],
            "strategy": config.strategy.name,
            "status": record["status"],
            "total_return": summary.get("total_return"),
            "raw_price_return": summary.get("raw_price_return"),
            "return_basis": summary.get("return_basis"),
            "dividend_income": summary.get("dividend_income"),
            "sharpe": summary.get("sharpe"),
            "costs": {
                "commission_per_order": config.commission_per_order,
                "slippage_bps": config.slippage_bps,
            },
            "error": record["error"],
        }
        trials.append(entry)
        if record["status"] == "COMPLETED":
            ranking.append(entry)
    ranking.sort(key=lambda entry: entry["raw_price_return"], reverse=True)
    result = {
        "campaign_id": campaign_id,
        "dataset_id": dataset_id,
        "created_at": created,
        "kind": "exploratory_tournament",
        "trial_count": len(configs),
        "run_ids": run_ids,
        "ranking": ranking,
        "trials": trials,
        "evaluation_access": {
            "start": dataset.manifest.start.isoformat(),
            "end": dataset.manifest.end.isoformat(),
            "prior_overlaps": overlaps,
        },
        "limitations": [
            "Full interval exposed; all attempts retained; raw trial count declared",
            "In-sample deterministic tournament; no untouched evaluation or walk-forward proof",
            "Same-identity overlap recorded globally; aliases and vintages may overlap undetected",
            "No autonomous LLM research or automatic strategy promotion",
            "Cost-stress candidates use doubled fixed fees/slippage; no optimized costs",
        ],
    }
    save_json(directory / "campaign.json", result)
    return result


def verify_replay(run_id, data_root, registry):
    record = registry.get_run(run_id)
    if record["status"] != "COMPLETED":
        raise ValueError("Only completed runs can be replay-verified")
    if record["code_identity"] != code_identity():
        raise ValueError(
            "Code identity differs from frozen run; restore exact source before verification"
        )
    original = json.loads(
        (Path(record["artifact_path"]) / "result.json").read_text(encoding="utf-8")
    )
    config = RunConfig.model_validate(record["config"])
    dataset = load_dataset(data_root, config.dataset_id)
    registry.record_evaluation_access(
        config.dataset_id,
        dataset.manifest.start.isoformat(),
        dataset.manifest.end.isoformat(),
        run_id,
        "verify identical financial replay",
    )
    repeated = replay_dataset(dataset, config)
    keys = (
        "config",
        "dataset",
        "summary",
        "equity_curve",
        "decisions",
        "fills",
        "positions",
        "balances",
        "dividends",
        "dividend_receivables",
        "engine_identity",
        "exposure_drift",
        "unfilled_intents",
    )
    differences = [key for key in keys if original[key] != repeated[key]]
    return {
        "run_id": run_id,
        "identical": not differences,
        "differences": differences,
        "compared": list(keys),
        "excluded": ["registry UUIDs/runtime times", "evaluation_access"],
    }

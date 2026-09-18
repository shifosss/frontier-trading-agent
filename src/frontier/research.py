"""Bounded model proposals evaluated only through typed, deterministic replay."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frontier.data import load_dataset
from frontier.domain import RunConfig, StrategyConfig
from frontier.providers import CodexProvider, ProviderError
from frontier.replay import code_identity, run_research, save_json, validate_replay_actions

_SUPPORTED_INPUTS = {"raw_close", "raw_open", "dated_usd_cad_fx"}
_REQUIRED_INPUTS = _SUPPORTED_INPUTS

PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "economic_mechanism": {"type": "string"},
        "family": {"type": "string", "enum": ["trend", "reversion"]},
        "lookback": {"type": "integer", "minimum": 2, "maximum": 60},
        "rebalance_every": {"type": "integer", "minimum": 1, "maximum": 20},
        "max_weight": {"type": "number", "exclusiveMinimum": 0, "maximum": 0.2},
        "price_basis": {"type": "string", "enum": ["raw"]},
        "required_inputs": {"type": "array", "items": {"type": "string"}},
        "failure_condition": {"type": "string"},
    },
    "required": [
        "name",
        "economic_mechanism",
        "family",
        "lookback",
        "rebalance_every",
        "max_weight",
        "price_basis",
        "required_inputs",
        "failure_condition",
    ],
    "additionalProperties": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(strategy: StrategyConfig) -> str:
    fields = strategy.model_dump(exclude={"name"})
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def _validate_proposal(proposal: Any) -> tuple[StrategyConfig | None, list[str]]:
    if not isinstance(proposal, dict):
        return None, ["proposal must be a JSON object"]
    errors: list[str] = []
    expected = set(PROPOSAL_SCHEMA["properties"])
    if set(proposal) != expected:
        errors.append(f"fields must be exactly {sorted(expected)}")
    for key in ("name", "economic_mechanism", "failure_condition"):
        if not isinstance(proposal.get(key), str) or not proposal[key].strip():
            errors.append(f"{key} must be a nonempty string")
    if proposal.get("family") not in {"trend", "reversion"}:
        errors.append("family must be trend or reversion")
    if type(proposal.get("lookback")) is not int or not 2 <= proposal["lookback"] <= 60:
        errors.append("lookback must be an integer from 2 to 60")
    if (
        type(proposal.get("rebalance_every")) is not int
        or not 1 <= proposal["rebalance_every"] <= 20
    ):
        errors.append("rebalance_every must be an integer from 1 to 20")
    weight = proposal.get("max_weight")
    if type(weight) not in {float, int} or not 0 < weight <= 0.2:
        errors.append("max_weight must be greater than 0 and no more than 0.2")
    if proposal.get("price_basis") != "raw":
        errors.append("price_basis must be raw; adjusted or total-return bars are unavailable")
    inputs = proposal.get("required_inputs")
    if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
        errors.append("required_inputs must be a list of input identifiers")
    else:
        unsupported = sorted(set(inputs) - _SUPPORTED_INPUTS)
        missing = sorted(_REQUIRED_INPUTS - set(inputs))
        if unsupported:
            errors.append(
                f"unsupported required_inputs: {unsupported}; "
                f"available: {sorted(_SUPPORTED_INPUTS)}"
            )
        if missing:
            errors.append(f"missing engine requirements: {missing}")
    if errors:
        return None, errors
    try:
        strategy = StrategyConfig(
            family=proposal["family"],
            name=proposal["name"].strip(),
            lookback=proposal["lookback"],
            rebalance_every=proposal["rebalance_every"],
            max_weight=weight,
        )
    except ValueError as exc:
        return None, [str(exc)]
    return strategy, []


def _prompt(frozen: dict, feedback: dict | None) -> str:
    dataset = frozen["dataset"]
    message = {
        "role": "exploratory_research_proposal_worker",
        "instruction": (
            "Return one JSON proposal conforming to the schema. Use only the built-in "
            "trend (close above trailing mean) or reversion (last close below first "
            "trailing close) template. No generated code, external data, quotes, orders, "
            "forecasts, adjusted prices, or new strategy logic. Every attempt counts."
        ),
        "dataset": {
            "dataset_id": dataset["dataset_id"],
            "name": dataset["name"],
            "mode": dataset["mode"],
            "interval": dataset["interval"],
            "start": dataset["start"],
            "end": dataset["end"],
            "instruments": [i["id"] for i in dataset["instruments"]],
            "corporate_actions_status": dataset["corporate_actions_status"],
            "availability_basis": dataset["availability_basis"],
        },
        "fixed_engine": {
            "supported_inputs": sorted(_SUPPORTED_INPUTS),
            "required_inputs": sorted(_REQUIRED_INPUTS),
            "price_basis": "raw",
            "decision_timing": "available_close",
            "fill_timing": "next_eligible_open",
            "quotes": "synthetic_from_raw_bars",
            "costs": frozen["costs"],
        },
        "schema": PROPOSAL_SCHEMA,
        "feedback_from_previous_attempt": feedback,
        "interpretation": "exploratory only; no alpha or holdout certification",
    }
    return json.dumps(message, sort_keys=True, ensure_ascii=False)


def run_model_campaign(
    dataset_id: str,
    data_root: Path,
    registry: Any,
    artifact_root: Path,
    max_proposals: int = 2,
    allow_incomplete_actions: bool = False,
    provider: Any = None,
) -> dict:
    """Persist up to two real proposal attempts and replay accepted templates."""
    if type(max_proposals) is not int or not 1 <= max_proposals <= 2:
        raise ValueError("max_proposals must be 1 or 2; repairs consume the same budget")
    dataset = load_dataset(data_root, dataset_id)
    validate_replay_actions(dataset)
    if dataset.manifest.corporate_actions_status != "complete" and not allow_incomplete_actions:
        raise ValueError("Action coverage incomplete: allow_incomplete_actions required")
    worker = provider if provider is not None else CodexProvider()
    campaign_id = uuid.uuid4().hex
    directory = Path(artifact_root) / "model-campaigns" / campaign_id
    base = RunConfig(dataset_id=dataset_id, allow_incomplete_actions=allow_incomplete_actions)
    frozen = {
        "campaign_id": campaign_id,
        "created_at": _now(),
        "dataset": dataset.manifest.model_dump(mode="json"),
        "code_identity": code_identity(),
        "costs": {
            "commission_per_order": base.commission_per_order,
            "slippage_bps": base.slippage_bps,
        },
        "run_defaults": base.model_dump(mode="json"),
        "proposal_schema": PROPOSAL_SCHEMA,
        "max_proposals": max_proposals,
    }
    save_json(directory / "frozen_inputs.json", frozen)
    overlaps = registry.record_evaluation_access(
        dataset_id,
        dataset.manifest.start.isoformat(),
        dataset.manifest.end.isoformat(),
        campaign_id,
        "model-driven exploratory campaign",
    )
    result = {
        "campaign_id": campaign_id,
        "dataset_id": dataset_id,
        "kind": "model_exploratory_research",
        "status": "RUNNING",
        "created_at": frozen["created_at"],
        "artifact_path": str(directory.resolve()),
        "max_proposals": max_proposals,
        "attempts": [],
        "accepted_run_ids": [],
        "evaluation_access": {
            "prior_overlaps": overlaps,
            "start": dataset.manifest.start.isoformat(),
            "end": dataset.manifest.end.isoformat(),
        },
        "limitations": [
            "All model-driven historical research is exploratory and adaptively selected",
            "No untouched outer holdout, hidden isolation, DSR, or proof of alpha",
            "No generated code, broker execution, or automatic strategy promotion",
        ],
    }
    save_json(directory / "campaign.json", result)
    seen: set[str] = set()
    feedback: dict | None = None
    for number in range(1, max_proposals + 1):
        attempt_dir = directory / f"attempt-{number:02d}"
        attempt: dict[str, Any] = {
            "number": number,
            "status": "started",
            "created_at": _now(),
            "artifact_path": str(attempt_dir.resolve()),
        }
        try:
            response = worker.propose(_prompt(frozen, feedback), PROPOSAL_SCHEMA, attempt_dir)
            proposal = response["proposal"]
            attempt["provider"] = {
                key: str(value) if isinstance(value, Path) else value
                for key, value in response.items()
                if key != "proposal"
            }
            attempt["proposal"] = proposal
            strategy, errors = _validate_proposal(proposal)
            if errors:
                attempt["status"] = "rejected"
                attempt["reasons"] = errors
                feedback = {"status": "rejected", "reasons": errors}
            else:
                signature = _signature(strategy)
                if signature in seen:
                    attempt["status"] = "duplicate"
                    attempt["reasons"] = [
                        "Strategy configuration duplicates an earlier accepted attempt"
                    ]
                    feedback = {"status": "duplicate", "reasons": attempt["reasons"]}
                else:
                    seen.add(signature)
                    config = RunConfig(
                        dataset_id=dataset_id,
                        strategy=strategy,
                        allow_incomplete_actions=allow_incomplete_actions,
                    )
                    attempt["config"] = config.model_dump(mode="json")
                    save_json(attempt_dir / "frozen_config.json", attempt["config"])
                    record = run_research(config, data_root, registry, artifact_root)
                    attempt["run_id"] = record["id"]
                    attempt["status"] = "accepted"
                    summary = record["summary"] or {}
                    feedback = {
                        "status": "evaluated",
                        "run_id": record["id"],
                        "total_return": summary.get("total_return"),
                        "raw_price_return": summary.get("raw_price_return"),
                        "return_basis": summary.get("return_basis"),
                        "dividend_income": summary.get("dividend_income"),
                        "max_drawdown": summary.get("max_drawdown"),
                        "sharpe": summary.get("sharpe"),
                        "trade_count": summary.get("trade_count"),
                        "fees": summary.get("fees"),
                        "slippage": summary.get("slippage"),
                        "evidence_label": summary.get("evidence_label"),
                        "interpretation": "actual deterministic replay; exploratory, not heldout",
                    }
                    attempt["feedback"] = feedback
                    result["accepted_run_ids"].append(record["id"])
        except ProviderError as exc:
            attempt["status"] = "provider_failed"
            attempt["error"] = str(exc)
            attempt["provider_artifact_path"] = str(exc.artifact_path)
            result["status"] = "FAILED"
        except Exception as exc:
            attempt["status"] = "evaluation_failed"
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            feedback = {"status": "evaluation_failed", "error": attempt["error"]}
        attempt["completed_at"] = _now()
        save_json(attempt_dir / "attempt.json", attempt)
        result["attempts"].append(attempt)
        save_json(directory / "campaign.json", result)
        if result["status"] == "FAILED":
            break
    if result["status"] == "RUNNING":
        result["status"] = "COMPLETED"
    result["completed_at"] = _now()
    result["call_count"] = len(result["attempts"])
    save_json(directory / "campaign.json", result)
    return result

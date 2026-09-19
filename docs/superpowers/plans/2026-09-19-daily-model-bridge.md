# Daily Model Decision Bridge Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to execute and independently review bounded tasks.

**Goal:** Turn the existing historical model code into a saved, reproducible daily decision pipeline without changing the active paper baseline.
**Architecture:** Existing models -> verified local bundle -> shared forecast scoring and cash planning -> immutable candidate decision report. Cost evidence remains independently measured.
**Tech Stack:** Python 3.13, numpy, pandas, scikit-learn, joblib, Typer, pytest, existing saved captures.
**Spec:** docs/superpowers/specs/2026-09-19-daily-model-bridge-design.md

## Global Constraints
Preserve frozen paper files and journal. No live orders, transfers, authentication, paid services or automatic promotion. Existing results remain immutable. Daily decisions use only known data, 1/3/5-session independent positions, next-close timing, settled cash and whole shares. Default candidate budget is USD2000. Keep all warnings and failed attempts visible. Ponytail full/standard: reuse existing models, data loaders and accounting; no speculative framework.

## Tasks
1. Model bundle: refactor ensemble_models.py without numerical change; add model_artifact.py and focused tests. Implement exact spec interfaces. Verify direct/reloaded predictions and integrity/schema/runtime failures. Owner: model implementer.
2. Shared policy: add daily_policy.py; delegate ensemble_study forecast score and short_horizon_study planning to it with identical baseline behavior. Add cash/reservation and differential regression checks. Owner: root.
3. Candidate integration: add candidate_daily.py, CLI candidate-build, tests and docs/daily-model-bridge.md. Verify frozen capture hashes, chronological training, immutable artifacts, deterministic decision IDs, full rankings/reasons and reloaded prediction parity. Use Task1/2 interfaces. Owner: candidate implementer; do not edit Task1/2 files.
4. Cost evidence: independently predeclare broader free SIP quote sampling across price/liquidity/date/time strata; implement repeatable analysis using existing capture/probe code and preserve all failures. Verify current primary broker tariffs and report fixed-fee arithmetic separately. Own docs/trading-cost-evidence.md and qualification evidence only; no strategy or account mutation. Owner: cost researcher.
5. Integration qualification: run all focused/full checks, real frozen USD capture build and differential simulator audit. Independent reviewers inspect task diffs and integrated result. Update roadmap/mandate/automation to actual completion; report remaining economic and broker qualification work without claiming profitability.

## Review record
Preflight: Task1 produces bundle API consumed by Task3; Task2 produces planner API consumed by Task3. Tasks1/2/3 own separate files except Task2 alone edits study modules. Task4 does not change production assumptions. Tests align with each task's implementation. No conflicting interfaces identified.


## Completed implementation and validation

Tasks 1-4 implemented; integrated build 83d99338fd394e7cad44bdad045b25ad completed on all 5,675 requested USD instruments. 2,878 eligible stocks were forecast; saved/reloaded predictions match exactly. The unchanged declared preset produced zero entry intents and retained USD2,000 cash. All source failures, no-entry decisions and MLP convergence warning remain visible. Two independent review findings were fixed: deterministic tree inference and complete failed-request arguments. Full 394 tests and final 17 candidate tests passed; 32 model tests; exact 240-case / 69,491-trade baseline comparison; lint and changed-file format passed. See docs/daily-model-bridge.md for complete evidence and unfinished economic/operating gates.

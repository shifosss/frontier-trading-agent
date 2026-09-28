# Stateful daily agent implementation plan

> For agentic workers: use bounded subagents and independent review; continue already authorized work without further approval.

Goal: persistent model-to-account rehearsal plus realistic declared order costs, with evidence-led forecast improvement.
Spec:docs/superpowers/specs/2026-09-19-stateful-daily-agent-design.md

## Global Constraints
Frozen paper state untouched; no live actions/spending; retain all research outcomes; predeclared methods; no claim of all-period profitability. Reuse existing modules with Ponytail full/standard.

## Tasks and ownership
1. Cost implementer owns execution_costs.py, test_execution_costs.py, docs/execution-cost-model.md. Verify primary tariffs, implement exact callable API and independent tests.
2. Root owns daily_policy.py and short_horizon_study.py state/cost integration, related tests and study code identity. Extend existing engine, no duplicate simulator.
3. Replay implementer owns candidate_replay.py, test_candidate_replay.py and docs/candidate-replay.md. Coordinate exact root state API and cost API; no shared-file edits.
4. Diagnostics researcher owns .qualification/forecast-diagnostics and docs/forecast-calibration-diagnostics.md. Existing source/model only; produce actionable evidence without changing strategies.
5. Root integrates CLI, runs real historical model/replay and independent review. Every task report and correction retained in .qualification/stateful-daily-agent. Update roadmap/automation to actual outcome. Goal remains active until full requirements proved.

## Preflight
Costs->planner/engine uses fee and maximum_quantity. Engine->replay uses next_session_index/full state and process_through while keeping fixed end. Replay does not refit or use signal-future labels. Diagnostics changes no production files. Shared filenames partitioned. No identified conflict.

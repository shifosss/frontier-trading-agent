# Research Kernel Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan task-by-task, with independent spec/quality review and a final integrated review.

**Goal:** Deliver a usable local research workbench for US and Canadian stocks/ETFs whose replay, data provenance, and currency/accounting semantics are demonstrated by executable evidence.

**Architecture:** A Python control application owns dataset and experiment records. A qualified established engine provides the trading simulation behind one narrow adapter. The report and local interface consume the same recorded artifacts.

**Tech Stack:** CPython 3.13, uv, a qualified engine selected in Task 1, Parquet/DuckDB analytical data, SQLite registry, CLI and local web interface.

**Spec:** ../specs/2026-09-18-frontier-trading-system-design.md

## Global constraints

- US and Canadian stocks and ETFs, hours-to-weeks strategies.
- Use existing access and free resources; ask before new spending.
- No live broker orders or assumed live-capital authority.
- Record fixtures, historical research, local paper, and broker paper as separate modes.
- Preserve USD/CAD balances, dated FX inputs, corporate actions, instrument identity, and venue calendars.
- Direct implementations, explicit contracts, visible failures; no silent substitute data.
- Tests demonstrate financial/time invariants using independent expected results.
- No global configuration changes or paid backend model calls as incidental setup.

## Execution authority

The user accepted the architecture and explicitly delegated implementation, testing, validation, and routine decisions on 2026-09-18. Do not ask for another architecture sign-off. Execute technical tasks autonomously, recording material rulings and their consequences in docs/progress.md.

## Task 1: Engine qualification

Read the complete requirements in `docs/tasks/01-engine-qualification.md`. Produce executable probes and observed results before selecting engine APIs. This task's result fixes the runtime dependency and adapter contract for subsequent tasks; do not fabricate those APIs in advance.

- [ ] Inspect official package/source availability and local runtime compatibility.
- [ ] Install candidate dependencies in workspace-local environments with workspace-local caches.
- [ ] Run a real simulation and inspect order/account results.
- [ ] Test USD/CAD identities, action-accounting primitives, corporate action gaps, and actual API limits.
- [ ] Record reproducible candidate evidence, exact versions, and the smallest viable integration.
- [ ] Independently review the evidence and decide the primary runtime.

## Subsequent implementation contracts

After Task 1, expand these into exact interface/test briefs before dispatch. These are dependent delivery contracts, not placeholder implementation APIs.

2. **Data and evidence:** immutable dataset manifests, time-aware records, typed run configurations, SQLite experiments and evaluation-access history. Test revision availability, duplicate identity, preserved failed trials, and repeatable manifests.
3. **Research replay:** engine adapter, cash/passive/trend/reversion baselines, explicit costs, USD/CAD reporting, independent account fixtures, future-mutation invariance, and exact replay. Default run uses engineering fixtures; a separate real-data import path preserves source limitations.
4. **Usable interface:** one-command CLI, local dashboard/report, dataset import, research run, run comparison, replay and doctor. Display actual stored artifacts and clear evidence modes. Exercise the interface through a browser.
5. **Evaluation and operation:** chronological campaign splits, portfolio-state continuity, transparent trial counts and honest uncertainty, deterministic research tournament, real data capture and frozen forward observations when public source access supports them.
6. **Integrated release:** independent review, targeted fixes, fresh lint/type/test/build evidence, one-click Windows launcher, usable documentation, and a precise capability/gap report.

Each task requires actual executable acceptance before completion. An unavailable external service does not turn a fixture into a completed integration.

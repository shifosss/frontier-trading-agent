# Execution ledger — Research Kernel

Plan: docs/superpowers/plans/2026-09-18-research-kernel.md

## Authority and rulings

- Architecture approved by the user's explicit delegation of the build, testing, and validation. Routine technical work proceeds without repeated approvals.
- Ruling: initialize a development branch in the greenfield workspace; no existing repository or code requires a separate worktree. Cost if wrong: local branch/worktree reorganization, with no production state involved.
- Ruling: engine selection uses actual executable package evidence. Planning sources are not accepted as proof of runtime availability. Cost if wrong: a bounded qualification experiment and documented dependency revision.

## Preflight review

| Task/interface | Producer -> consumer | Check |
| --- | --- | --- |
| Task 1 -> data/replay | Installed engine evidence -> exact integration contracts | Dependent API design waits for actual probe results. |
| Data -> replay -> UI | Dataset/run records -> engine results -> report | Shared schemas will be frozen in the next task brief; UI must display persisted results. |
| All tasks | US/Canada, USD/CAD, existing/free-only | Binding scope copied into plan and qualification brief. |
| Task 1 | Candidate source inspection vs runtime probes | Report labels required; neither is allowed to imply the other. |

## Status

- Planning/design: reviewed and approved.
- Task 1: not started.
- Remaining implementation: not started.

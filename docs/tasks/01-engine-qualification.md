# Task 1: Engine qualification

## Context and authority

New project in `E:\Alex's Local Codebases\One_Person-Trading_Agent`. Approved US+Canadian stocks/ETFs, hours-to-weeks, existing/free-only. No code exists yet. Python 3.13 and uv are present. .NET 9.0.310 is installed; Docker Linux engine was not reachable during planning. No broker/account operation is authorized by this task.

## Deliverable and owned files

Own `engines/qualification/` and `docs/engine-qualification.md` only, plus ignored `.qualification/` environments and `.cache/uv/` cache. Do not change root dependency files or other agents' files. Do not spawn subagents. Write a concise report to `docs/tasks/01-engine-qualification-report.md` and return status/evidence/concerns. The root agent will handle commits and independent review.

## Required work

1. Verify actual package/source availability. The researched Nautilus candidate is 1.231.0; do not assume it exists on the accessible package index. If unavailable, record actual official index evidence and resolve a current stable supported version, reporting that change immediately. Pin all actual versions used.
2. Install Nautilus only into a workspace-local environment using existing Python and a local uv cache. Network escalation for legitimate package downloads may be requested through tools. Do not alter global Python or install system runtimes.
3. Build a small executable engine probe with a native US equity and Canadian CAD equity, different venue/instrument IDs, quotes/bars and a simple order. Obtain actual fills/account outputs; report native USD/CAD cash behavior and currency conversion prerequisites.
4. Inspect and experimentally test available action/account adjustment APIs. Establish whether dividends and split positions/orders can be represented faithfully through a narrow adapter. Do not claim a synthetic fill is economically equivalent without independently checking cash, quantities, order state, and P&L. If not possible, report the exact gap.
5. Inspect standalone LEAN's actual accessible pinned source/config runtime requirement, Canadian support and licensing. Attempt execution only if a compatible existing/local free runtime is already available; do not make a global .NET/Docker change to satisfy this comparison. Explicitly label source inspection vs executed probes.
6. Propose the smallest qualified route satisfying the combined market/accounting requirements. It is acceptable to report neither fully qualified, but include the precise remaining work and evidence. Do not create a universal custom trading engine.

## Probe acceptance

- The probe imports and uses the real installed engine.
- All data are visibly synthetic engineering fixtures.
- Report installed engine version, interpreter, source/package identities, input events, fills, balances and limitations.
- Repeated runs normalize nondeterministic IDs/times explicitly and compare financial/order content directly.
- Hand-work a known purchase and fee result, then compare actual engine output.
- Any unsupported feature is reported as unsupported/unverified, not given mock success.
- Test execution must be recorded with commands, exit codes, and relevant results.

## Shell instructions

Prefix shell commands with `rtk`; use `rtk proxy` when necessary. PowerShell paths contain spaces and an apostrophe. Keep environment/cache writes inside the workspace. Never expose credentials. All state-changing work must stay in owned directories.

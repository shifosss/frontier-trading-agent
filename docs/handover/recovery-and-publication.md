# Recovery, publication and continuation

## What a fresh clone contains

The private repository is intended to contain the application, its tests, locked dependencies, original Git history, complete recorded documentation, project-authored research scripts/tests/reasoning at their original `.qualification` paths, and an explicit curated set of compact experiment declarations/results/verification tables. Original bytes and failed/pre-review snapshots remain distinguishable. The publication manifest names every included research file.

Large original market/SEC captures, full row-level ledgers, large model/joblib/NumPy payloads, source caches, installed runtimes/plugins/dependencies and the existing private broker journal are retained locally. The artifact inventory gives relative paths, sizes, SHA256 identities, modification times, publication decisions and any read/access failures. It is not a claim that a clone includes those bytes. A no-data clone can install/build/test the normal application and inspect the research decisions; reproducing a completed historical study requires its retained frozen inputs and compatible environment. Do not silently reacquire revised history and claim it reproduces the original run.

GitHub blocks ordinary Git files above100MiB and recommends small repositories. Large binary releases are a separate facility; a release attachment does not remove source licensing/access restrictions or authorize storage spending. See [GitHub's official file-size guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github). The existing `earnings-comparison-20260929.zip` is155,043,133bytes and exceeds the normal Git per-file limit. Its191 payload files plus one archive manifest (192 ZIP entries) and SHA256 `51a620b50b7462d04887d6317fc9b8a6b68ebafc8fb07e2e8386510c3f122c97` are catalogued. Its raw SEC source corpus is separate; the archive is not a full workspace backup. The unchanged bundle is attached to the private [October1 handover release](https://github.com/shifosss/frontier-trading-agent/releases/tag/handover-2026-10-01), after a hash and credential/private-identifier review.

Source acquisition rights and private repository access are not the same as permission to redistribute vendor datasets. The publication selection excludes original vendor payloads by default. Public SEC source facts, provider responses, current broker metadata and installed third-party source clones are classified separately. Preserve provider identity/license/terms references; do not vendor external runtimes or a plugin clone just because a filename has a source-code extension.

The owner requested a **private** repository and will create it. Recommended project title: **Frontier Trading Agent**. Recommended slug: **`frontier-trading-agent`**. The owner supplied `https://github.com/shifosss/frontier-trading-agent.git`. Its private visibility and owner/admin permission were verified on October1. Existing GitHub access was available through the authenticated connector and CLI keyring; no new login was needed. Publication preserves local and any initial remote history. Do not create an account/repository, change visibility or overwrite unrelated remote history by assumption.

## Installation and a safe first run

Use Python3.13, uv and Node.js/npm. From the clone root:

```powershell
uv sync --frozen
npm --prefix frontend ci --cache .cache/npm
npm --prefix frontend run build
& '.venv/Scripts/python.exe' -m frontier.cli --help
```

On Windows, `Launch Frontier.cmd` or `scripts/start.ps1` opens the local workstation. The normal UI is at `http://127.0.0.1:8765/`; bind it locally. The UI/server does not itself prove that any historical source worker or paper watcher is running. Read the detailed technical runbook for actual entrypoints, port/process reuse and logging.

For the ordinary application checks, run `scripts/verify.ps1`. Do not recursively execute every archived test snapshot under `.qualification`: those files preserve earlier interfaces and failed/pre-review states. Execute a research study's documented focused tests against its declared current implementation when that study is being changed. Software verification must not trigger a source acquisition, model refit or broker order cycle accidentally.

On October1, the owner explicitly authorized storing the existing paper credentials in the private repository or as GitHub secrets for machine synchronization. The selected approach stores `FRONTIER_ALPACA_PAPER_KEY` and `FRONTIER_ALPACA_PAPER_SECRET` as encrypted GitHub Actions repository secrets; both names and update metadata were verified without retrieving or printing their values. No plaintext credential was committed. Repository secrets can be used by authorized Actions workloads; GitHub does not expose them as downloadable local-machine configuration. Each local workstation still needs its own local variables. See [GitHub secret usage](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) and [the official CLI secret command](https://cli.github.com/manual/gh_secret_set). No cloud trading workflow or new paper watcher is enabled by storing these secrets.

No broker keys are needed to understand the handbook or run synthetic software tests. For authorized paper access, set `FRONTIER_ALPACA_PAPER_KEY` and `FRONTIER_ALPACA_PAPER_SECRET` locally as documented in `docs/paper-operator.md`. Credentials never belong in tracked source, Markdown, result records, screenshots or issue comments. The Windows persisted-user-variable fallback is implemented because restarting the desktop app was necessary for inherited environment changes in the original session. Never put real credentials into the repository or send them in chat.

A fresh clone has **no initialized operator journal**. It must not initialize a replacement journal while the original USD100,000 paper account still has the authorized existing holdings/orders. For continuity, the trusted existing operator journal must stay with its original reconciled account and frozen identity. Moving the workstation requires a separately reviewed backup/restore and state reconciliation; copying executable code alone is not a paper-account migration.

## Restoring completed research evidence

1. Read the study's current results and original definition, including excluded/failed counts and code/source/dependency identities.
2. Locate the exact run/attempt IDs in the study catalogue and `artifact-inventory.csv`. Recover retained files from the original workspace/archive or a separately authorized backup. Verify SHA256 and sizes. Keep relative layout and any declared absolute-path/source identity requirements visible.
3. Install locked dependencies; keep Python/scikit-learn/runtime identities compatible. Trusted joblib files can execute code when loaded, so only restore known locally generated bytes after verification. A hash is an identity check, not a license or trust grant for a stranger's payload.
4. Restore raw response files, registry/requests/progress/completion records, manifests, models and accounts as required by the original runner. The compact Git publication is not a substitute for omitted raw/row-level files.
5. Check actual owned processes and source/shared historical locks. A saved completed historical-status record does not describe another worker. A terminal source status named `incomplete` can mean completed with preserved failures, not resumable interruption.
6. Prefer exact saved-model reload or independent ledger/source checks. Refit/reacquire/rerun only for a declared reproduction purpose and a new immutable attempt, keeping the original intact. Never overwrite a failure or alter a study to get a more favorable result.
7. If original bytes are unavailable, label reconstruction as a new experiment and disclose changed vintages/membership/environment. Do not represent a current re-download as byte-exact reproduction.

`artifact-inventory.csv` is a dated snapshot, not a perpetual file-existence assertion. Its stable-during-inventory flag detects size/time changes during hashing; traversal/file failures and excluded mutable broker state remain explicit. Installed dependencies and third-party clones can be restored from their lock/upstream identities and are outside the authored-evidence inventory.

## Operational state verified October 1

Before the documentation request, root inspected historical-status and actual project worker processes. The saved historical-status was the completed September19 multi-model run `814780d48b4141b9a82a3fb917d1b85a`, not evidence of a still-running earnings collector. No owned project Python research worker was running at the initial process check. The September29 100-issuer source capture, terminal collector, ten earnings fits and twenty economic paths are complete and must not be restarted unchanged.

The earlier paper watcher had stopped. An independent read-only review verified absent old processes, a free paper lock, SQLite integrity, the frozen seven-file identity, reconcilable cash/holdings and no uncertain/working orders or rejected exits. Root resumed `scripts/start-paper.ps1` **once**. Parent38984/child32940 were verified and a fresh15:18UTC paper status was `ready`, with USD81,194.12 cash, simulated MSFT15/META6/XOM42 and zero open orders. This is a dated observation; future readers must check actual processes, locks and observations again. Paper operation uses only the fixed paper endpoint and ignores advertised margin buying power.

The frozen paper code identity is `9fd509d8ce514b9fe3e3136684c7475637a12304670cc517b285e48aebbc26a2`. Its seven files are `operator.py`, `operator_store.py`, `paper_risk.py`, `paper_broker.py`, `swing_policy.py`, `scan_data.py`, `sources.py` under `src/frontier`. Editing any of them changes the identity and requires reconciliation/migration; this documentation work changes none.

The thread heartbeat `frontier-daily-research-scan` remains scheduled on weekdays at09:35 and17:35 Toronto. Its October1 priority was updated to finish this handover/publication preparation before new research. After the handover is complete, its existing source-only novelty/timing priority resumes subject to all preserved constraints. A scheduled heartbeat is not an experiment worker, and a300-second paper watcher interval is not an hourly strategy.

## Unfinished work toward the automated-agent goal

| Work | What exists | What remains |
|---|---|---|
| Strategy edge | Many frozen rule/model/event comparisons, full losses/failures and independently verified ledgers | A reproducible strategy with credible net economic benefit, acceptable concentration/stability/drawdown and explicit source limitations |
| Hourly strategy | Verified US SIP minute source path and a completed losing intraday pilot | Broader useful evidence/qualified hypotheses; no synthetic hourly bars or universal US/Canadian coverage claims |
| Disclosure timing | Completed original10-Q S/Q corpus and cached discovery roots/history; 8-K Item2.02 metadata audit frozen October1 and run once October2 ([results](../disclosure-timing-results.md)): supported at metadata level, 63.9-64.4% of qualified events | Do not rerun the audit unchanged. The seeded, bounded exhibit-content probe of qualified `single_prior` candidates is frozen ([design and run steps](../exhibit-content-probe.md)); run it once on the workstation to verify original release/exhibit fiscal-period and component disclosure before any earlier-clock strategy |
| Stateful daily decisions | Saved models, exact reload, shared cash planner and persistent historical rehearsal | Separately versioned broker-daily integration with reconciled positions, partial-fill remainders, reservations, exits and settlements; no automatic baseline migration |
| Corporate actions | Dividend receivables/payment-date support where qualified, plus separate split reconstruction/action-source investigations and retained failures; strict replay rejects known splits | Exact unresolved issuer/action/share/cash chronology; adjusted-notional marks do not implement every actual broker dividend or merger event |
| Canadian operations | Listings and exploratory histories with retained failures | Reliable sufficient historical source coverage, corporate-action completeness and authorized Canadian broker execution integration |
| Options | Bounded access/metadata probes and broker-feasibility analysis | Historical as-of contract/deliverable and executable bid/ask evidence, settlement/cash semantics and permitted account structures; no option backtest or order authority exists |
| Live deployment | Fixed paper-only baseline and reconciliation controls | A qualified operational policy, broker/account readiness and explicit live authority. Nothing in this handover activates live trading |
| Product maturity | Local dashboard, CLI, registries and reports | Make economic and operational status easy to understand; retain clear distinctions between exploratory simulations, qualified execution, paper observations and live results |

The source-only disclosure novelty audit is a research hypothesis, not a proven explanation for weak earnings forecasts. Earlier timestamp/sameCIK/Item2.02 is a candidate, not proof of same-period earnings or cash-flow disclosure. Freeze matching windows, event denominators, ambiguity/missing/late rules and source/code identities before matching. Never backdate a later10-Q's S/Q to an earlier release. If a bounded original-document probe becomes useful, declare request/storage/rate/source boundaries before acquisition; do not restart broad completed capture or work around global STOP conditions.

## First session checklist for a new agent

Read `AGENTS.md`, this handbook, `config/mandate.json`, `docs/trading-cadence.md`, the current results and the relevant frozen definition. Resolve apparent conflicts by date and evidence; preserve old plans as historical records. Inspect Git status and original paper identity before editing. Check actual processes/locks before worker operations. Use existing implementations rather than rebuild the daily/model/cash interfaces. Prioritize a useful falsifiable strategy question rather than minor cosmetic code issues. Predeclare each new test and report every account/variant/failure, costs, weeks, exposure, concentration and drawdown. Keep paid/live/options/transfer boundaries intact. Continue from the evidence; do not repeat the failed unchanged grids.

## Documentation maintenance policy

For a material decision, record the problem, considered alternatives, selected behavior, practical reason, evidence, validation, limits and status. Distinguish a contemporaneously recorded rationale from an explicitly labeled retrospective reconstruction. Include the relevant source/attempt/code identity and date. Update the current handbook/status index when a milestone completes, while preserving the original dated definition/result and failures. Never present new software tests as economic validation or a plan as implemented behavior.

A future reader should be able to answer: what does the system do now; what can it trade under current authority; why was each path chosen; what happened in every experiment; where are the exact inputs/results; what must be restored; and what is the next authorized useful step. This handover is organized around those questions.

## Byte identity and cross-platform checkout

Curated `.qualification` research/evidence and handover records are marked `-text` in `.gitattributes`, preserving their original bytes rather than silently rewriting line endings on another machine. Ordinary pre-existing application source retains its Git text behavior. The recorded original-doc identities describe the inspected Windows working bytes; platform newline conversion can alter those bytes while preserving text. Strict saved-model code identities compare actual bytes and may refuse a cross-platform reload. Restore the exact source members from the retained qualified archive and verify declared runtime/code identities rather than editing the saved model manifest to accept drift. Code synchronization alone is not exact model/data reproduction.

# Frontier Trading Agent — instructions for a new session

Start with [the project handbook](docs/project-handbook.md), then `config/mandate.json`, `docs/trading-cadence.md` and the latest results/definition for the work you are changing. The handbook records the owner mandate, decisions, failed experiments, architecture, current state and continuation rules. Older dated plans are historical evidence; newer completed results govern current status.

## Current priority

The October1 handover/publication and cached disclosure timing audit are complete. Read `docs/disclosure-novelty-results.md` and its frozen definition/reviews before continuing. Next: declare a bounded, source-only original 8-K document/exhibit probe to verify candidate filer identity, fiscal period and components actually disclosed. Metadata timing alone does not qualify an earlier financial signal. Do not rerun the unchanged cached audit or completed earnings, ETF, conditional, multi-model or intraday studies. Repository: `https://github.com/shifosss/frontier-trading-agent`.

## Governing constraints

- Prioritize useful historical strategy development over cosmetic code changes. US/Canadian stocks/ETFs, hourly/daily decisions and intraday to about one-week individual positions are the product mandate.
- USD10,000 primary research balance and USD2,000 comparison are simulated; the5%/10%/15% whole-account weekly targets are aspirations. Keep idle/losing weeks, costs, drawdowns and all failed variants. Cash only, no borrowing,30%drawdown constraint; CAD risk and ETF reserves are separate.
- Use existing authorized access/free resources only. No purchases, fund transfers, broker authentication, real securities orders or options orders are authorized.
- Preserve original source bytes, membership, clocks, failures, attempt/code/dependency identities and training-only/purged chronology. Never manufacture hourly observations or backdate later10-Qfeatures to an earlier release.
- Inspect actual owned processes and locks as well as saved status before any worker action. Resume an interrupted attempt only after understanding its failure; never duplicate a worker, reset its journal or overwrite a failed attempt.
- The separately authorized USD100,000 Alpaca PAPER baseline uses a fixed endpoint, eleven-stock universe, seven-file code identity and durable order IDs. Do not migrate/promote it automatically. Uncertain orders, rejected exits, code drift or unexplained funds/holdings require reconciliation.
- Follow Ponytail standard/full principles: reuse the existing models, preprocessing, cash engine and interfaces, prefer readable minimal implementation, and review material changes. Existing learned outputs are not proof of an edge.
- Protect credential values and private broker journals. The owner authorized encrypted GitHub Actions secrets on October1; this does not enable a cloud trading worker or downloadable local-machine keys. Configure local paper keys separately.

## Local tool convention

On the owner's Windows workstation, read `C:\Users\user\.codex\RTK.md` and use its verified RTK proxy. Other machines must follow their own applicable tool/permission instructions. Do not publish machine credentials or dependency runtimes.

## Reproduction and publication

`uv sync --frozen`, frontend install/build and `scripts/verify.ps1` cover the normal application. Research tests have study-specific declarations; preserved failed/pre-review snapshots are not a single active test suite. `docs/handover/artifact-inventory.csv` identifies retained local evidence; a clone does not include the31.8GB raw/model corpus or the existing operator journal. Preserve the owner's initial GitHub license/history when publishing, and verify private visibility before writing secrets/evidence.

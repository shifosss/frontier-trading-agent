# Daily model decision bridge

This local CLI saves an **unqualified historical preview** from a verified frozen USD capture. It does not activate the paper worker or submit orders. Defaults are the predeclared engineering preset: USD 2,000, calibrated ensemble, five sessions, and 40 bps round-trip proportional costs. These settings were not selected as a profitable winner.

```powershell
.venv/Scripts/python.exe -m frontier.cli candidate-build 814780d48b4141b9a82a3fb917d1b85a
# Optional: --signal-session YYYY-MM-DD --budget 2000 --cost-bps 40 --horizon 5
# --strategy ridge|extra_trees|hist_gradient_boosting|multi_head_mlp|equal_ensemble|calibrated_ensemble|diversified_ensemble
```

Each invocation creates a new directory below `artifacts/daily-candidates`. `attempt.json` is written before source loading and records every requested argument and completion or failure type/message; failed attempts are retained. `model/manifest.json` records the payload digest, runtime, ordered features/heads, fit/calibration dates, exact sampled session/symbol identities, raw source hashes, source reuse identity, policy, and hypothetical account. `report.json` contains every eligible ranking, excluded universe member, planning rejection, deterministic intent ID and exact prediction reload check. Model files are trusted local joblib artifacts: integrity checks detect alteration but do not authenticate an attacker-controlled file. Never load uploaded model files.

The builder verifies the frozen capture definition and index against its saved completed summary, follows source reuse to its original hashes, then uses the existing raw-history verifier and normalizer. It retains 1,009 USD sessions per symbol before concatenating: 252 feature warmup sessions, 504 training sessions, 252 calibration sessions, and one signal session. All six training targets finish strictly before calibration; all calibration targets finish strictly before the signal. Sampling remains capped at 96 stocks per date; prediction includes every eligible signal-date stock, independently of future labels. Failed capture membership remains visible.

Whole-share planning uses the same function as historical simulation: five slots, 20% entry notional including entry fees, 0.5% NAV divided by two ATR, and available settled cash. This slice explicitly models an empty isolated hypothetical account. It neither reads nor implies the state of the active paper account. Reference-price quantities are previews; the historical next-close engine still sizes actual fills. Frozen signal sessions are historical and cannot be treated as current orders.

Limitations remain current-member survivorship, adjusted-vintage corporate-action coverage, negative or fragile historical evidence, uncalibrated execution costs and the unresolved TPX source issue. No guessed split repair or economic promotion is included. The next activation milestone requires independent model and economic qualification, current validated data, reconciled holdings/reservations/settlement, and execution-cost evidence. Migrating the active paper policy is a separate, explicitly chosen activation step; offline development and paper integration engineering can continue under the existing authorization.

Focused verification: `pytest tests/test_candidate_daily.py tests/test_model_artifact.py tests/test_daily_policy.py`. Real frozen-universe build evidence is recorded by integration qualification under `.qualification/daily-model-bridge`.


## First full-universe qualification (September 19, 2026)

Run `83d99338fd394e7cad44bdad045b25ad` completed from frozen study `814780d48b4141b9a82a3fb917d1b85a`, whose original sources are retained under `90af4c840aad48f7ab58fba7a682f96a`. Signal session: September 18. The model payload is `8f6baa20861931ca7c52f593d7c8057c8b8e6f5ab59cc0ff07540c9f8942ab7a`.

| Evidence | Result |
| --- | --- |
| USD instruments considered | 5,675 requested, 5,664 usable source histories |
| Signal-day stock forecasts | 2,878 eligible; all other requested members retain rejection records |
| Fitting / calibration examples | 47,808 / 23,616; actual session/symbol identities saved |
| Latest fitting outcome | September 16, 2025; calibration starts September 17 |
| Latest calibration outcome | September 17, 2026; signal is September 18 |
| Saved/reloaded predictions | Exact equality for every model and eligible stock |
| Five-session calibrated-ensemble scores | Maximum -0.011063; no score above zero |
| Hypothetical decision | No entry intents; all USD2,000 remains cash |
| Warning retained | MLP reached its 60-iteration optimization limit |

The default engineering preset remains unchanged after this no-entry result. Its score deducts proportional costs and half the predicted completed-close downside; it is not a predicted portfolio return. Calibration and model error need further research. No fee reduction or filter relaxation was used to force a trade. This run is a reproducible historical decision preview, not a new performance test or economic qualification.

The production change passed the 394-test full suite, with the final failed-request provenance correction also covered by 17 candidate tests. Model persistence passed 32 focused tests. Independent review found two issues (parallel tree prediction reproducibility and incomplete failed-request provenance); both were fixed and reviewed. The shared planner exactly reproduced all curves, trades, fees, activities and cash state in 240 baseline comparisons containing 69,491 trades. Ruff lint and formatting of the 12 changed Python files passed. Existing unrelated formatting differences and dependency deprecation warnings were recorded rather than bundled into this change.

Artifacts: `artifacts/daily-candidates/83d99338fd394e7cad44bdad045b25ad/{attempt.json,report.json,model/manifest.json,model/heads.joblib}`. Supporting qualification evidence is under `.qualification/daily-model-bridge/`, including `verification.json`, `daily-policy-differential.json`, `real-build-summary.json` and independent reviews.


September 28 continuation: [saved-model account rehearsal](candidate-replay-results.md) now carries positions, pending simulated entries and settlements across durable historical chunks, with explicit cost profiles and independent ledger audit. Both predeclared USD2,000 accounts lost money; neither is promoted. [Forecast diagnostics](forecast-calibration-diagnostics.md) and [AIXI source verification](aixi-source-continuity.md) identify separate selection-cost and source-unit problems. The next economic work must qualify action-consistent data and test quantity-aware net-return selection; the next execution integration still needs reconciled broker positions and partial-fill remainders under a separately versioned daily paper policy. Existing paper operation remains the unchanged eleven-stock baseline.

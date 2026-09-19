# Daily model decision bridge

Date: 2026-09-19. Approved by the owner's proceed instruction following the daily-first automation roadmap.

## Outcome
Persist the existing six-output models and their preprocessing, then generate reproducible next-session-close candidate intents from a verified frozen US capture at a default US$2,000 strategy budget. The same forecast scoring and whole-share planning functions must drive the historical daily cash engine and the new decision preview. This is an engineering qualification lane, not economic promotion or a new broker journal.

## Constraints and reasoning
- Preserve the active Alpaca paper operator, its eleven symbols, policy identity, journal and fixed transport. Do not change operator.py, operator_store.py, paper_risk.py, paper_broker.py, swing_policy.py, scan_data.py or sources.py.
- Existing full study stays immutable, including negative results and source failures. Reuse its frozen data; do not rerun the unchanged grid.
- Fit only prior 504 sessions, calibrate on the following 252, purge labels at both boundaries, and use all eligible US stocks for the signal session. Store actual sampled row identities/digests and source hashes. Training sample cap remains 96 per session.
- Persist fitted imputer, scalers, four models and calibrated weights together. In-memory and reloaded predictions must match. Preserve fit_predict_heads API and numerical results.
- Local model files use the already installed joblib library and are trusted local artifacts only. Verify manifest, payload digest, feature/head order and runtime compatibility before loading. A checksum is integrity, not authentication; never accept uploaded model files through the server.
- Default decision policy is calibrated_ensemble, 5-session holding, 40bps round-trip scenario; these are predeclared engineering settings, not selection of a profitable winner. Support 1/3/5 sessions and all existing learned outputs explicitly.
- Every candidate decision records model, data, policy and account snapshot identities, complete ranking/rejection reasons and deterministic intent IDs. No broker submission path.
- Reuse exact every-session screening, independent holdings, 5 slots, 20% entry notional-plus-fee cap, 0.5% NAV divided by 2 ATR, whole shares and only cash settled by the planned fill. Existing holdings and reserved orders count against capacity. Next-close fill sizing remains in the existing simulator; preview quantities are not guaranteed fills.
- The new artifact is unqualified: current-member survivorship, adjusted-vintage corporate-action coverage, negative/fragile historical evidence and uncalibrated execution costs remain explicit. TPX source issue remains unresolved; no guessed split repairs.
- Measure additional cost evidence with a return-independent sample declaration and preserved raw data. Report quote spreads separately from broker fees and fills; do not replace 20/40/100 scenarios based on profitable outcomes.

## Interfaces
ensemble_models: fit_heads(X_train,y_train,X_cal,y_cal,seed=1729) -> FittedHeads; predict_heads(bundle,X) -> dict model name to Nx6 arrays; bundle.audit contains existing calibration/warnings/config/model_audit/preprocessing. fit_predict_heads delegates to these.
model_artifact: save_heads(bundle,path,metadata) -> manifest; load_heads(path) -> (bundle,manifest). metadata is JSON containing feature_names, head_names, source/capture identities, fit/calibration/signal boundaries and sample audits. New target directory only.
daily_policy: forecast_score(predicted,head,cost_bps) -> array; plan_entries(*,symbols,ranking,prices,atrs,nav,available_cash,held_symbols=(),reserved_symbols=(),slots=None,cost_bps=40,correlation_allowed=None,audit=True) -> dict with orders, decisions, remaining_cash. ranking contains eligible positive-score symbol indices. orders carry symbol_index,symbol,quantity,reference_price,reserved_cash. correlation_allowed(index,peer_indices) matches the existing trailing correlation rule. Duplicate symbols cannot create duplicate positions. Omitted slots deduct held/reserved names from five. Explicit slots are caller-computed free capacity at the planned fill, including scheduled exits and existing reservations; held names remain excluded. audit=False avoids serializing full rankings inside historical loops. The simulator translates to its existing pending format.
candidate_daily: build_candidate(workspace,capture_run_id,signal_session=None,budget=2000,cost_bps=40,horizon=5,strategy='calibrated_ensemble') -> JSON report. CLI candidate-build invokes it. Save bundle and report below artifacts/daily-candidates. No HTTP mutation endpoint or worker activation in this slice.

## Acceptance
Unit coverage for fit/reload equality, tampering/schema rejection, empty predictions, cutoff validation, exact cash planning, insufficient funds, holdings/reservations and deterministic IDs. Differential test unchanged daily simulator outputs against the pre-edit implementation. Integration trains and reloads a real frozen US universe artifact and records forecast/intent equivalence. Existing tests, lint and independent spec/code review must pass. Document commands, result evidence, limitations and the next activation milestone.

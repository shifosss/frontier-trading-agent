# Model bundle implementation

Implemented `FittedHeads`, `fit_heads`, `predict_heads` and delegating legacy `fit_predict_heads`. Fitted train-only preprocessing, four models, calibration weights and prior audit are persisted together.

`save_heads(bundle, path, metadata)` requires a new directory. It writes `heads.joblib` and `manifest.json`; metadata requires unique ordered `feature_names` and exact `head_names`. Additional JSON metadata survives roundtrip. `load_heads(path)` checks schema, runtime (Python major/minor and exact numpy/scipy/sklearn/joblib versions), feature/head/model order, metadata hash and payload hash before deserializing the exact verified bytes. It then validates payload metadata, feature count and calibration state. Local trusted artifacts only; checksums are not authentication.

Validation:
- `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ensemble_models.py tests/test_model_artifact.py -q`: 31 passed in 10.25s.
- Direct comparison against pre-edit original implementation using deterministic 512 training / 128 calibration / 16 test rows: ridge, boosting and MLP identical; extra trees max absolute delta 1.39e-17 (parallel accumulation); ensemble deltas <=6.94e-18. Config, preprocessing, model audit and warnings equal.
- Roundtrip test verifies all six predictions, full audit and JSON metadata; empty prediction matrices supported. Corruption/schema/runtime/order tests assert deserializer was never reached. Existing destination and malformed metadata rejected.

No frozen paper, journal, old research artifacts, or broker paths changed. No commits made.

## P1 deterministic inference correction

ExtraTrees still fits with n_jobs=2, then switches to n_jobs=1 before calibration and subsequent inference. This fixes the estimator accumulation order and is recorded separately in config.extra_trees_prediction_n_jobs and model_audit.extra_trees.fit_n_jobs/predict_n_jobs.

Focused tests: 32 passed in 3.98s, now asserting exact array equality after reload and across repeated inference/repeated seeded fits, including exact calibration/audit equality. Original pre-refactor differential rerun passes rtol=1e-12, atol=1e-15; small floating-point tree/ensemble differences remain expected against the original parallel predictor. No policy/broker files changed.

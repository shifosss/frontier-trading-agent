# Candidate bridge implementation evidence

Implemented `src/frontier/candidate_daily.py`, local CLI `candidate-build`, `tests/test_candidate_daily.py`, and `docs/daily-model-bridge.md`. No operator, paper, scan-data or sources files edited.

Verification: `python -X utf8 -m pytest tests/test_candidate_daily.py -q`: **17 passed**, latest execution 1.59 seconds. Final Ruff check and formatting passed. CLI help verified candidate command registration and defaults.

Coverage includes all-horizon chronological purge, exact sampled identities and 96/session cap, invalid request rejection, immutable per-invocation report locations, deterministic intent IDs under identical model/data/policy/account, complete eligible plus rejected universe coverage, empty signal universe, reload discrepancy failure retaining attempt evidence, original source reuse hashes, future/non-session/too-early cutoff rejection, source-hash failure propagation and bounded USD normalization.

Capture loading uses existing `_reuse_source_run` plus `read_history`. Original source definition/index digests are checked against the reused run; every selected USD raw history is hash checked before normalization. Per-symbol rows are reduced to 1009 sessions before concatenation. Fit 504/calibration 252 periods follow 252 sessions of feature warmup. All target outcomes precede both boundaries strictly. All eligible signal stocks are forecast regardless of future labels. Missing captured membership remains in universe rejection audit; TPX issue remains explicit.

Real frozen-universe build is pending root-coordinated integration launch after deterministic model prediction verification. Unit integration uses lightweight test doubles; it does not claim real fit/reload evidence. Root owns full tests and real build qualification.

Final P2 review: attempt.request captures every input before validation with strict JSON; NaN and positive/negative infinity are explicit strings. Invalid request tests assert complete reconstructible failed configurations. Documentation separates chosen policy activation from authorized development.

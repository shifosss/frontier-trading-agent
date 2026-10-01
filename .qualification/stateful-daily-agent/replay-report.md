# Replay implementation report

Implemented the isolated candidate_replay module, user documentation, and focused
tests. API includes replay_id for named resume and max_chunks for durable bounded
stepping. Root integrates the command and runs a genuine earlier saved model
against later frozen sessions after production source hashes are stable.

Validation: .venv/Scripts/python.exe -X utf8 -m pytest tests/test_candidate_replay.py -q
passed 16 tests. Synthetic forecasts drive the real daily engine through nonempty
positions, actual exits, settlement and later reentries. One-shot and changed-size
restart results match curves, trades, activity and final state exactly; summed
fees agree within 1e-12 because chunk addition changes floating accumulation grouping.
Actual SQLite locking excludes a second writer; a failure after a durable commit
resumes without duplicated outputs. Invalid target chronology, code identities,
paths and journal ordering/integrity are rejected.

No fit, broker activity, operator database access, paper changes, or promotion.
Current-member adjusted-vintage and incomplete-cost limitations are recorded in
reports and documentation. All failed journal attempts remain durable. Real
source/model replay and independent review remain root integration checks.


Integration corrections: preparation now invokes the verified history loader once,
retaining the original warmup start while extending to replay end. Reconstructed
original evidence changes only signal_session before comparison. Each failed or
successful invocation stores its full requested arguments; nonfinite inputs are
explicit strings. Replay code identity also includes historical_settlement.py.
Single-pass and failed-request provenance regression tests pass. Ruff clean.

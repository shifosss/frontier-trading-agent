# Saved candidate replay

`frontier.candidate_replay.replay_candidate(workspace, candidate_id, *, end_session=None,
cost_profile='proportional', round_trip_bps=40, chunk_sessions=21, replay_id=None,
max_chunks=None)` runs an exploratory historical account using a trusted local
candidate in `artifacts/daily-candidates/<candidate_id>/model`.

The saved model is loaded with artifact integrity/runtime checks and never fitted
again. All saved training/calibration targets must end before the first signal.
Every recorded training implementation hash must still match. Rebuild a candidate
when implementation compatibility fails; existing artifacts remain unchanged.
The original capture is reverified, including its original reused source. Causal
features retain the candidate's original warmup start in one verified normalization
pass per invocation and extend through the
requested completed frozen session. Predictions consume features only, never labels.

The resulting `replay_id` identifies a separate directory under
`artifacts/candidate-replays`. Its `journal.sqlite` stores immutable identity,
each chunk's complete state and outputs, forecasts, and invocation attempts with
full requested arguments, including failed requests and explicit nonfinite values.
`writer-lock.sqlite` holds a real SQLite writer transaction for the entire
invocation; concurrent writers fail immediately. Process death releases that lock.
Each journal chunk commits its cursor, positions, reservations, cash, settlement
receivables, curves, trades, and costs atomically. The human-readable `report.json`
is a regenerable view, not the source of truth. This code never opens `operator.sqlite`.

For a bounded run, pass `max_chunks=1`. Resume by supplying its `replay_id` plus
the same candidate, end session, and cost arguments. Chunk size may change. The
full simulation end always remains fixed; a chunk boundary does not liquidate
positions or suppress otherwise valid signals. Resume validates identities,
chunk hashes, exact chronology and the state chain. A crash after commit but
before report replacement resumes after the durable chunk. Repeating a completed
replay returns its existing result without duplicate trades. Failed invocations
are preserved in the attempts table. A missing-data chunk is not committed.

Forecast ranking uses the declared proportional round-trip scenario. Fixed broker
fees affect actual modeled entry affordability and the cash ledger, but do not
rerank the frozen forecasts; the result is not fee-optimal selection. Costs carry
their complete serialized tariff identity and exclusions. Historical application
of current tariffs is a counterfactual. Adjusted-vintage prices and original-share
quantities do not reproduce corporate-action-complete broker accounting. These are
current-member research rehearsals, not paper activation, trade instructions,
broker fills or promotion evidence.

`tests/test_candidate_replay.py` exercises real nonempty engine order lifecycles,
durable restart with changed chunk sizes, exact curves/trades/final-state equality,
fees within floating accumulation precision, recovery after a committed-chunk
failure, writer exclusion, chronology/integrity failure and model cutoff checks.

The private daily engine validates cursor, market layout and policy, not array values.
Its caller owns source and signal immutability. This supported replay wrapper enforces
the frozen source, model and implementation identities before using the engine.

This rehearsal has atomic next-close simulated fills, with affordability reductions.
It does not reconcile broker positions or partial fills, preserve unfilled remainders
across sessions, or activate the separately required daily paper migration.

Replay identity also records Python and numerical/data/calendar dependency versions,
plus the derived settlement-index digest. Resume rejects changes before another chunk
can commit. This was added after independent review and before the real rehearsal.

## Cost identity version 2

September 28: cost specifications now serialize equivalent numeric inputs identically, including `40`/`40.0` and signed zero. API and CLI invocations can resume the same newly created journal. Fee arithmetic and trading rules are unchanged. Raw request arguments remain in the attempt records.

Previously completed journals keep their version-1 identities and exact source hashes. They are not silently migrated or relabeled. Their matching implementation is preserved in `.qualification/stateful-daily-agent/qualified-code-20260928/source.zip`, with a verified SHA-256 manifest matching both real replay journals and all eleven saved-model dependency hashes. Reproduction of an old journal requires that recorded implementation and runtime in an isolated checkout; new code intentionally rejects its old identity. This serialization change does not require refitting the unchanged saved model.

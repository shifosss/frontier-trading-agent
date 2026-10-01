# Independent integrated review

Reviewed September 19, 2026 against the daily-model-bridge spec and plan, supplied baseline-relative model/policy/candidate diffs, current source and tests, and implementation/qualification reports. This review covers candidate chronology and provenance, core interfaces and model correction, cash-engine integration, identity semantics, retained failures, and cost-evidence scope. No production edits, broker actions, study reruns or redundant full test runs were performed.

## Specification verdict

**Implementation approved after the two review corrections. Final integration qualification remains pending the real frozen-universe build and root-owned full checks.**

The candidate uses the captured USD universe, retains failed members in the rejection universe, validates source reuse identities and original raw hashes, and trims histories before combining them. Calendar-completed signal cutoffs, 252 warmup / 504 fit / 252 calibration sessions, all-six-target boundary purging, and the existing 96-per-date sampler are consistent. Actual sampled session/symbol identities and hashes are saved. Signal eligibility does not depend on future labels.

Forecast scoring and whole-share reservation planning are shared with the historical engine. Stable ranking, t+1 close entry and t+1+h close exit, five slots, entry fees within the 20% cap, 0.5% NAV / two ATR sizing, and settled available cash are consistent. The preview explicitly uses an empty hypothetical USD account; it does not imply reconciliation with the active paper account. Reference-price quantities remain subject to next-close resizing.

The report connects data, policy, hypothetical account and model identities. Intent hashes include those identities, signal/fill/exit sessions and exact order details. New per-attempt directories prevent overwriting prior candidate results; model and report destinations reject overwrite. Every eligible symbol is ranked and every other declared member receives a rejection reason. No HTTP activation or broker submission path was added.

Model persistence retains preprocessing, four models and calibration weights. The loader validates schema, runtime, order, metadata and exact payload bytes before trusted-local deserialization. Exact reload equality is enforced by the candidate. Checksums are correctly described as integrity checks rather than authentication.

The cost study retains its predeclared 54 cells, raw responses and wide/sparse results. The reported independent Decimal verification and separate fee arithmetic support the limited measurement claim. Quotes are not fills; the production 20/40/100 scenarios remain unchanged. The artifacts remain explicitly unqualified and preserve survivorship, adjusted-vintage, negative/fragile evidence and TPX limitations.

## Code-quality verdict

**No remaining material code finding in the reviewed implementation.** Responsibilities are divided into fitted models, trusted persistence, reusable policy and local candidate orchestration without a second order system. Existing loaders, calendar construction, sampling and cash accounting are reused. The policy extraction is narrow and the supplied exact differential evidence covers 240 cases / 69,491 trades, including arrays, trades, fees, activities, cash state and metrics.

Two concrete findings were raised and corrected:

1. **P1, deterministic inference (core review): closed at code/focused-test level.** ExtraTrees fits with two jobs, switches to one immediately before calibration, and retains sequential inference in the saved model. Audit distinguishes fitting from prediction parallelism. Reviewed tests assert exact repeated-fit audit/calibration/weights and repeated inference, plus exact reload equality. The model report records 32 passing focused tests and numerical compatibility against the former parallel implementation at rtol=1e-12 / atol=1e-15. This small documented floating-point difference is not a strategy-selection change.
2. **P2, incomplete failed-request provenance (this review): corrected.** The original attempt record omitted budget, costs, horizon and strategy, making early failures with identical error text ambiguous. The current request object saves every public build argument and resolved workspace before validation; nonfinite numeric arguments are represented as strings so strict JSON remains valid. Reviewed assertions verify complete request retention for invalid inputs. Unique attempts, error type/message and completion timestamps remain retained.

## Evidence boundary

Focused implementation results and policy/cost differential results above were inspected, not rerun by this reviewer. Candidate tests use doubles and do not establish real fitted-universe integration. Root must still record a successful real frozen USD build, exact in-memory/reloaded forecasts and resulting intent equivalence, full suite/lint results, and unchanged frozen paper/study state before calling engineering qualification complete. These remaining execution checks are not an economic promotion or permission to activate paper trading.


## Final real-build qualification follow-up

The real-build and test gates above are now satisfied by the recorded evidence. **Final specification verdict: approved for the implemented local engineering bridge. Final code-quality verdict: approved, no remaining material findings.** This supersedes the earlier pending real-build/full-check disposition; frozen paper/study preservation remains the root final change-boundary check.

Inspected real-build-summary.json, verification.json, and the actual report, manifest, payload bytes and completed attempt for artifact 83d99338fd394e7cad44bdad045b25ad. The real build completed from capture 814780d48b4141b9a82a3fb917d1b85a using the predeclared USD2,000 / calibrated ensemble / five-session / 40bps settings. Signal 2026-09-18 schedules entry 2026-09-21 and exit 2026-09-28. It retains 5,675 requested USD members, 5,664 usable histories, 2,878 ranked eligible members and 2,797 rejected members. Training/calibration contain 47,808 / 23,616 sampled rows. Latest training target 2025-09-16 precedes calibration start 2025-09-17; latest calibration target 2026-09-17 precedes the signal.

This reviewer independently checked, without refitting or re-predicting:

- Exact agreement between report manifest, saved manifest and metadata; saved payload SHA-256 equals reported model identity 8f6baa20861931ca7c52f593d7c8057c8b8e6f5ab59cc0ff07540c9f8942ab7a.
- Recomputed data/policy/account identity hashes and all ten implementation-file hashes against current files.
- Recomputed both sampled-identity digests and confirmed at most 96 sampled stocks per session, with both chronological target cutoffs.
- Recomputed every saved ranking score from its six forecasts using the shared scoring function with exact numeric equality, checked descending order and the complete unique 5,675-member ranking/rejection union.
- Confirmed every ranked member has a nonpositive score, every reason is nonpositive_score, both intents and planning decisions are empty, and remaining cash is USD2,000. The hypothetical account has no holdings, reservations or receivables.
- Confirmed the completed attempt retains the full build request and model identity. Source evidence retains 200 original capture failures across currencies. The MLP maximum-60-iterations convergence warning remains visible.

The actual build records exact in-memory versus reloaded predictions for every model output; the enforcement branch in reviewed code fails before producing a successful report if equality fails. Therefore both sets of forecasts necessarily yield the same empty intent set under the deterministic shared planner. This is a valid real all-cash integration outcome, not evidence of a nonempty real order path; meaningful nonempty sizing and identity cases remain covered by the focused policy/candidate tests and exact simulator differential. No settings were retuned to manufacture trades. The maximum score was -0.01106253217869278.

Recorded final checks: 394 full-suite tests pass, 96 existing dependency/pandas deprecation warnings; 17 candidate and 32 model focused tests pass; source/test lint passes; formatting passes for 12 changed files while four unrelated pre-existing formatting differences remain untouched. These root-run results were inspected, not redundantly rerun. Historical-policy differential remains exact for 240 cases / 69,491 trades, and the 54-cell cost verification remains separate.

Engineering fit/save/load/score/plan/report completion is established for the real frozen capture. The resulting artifact correctly remains unqualified: negative signals, the model warning, survivorship/data-vintage limitations, unresolved TPX and uncalibrated execution costs do not justify promotion, live use or paper activation.

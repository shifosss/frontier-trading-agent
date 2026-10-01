# Frozen economic runner

Run only after the root agent reviews and binds the terminal qualified corpus and complete execution definition:

`python -B -X utf8 .qualification/earnings-quality20260928/economic/run_study.py --definition PATH`

No paper/broker interface, source capture, paid resource or network request is used.

The root-owned JSON definition has schema=1, reviewed_for_execution=true, rerun_of=null for an original attempt, paths, inputs and dependencies. Mandatory path keys are exposed as PATH_KEYS. inputs maps repository-relative or absolute file paths to SHA-256; dependencies must equal runtime_dependencies(). Bind every path except the source directory, all four terminal source request/implementation/registry/completion files, and every path returned by required_code_paths(). The terminal collector definition/summary/events/issuer-status/source-inputs and the completed source-only market artifacts are independently cross-checked, including nested raw source identities. The frozen model specification is fixed by its declared SHA.

Both source SQLite databases are held in read-only transactions and the main historical worker lock is exclusive. One atomic definition-digest claim is retained even on failure. Repeating that same definition is refused. A changed reviewed definition can reference an earlier attempt with rerun_of, but must provide reviewed_rerun_reason; no automatic repeat or failed-attempt deletion occurs. The root remains responsible for inspecting actual process ownership before launch.

Each unique attempt first writes its definition and all ten model/twenty account declarations. It preserves all prepared original events, including unavailable financial/clock/price inputs. FoldLabels delegates partitioning to the existing model fitter, verifies causal status and label-end boundaries again at outcome lookup, and records every fitting/calibration access. Both models are fitted once per year and saved/reloaded before forecasting. Both families' forecast files and a durable hash barrier are written before that year's test labels are extracted.

There are five fixed expanding folds and two fixed families, with all insufficient and internally failed bundles retained. The five yearly forecast lists are combined per family with one artifact hash shared across four cash/cost paths. The unchanged account adapter runs all twenty full 2021–2025 accounts plus the January16,2026 tail. Each account's actual failure is retained; unresolved same-decision collisions are never selected around. A fatal source/model-artifact error leaves the global failure and declared matrix plus every completed prefix artifact.

Reports preserve account weekly objectives, full ledgers and policy audits; all original issuer/year denominators including zero-event years; per-head raw/corrected errors and fitting-only means on exactly matched rows; calibration-only bins with missing labels; scheduled overlapping interval and issuer/date counts; and costless fully invested SPY adjusted-price/cash references on the exact full account interval. These references do not simulate dividend cash or brokerage fees. Raw versus corrected forecasts are never altered by diagnostics. The completed-account status is computational completion, not promotion or proof of profitability.

Tests use generated financial values and market prices over the retained official calendar. They exercise two real sklearn fits, eight declared insufficient fits, exact reloaded forecasts, all twenty full-date synthetic accounts, no-early-test-label access, purge refusal, source lock behavior, preserved failures, matched diagnostics and reference gaps. No actual cohort financial outcome is used by these tests.

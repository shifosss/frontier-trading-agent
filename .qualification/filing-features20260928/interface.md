# Filing feature contract

`features.py` is a source-only module. `qualify_filing(manifest, source_root, repo_root)` reads the exact preserved original fact source and returns source identity, original fact/context/unit spans, fiscal slot and `u`, or retained unavailable reasons. `build_features(records, calendar)` preserves every original and calculates only the first original's causal eight-slot score. Calendar is the sessions list inside the root-provided calendar JSON.

Each result preserves `symbol`, `accession`, `filing_date`, `report_date`, `u`, `S`, `availability_floor`, `decision_time`, `entry_session`, `exit_session`, `history_accessions`, and original `source_sha256`/`source_path`/`source_url` with selected fact/context/unit evidence.

- `status == qualified`: the current original's financial inputs and clock are qualified.
- `feature_status == qualified`: all eight immediately preceding scheduled Q1/Q2/Q3 innovations are qualified and known, with nonzero sample SD; S is computed. Both treatment and control require this.
- `selected == true`: Decimal(S) >= 1. Only the treatment requires this. The control also admits qualified S below1.
- `feature_status == unavailable` or `duplicate_original`: no signal eligibility. Reasons and original records remain visible.
- `execution_status == qualified`: the conservative09:00ET decision, actual entry close and fifth subsequent exchange-session exit are inside the supplied calendar. Both accounts additionally require this. Other statuses are calendar_unavailable, calendar_starts_after_availability, entry_outside_calendar or exit_outside_calendar.

This is financial-input qualification, not historical ordinary-share mapping, complete corporate-action accounting or proof of original public dissemination time. There are no price-return labels or model fits. Baseline manifests remain unchanged and any overlay must retain baseline plus effective provenance.

# Independent bounded source-batch verification

Passed after one preserved classification correction. No network, model/P&L/account reads, source correction or production edits were used.

- Reproduced all 91 frozen sample identities and minimum SHA-256 ranks across populated strata. The batch is exactly the 24 sampled USD events from 2016-01-04 onward, spanning 23 symbols. All 67 other cases remain visible and pending; no substitutions.
- Verified all 48 GET request parameter sets, SIP feed, raw/split adjustment, fixed entity `asof`, UTC bounds corresponding to declared New York local dates, pagination completion, response hashes and 584 retained bars. Rechecked all 23 original source hashes and source event/boundary identities.
- Independently recomputed price/volume intervals with Decimal and unchanged tolerances. Price factors: 8 consistent, 11 inconsistent, 4 missing boundaries, 1 precision-insufficient. Nominal boundary prices: 37 agree, 3 differ (EVO twice; TOPS effective), 8 missing. These are source/precision findings, not automatic bad-price diagnoses.
- Found TOPS adjusted volume was 1 ± 1 shares on both boundaries, making its factor unidentifiable. It had been labeled inconsistent; the analyst changed it to unresolved precision-insufficient and retained the pre-review results. Final independent checks now match. `verification-before-tops-fix.json` preserves this finding.
- Verified hashes for all 25 retained primary notices and the 91-row status ledger. Spot-checked the five material distribution/composite interpretations against retained text: DHR/FTV, IP/SLVM, OLOX/SGDevCorp, ENOV/ESAB and HON/HONA. A provider adjustment factor is not automatically a same-security share ratio. No full legal entitlement or corporate-action accounting audit is claimed.

Fixed symbol/asof requests are entity-mapping assumptions, not proof of predecessor class continuity. Fresh adjusted data does not establish historical availability. Price consistency, basic action notices and complete share/cash accounting remain separate dimensions. All complete action-accounting classifications remain unresolved. This bounded audit is finished; no additional source batch or code-quality work was started.

Evidence: `verify_batch.py`, `verification.json`, `notice-and-visibility-check.json`, and the retained pre-correction verification.

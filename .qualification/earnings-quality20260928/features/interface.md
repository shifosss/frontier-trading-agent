# Original cash-backing Q feature contract

`cash_backing.py` imports the exact frozen original S parser by path and SHA. It reads original filing facts only; no network, price arrays, return labels or model fits.

- `enrich_filing(manifest, source_root, repo_root)` validates the original manifest with the frozen parser, then appends Q fields.
- `enrich_record(record)` accepts a retained record from the hash-bound original S qualification, rechecks its original source hash, and appends Q. The caller must bind the original record artifact identity; this is not an untrusted-record validation API.
- `qualify_document(raw, representation, cik, report_date)` is the source-fixture API.
- `build_features(records, calendar)` invokes the frozen first-original/eight-slot S builder, then annotates joint eligibility. Missing older Qs never alter S history.

Every original S, clock and history field is preserved. New `q_status` is `qualified` or `unavailable`; `q_reasons` retains failures. `Q` is a Decimal string or null. Qualified fields include `q_current_cfo`, `q_current_ni`, `q_prior_cfo`, `q_prior_ni`, `q_prior_fy_assets`, both exact YTD period endpoints, and `q_selected_facts` with original fact/context/unit byte spans. `q_all_facts` retains decoded original CFO facts for source review. Synthetic alias offsets are never exposed as source evidence.

`joint_feature_status == qualified` requires original `feature_status`, `q_status` and `execution_status` all qualified. This is source-feature qualification; the downstream five-input model population additionally requires the three causal price inputs. The original `selected` flag remains the old S>=1 rule. Apply Q>0 only for the explicitly declared cash-backing control; do not redefine the wider population or substitute unavailable Q with zero.

Existing-252 compatibility attempt `compatibility/86b8406531564d54ba01540b9622b936` retained every original and proved all original record/event fields exactly unchanged. Q qualified146, unavailable106; all146 rational values and3186 original source spans passed.2017-2025 joint eligible111 versus original S-eligible121. All73 exact-CFO gaps have only the prohibited ContinuingOperations alternative;29 inherited S failures and4 exact-YTD-NI gaps remain. No returns were inspected. This existing six-issuer compatibility population does not select the new100 issuers.

Q measures a seasonal change in cash backing, not demonstrated earnings quality. Consolidated operating cash flow and parent-attributable NI can differ conceptually; working capital/tax timing, current-filing comparator revisions and all inherited source/security/action limits remain explicit.

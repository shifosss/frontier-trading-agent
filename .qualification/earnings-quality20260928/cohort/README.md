# Earnings-quality cohort preparation

This directory selects sources, not trades. It belongs to the fixed 100-issuer cash-backing experiment. The user's later USD10,000 primary research balance and USD2,000 comparison do not change issuer selection.

The frozen exchange snapshot supplies 5,661 USD entries labeled stock, but combines common/ordinary shares and depositary securities in one coarse category. It has no CIK, SIC or incorporation fields. Saved Yahoo chart metadata calls an ordinary company, a REIT, an ADR and a closed-end fund `EQUITY`; that field cannot resolve the cohort. Original source paths/hashes and these schema limitations are saved in `inventory.json`.

The parent agent separately captured the official current SEC ticker/exchange map. `criteria.json` declares the complete order of operations: explicit exchange common-share title and exclusions, exact ticker/CIK mapping, 2016 dollar-activity eligibility, one qualifying share class per CIK, then deterministic CIK hashing. The first 300 CIKs form a fixed classification pool. Only their current SEC profiles can qualify the eventual first 100. Missing or rejected members remain visible; the 300-member pool is never refilled. Financial-fact extraction success and strategy outcomes cannot affect membership.

Current profiles must identify the exact ticker/CIK, an operating entity incorporated in a US state or DC, and a numeric SIC in 0100–5999 or 7000–8999. Business addresses do not prove incorporation. These are current source classifications, not dated historical classifications. Preserve original filing-header SIC and share-cover evidence later; conflicts remain visible without rewriting the cohort.

`cohort.py --definition <path>` is an offline pool command. Before using it, the parent freezes `definition.json` with `paths` for criteria/listing/capture_index/capture_workspace/calendar/ticker_exchange and an `inputs` mapping of repository-relative file paths to SHA256, including code and tests. The command refuses missing/changed frozen inputs, checks raw-source hashes, records a unique attempt, retains all requested/excluded symbols, and writes an immutable `pool-completion.json`. Reuse requires the same definition and unchanged saved output identities. It reads only 2016 price/volume observations for its liquidity statistic. It does not use future return labels, financial facts, broker access or network requests.

`qualify_pool(pool, profiles, criteria)` is the later pure classification function. The caller must bind each profile to its saved source URL/path/hash before freezing the final cohort; passing a Python dictionary alone is not source qualification.

The synthetic checks cover future-price/dividend/split-input invariance, observation quality, exact rather than heuristic ticker joins, share-class deduplication, SIC/incorporation/type exclusions, stable hash order and an insufficient fixed pool without replacement. No cohort names were selected to design these tests.

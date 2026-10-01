The bounded probe succeeded in retrieving all six expired SPY contract records: three HTTP200 responses, 4,421 raw bytes, no pagination, no missing or ambiguous contract identities. It ran once on September29,2026 at00:55:30–00:55:36 UTC (September28 Toronto). No historical quote request, order, account query or retry was made.

Independent verification checked the frozen request/code/source hashes, exact GET URLs and query parameters, all raw response hashes and byte counts, request spacing/deadlines, six unique identities, strikes, expiry, call/put types, contract sizes, deliverables and exact retention in the summary. All checks passed. Evidence is in independent-verification.json and the unchanged raw response files.

Every record reports size="100" and one equity deliverable of100 SPY shares with100% allocation. Every record also reports multiplier="0". Both are retained literally: size must not silently replace multiplier, and neither zero-premium nor100-times-premium cash conversion is qualified by this response. The provider field semantics remain unresolved.

Every deliverable reports settlement_type="T+1" at retrospective retrieval. This does not establish the terms or settlement rules that applied in February/March2024. Open-interest and close-price fields are dated March15,2024, later than the February fixture; they must not be used as features known during that fixture.

This establishes retrospective metadata access through the existing credentials. Historical OPRA quotes, historical as-of chain membership, contract-action history, executable fills, exercise/assignment accounting and strategy profitability remain unqualified. No further request was attempted to resolve those gaps.

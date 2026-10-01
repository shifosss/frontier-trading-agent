# Bounded source plan for the100-issuer earnings-quality study

This is source preparation for the accepted next-stage design. No new SEC request, fact extraction, model fit or price-return join has run here. Final100CIKs are pending the separate cohort stage. The draft cannot launch: the adapter requires exactly100 unique CIKs and a hashed frozen cohort file.

## Reuse and measured scale

The six-issuer pilot plus its reviewed supplement made894 new GETs and now expose900 successful unique URLs. The catalog retains931 resource observations, including all original503/timeout failures and their later separately authorized successes; no successful same-URL payload conflict was found. All six current submissions roots are included, including MSFT/F sources that were not in the original request reuse list. Source paths remain references to unchanged artifacts, with URL/hash/size/retrieval time and the original resource-record identity. The capture verifies raw bytes before reuse.

Successful distinct payloads total1,147,336,187bytes. There are252 original filings,251 captured; the remaining Microsoft original lacks an XBRL instance and is not silently replaced. Per-filing retained source sizes range0.745MB to13.529MB, with3.880MB median. Pilot-based linear scaling is roughly15,000 successful URL requests and19.1GB for100 comparable issuers before cache reuse. This is a planning estimate, not guaranteed cohort volume or download time.

| Fixed ceiling | Value |
|---|---:|
| Selected unique issuer CIKs / root submissions |100|
| Overlapping additional history pages per issuer |8|
| Original10-Q accessions per issuer / total |60 /6,000|
| Original document requests per accession |Index, header, primary, at most one instance|
| Lifetime network request starts |24,900|
| Minimum interval between new requests |1second|
| Maximum response body / newly stored raw bytes |32MiB /40GiB|

At1request/second,15,000requests have a4.17hour rate floor and24,900have a6.92hour floor; network and parsing add time. Reused sources need no GET. Interrupted attempts consume this same fixed total, so the ceiling may leave explicit incomplete coverage. The owner has approved free existing access; this proposal buys no service.

## Small implementation and its boundaries

capture.py wraps the already frozen Cache, discover and capture_filing helpers from filing-source20260928 and the independently reviewed exact-registry-primary selector from filing-source-supplement20260928. It retains the existing durable writer. It adds only the100CIK/request bounds, source URL scope, shared SEC lock, separate capture lock and a simple orchestrator that keeps incomplete issuers visible.

Allowed metadata requests are the100 named CIK roots and history files actually declared by those roots with overlapping2012–2025 filing dates. Missing/invalid ranges or more than8 pages remain failures. A new archival request must belong to an original10-Q registered from a complete issuer discovery, inside the exact filed interval. Only its index/header/registry primary or its cached-index unique originalEX-101.INS is permitted. Known exact original index aliases remain reusable; no PDF, taxonomy, later amendment, companyfacts or unrelated accession fallback is introduced.

All original10-Q rows, duplicate periods and amendment metadata are preserved before document acquisition. A non-access discovery failure does not erase the other fixed issuers: it stays incomplete in the100-member registry while complete discoveries can be captured. HTTP403/429, identity/budget failures and permanentSTOP.json halt globally. The helper already preserves partial filing manifests and errors. No issuer is replaced because facts or source coverage fail.

Completed source results, including503/timeout records, are never automatically retried. max_attempts_per_url=2 means only one interrupted request_started without a durable resource result can receive a later resume attempt. If both starts are unresolved, or the total ceiling is exhausted, stop for explicit reconciliation. Prior pilot failed observations remain in the catalog even when an already authorized successful supplement now supplies the same URL.

The implementation acquires earnings-quality20260928/sec-source.lock.sqlite and source/capture.lock.sqlite. The metadata worker should use the shared SEC lock; broad capture also waits for completed profile acquisition and a frozen final cohort/reuse list. Root owns durable launch. Existing active paper and historical-account workers are separate.

## Current mapping versus dated classification

The separate cohort stage uses the frozen listing and2016liquidity rule, a deterministic CIK hash, a fixed first300metadata pool and then100 eligible unique CIKs. Root's current rule is at least200valid2016sessions and median vendor quote-close times volume at leastUSD5million. The source adapter does not change or implement the cohort ranking.

SEC current ticker/CIK associations are issuer locators, not historical common-share classifications. A single CIK can list debt/preferred securities alongside common stock: the saved T response contains T/TBB/T-PA/T-PC; Ford contains F/F-PB/F-PC/F-PD. Current entityType='operating' also includes BANF, a bank with SIC6021. Thus it cannot replace the explicit common-share/type/SIC exclusion rules. Current incorporation is a current admission fact and must not be inferred from a business address or treated as historical domicile.

The original SGML headers already downloaded for clocks also contain ASSIGNED-SIC in all18 checked first2012/2016/2025pilot filings. classification-evidence.json retains exact URLs/hashes/tags. They provide dated issuer-industry evidence without extra requests; original report covers provide dated security-class evidence where present. Record contradictions/absence explicitly and apply the predeclared event-level classification rule. Do not rewrite the frozen cohort, substitute current SIC into history, or replace an issuer after later source inspection. CIK continuity alone does not prove unchanged economic entity, traded share class or ticker lineage.

Current-member and later-retrieval limitations remain. The saved official SEC API/access guidance in filing-feasibility20260928/results.md documents original-accession retrieval, conservative filing/acceptance clocks, non-recycled CIK identity and ticker-map scope limitations. Root has separately rechecked current SEC access rules; this adapter stays at1request/second and preserves its honest existing user-agent and403/429 stops.

## Review and freeze before launch

Eight offline tests pass:100-root and budget limits; exact source reuse without GET; root-declared overlapping history and invalid-range/page ceilings; registered original documents, exact-primary/PDF and legacy-index handling; original form/date/count limits; completedfailure/403429behavior; interrupted-only retry/lifetime bounds; shared/capture lock exclusion. These tests do not acquire a corpus.

After root finishes cohort metadata, merge its successful exact URL records into the catalog, retaining every observation and rejecting unexplained successful URL/hash conflicts. Fill request.json from request-draft.json with the exact100 issuers and cohort path/hash. Freeze wrapper/test/request/catalog plus the old capture, selector, durable-writer and cohort/profile identities. Have the additions independently reviewed, then root can launch the one durable capture. Source qualification of NI/CFO/context periods and trading strategy execution remain separate subsequent stages.

# Disclosure novelty and timing — source-only audit

The completed [cash-backed earnings study](earnings-quality-results.md) did not justify strategy promotion. One untested explanation is that some income information was already public before the original 10-Q. This audit checks candidate timing in retained SEC submissions metadata. It cannot establish which fiscal period or financial components an earlier release disclosed, explain the strategy losses, or demonstrate an earlier-time trading edge.

The cached audit is now complete; read [the results and preserved verification failure](disclosure-novelty-results.md).

## Frozen question and population

The [definition](../.qualification/disclosure-novelty20261001/definition.json) was saved before candidate extraction, followed by a [timestamp clarification](../.qualification/disclosure-novelty20261001/clarification.json). It requests every one of the same 4,057 original 10-Qs filed in 2012–2025 for the fixed 100 issuers. No issuer, filing or source failure is replaced. The declaration binds 4,243 existing input files, including 179 unique original SEC discovery responses. All source responses are reused; zero HTTP or original-document requests, model fits or economic paths are permitted.

Reconstruct the original root/history parallel arrays through the reviewed existing parser and verify the resulting rows against the terminal registry. Every occurrence retains raw response path, URL, SHA-256, root/history page and row ordinal. Identical accession rows may share a logical record while retaining all origins. Conflicting dictionaries remain unavailable; a newer response never silently wins. Exact issuer identity comes from the root CIK/current ticker plus issuer-specific history descriptors/URLs. An accession's prefix need not equal the issuer CIK. Current identity and retrospective metadata are not point-in-time share/entity continuity.

## Candidate rules and reasons

| Decision | Fixed rule | Reason and practical limit |
|---|---|---|
| Near-filing preceding window | Same-CIK original `8-K`, exact comma-delimited Item `2.02`, with `Q − 45×86,400 seconds ≤ K < Q` | Broad near-filing coverage without deliberately including a whole adjacent quarterly cycle; fixed before observed prevalence or returns |
| Equal/later timing | Equal instants are separate; later window is `Q < K ≤ Q + 7×86,400 seconds` | Prevent an equal/later filing from being presented as earlier information |
| Time domain | Explicit timezone-aware API acceptance instants, converted to UTC; elapsed durations | Never substitute filing-date midnight, assume a timezone for a naive value, compare timestamps lexically, or silently use ET civil-day subtraction across DST |
| Amendments | Retain `8-K/A` separately; exclude it from primary original-candidate counts | An amended filing cannot replace an original disclosure |
| Multiple candidates | Preserve all matches; choose no nearest/latest winner | Timing alone cannot identify the relevant earnings release or period |
| Fiscal linkage | Retain report-date context, with fiscal period and disclosed components unverified | An 8-K report date describes event metadata; it does not prove a matching financial quarter or the availability of S/Q components |
| Missing/conflicting metadata | Preserve missing/invalid items, clocks, periods and conflicting accessions | Unavailable evidence cannot become a negative disclosure finding |
| Source envelope | Flag window endpoints outside the original 2012–2025 filing-date envelope after conversion to ET civil dates | The prior page selection targeted 10-Q filing dates, not guaranteed completeness of every earlier/later release window |
| Output size | Store all relevant metadata groups once and every near-window pair; retain per-Q exhaustive categories for outside/unavailable groups | Far-away Cartesian pairs can be reconstructed from retained groups without duplicating millions of rows |

The existing original-10-Q manifest status/error/clock is carried as a separate annotation. An API timestamp alone is candidate metadata; this audit does not verify an 8-K header/index clock or its public dissemination instant. No S/Q financial facts, prices, returns, model predictions or account ledgers are extracted or joined. In particular, later 10-Q S/Q values are never assigned to an earlier candidate's timestamp.

## Verification and continuation

The isolated implementation uses the existing submissions parser and standard-library matching/storage. Focused synthetic checks exercise endpoint inclusions, equivalent offsets, DST elapsed-time semantics, missing/invalid clocks and item encodings, amendments, multiple matches, conflicting duplicates, raw/source identity and registry reconstruction boundaries. A separate checker reconstructs raw origins and matching independently. Software/source qualification is distinct from an economic result.

A completed metadata audit should retain all 100 issuer and issuer/year denominators, every requested original and every candidate/unavailable case. Original raw metadata, row-level results and completion identities stay at their declared paths. Compact summaries and declarations belong in GitHub; large files can join the owner's separate research backup. The October 1 handover inventory is an earlier snapshot and does not automatically contain this later audit's new files.

Any original-document/exhibit probe requires a separately frozen bounded source definition. Select probes without returns or financial extraction success. Verify the exact original accession, matching filer CIK, fiscal period and components actually disclosed before treating a candidate as an earlier event. An earlier-time strategy then needs its own causal feature construction, execution clock, costs and predeclared account comparison. No economic account, strategy promotion or paper migration follows from candidate timing alone.

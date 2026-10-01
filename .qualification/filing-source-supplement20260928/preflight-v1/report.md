# Original-accession filing supplement

The20 Ford failures are caused by a specific index-selection rule, not evidence that the original reports are missing. Every affected index has one HTML10-Q matching the submissions registry's primaryDocument, a printable PDF also labelled10-Q, and one original EX-101.INS. The frozen baseline required exactly one10-Q document row overall and therefore stopped before fetching the header or facts.

For example, accession[0000037996-12-000023](https://www.sec.gov/Archives/edgar/data/37996/000003799612000023/0000037996-12-000023-index.html) has:

| Sequence | File | Index type | Role |
|---|---|---|---|
|1|f03312012-10q.htm|10-Q|Exact registry primaryDocument|
|15|f0331201210q.pdf|10-Q|Printable report; metadata retained|
|9|f-20120331.xml|EX-101.INS|Original fact-bearing instance|

`request.json` freezes all20 original failure identities, every relevant index row, selected primary URLs and60 missing resources: header, original HTML and original instance for each accession. All20 saved indexes are reused with hash checks. Selection requires exactly one10-Q row matching the registry primary URL; duplicate or absent exact matches still fail. Other10-Q/PDF metadata remains visible. There is no later filing, amendment, companyfacts or profitability-based substitution.

`capture_supplement.py` reuses the frozen transport/cache/clock machinery in an isolated process, replacing only its in-memory primary-row selector. Baseline source/code/results are never edited or rerun. The supplement writes new manifests that identify their unchanged original failures. It enforces the fixed URL list, maximum60newGETattempts,1request/second,32MiBresponse/512MiBraw-cache limits and original stop/failure behavior. Original completed failures are not retried. An interrupted request remains subject to the fixed total budget. Root launches only after baseline completion; actual exclusive locks for both source workers prevent overlap. No full supplement acquisition has been started by this agent.

Microsoft accession[0001193125-12-017029](https://www.sec.gov/Archives/edgar/data/789019/000119312512017029/d266753d10q.htm) is a different case: metadata saysisXBRL0 and the original index has no EX-101.INS. Its retained original HTML nevertheless states net income6,624 and6,634 in the three-month columns endedDecember31,2011/2010; the separate six-month values12,362/12,044 must not be substituted. Its balance sheet reports total assets108,704 atJune30,2011. Tables are labelledmillions and monetary cells use`$`.

`msft-original-html-assessment.json` preserves the unchanged original raw/hash reference, exact original table byte/character spans, all cells/column headings and verified acceptance/index/header clock. The two HTML table fragments match those exact raw spans. A separately declared original-HTML extraction path is feasible; it must document semantic concept/currency mapping because this accession supplies neither XBRL us-gaap tags nor an explicit ISOUSD unit. The original missing-instance result stays visible. No MSFT download, later amendment, return or signal was used.

Six offline checks passed, covering all20saved Ford indexes, missing/duplicate exact-primary cases, fixed URLscope, originalfailurehashes, bothworkerlocks and Microsoft's original table provenance. These establish the source refinement; they do not qualify financial features, historical dissemination instants, trading economics or profitability. Full original failure/source details remain in the baseline capture, with no response headers or cookies reproduced in this report.

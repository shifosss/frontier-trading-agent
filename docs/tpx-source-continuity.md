# TPX-B historical issuer and corporate-action continuity

Reviewed September 19, 2026 after the completed multi-model study. This is an observed data-quality concern, not a numerical repair or a new favorable backtest. The original capture and every result remain unchanged.

## Observed effect

In run `814780d48b4141b9a82a3fb917d1b85a`, the CAD 2,000 / 40-bps / five-session gradient-boosted account records a TPX-B.TO purchase on February 7, 2005 and sale on February 14. It holds five synthetic shares throughout, with entry price C$34.59 and exit price C$87.01. Its C$260.884 net gain contributes about 34% of the account's C$767.596 total net gain.

The reconstructed nominal series jumps from C$34.59 to C$95.83 on its February 8 session, approximately 177.05%. The provider's stored close likewise jumps from 17.295 to 47.915, and its adjusted close from approximately 10.986 to 30.436. The ratio of adjusted close to reconstructed nominal close remains approximately 0.3176047; the existing later-split reconstruction factor remains two. The source lists no nearby split or dividend event that explains the transition. Today's listing mapping links Molson Coors Canada class B / TPX.B to TPX-B.TO; it does not prove predecessor identity or equivalent share units across the 2005 boundary.

The independent arithmetic audit reproduces the recorded trade. That establishes consistency with the saved feed, not the economic validity of treating five shares before and after the event as the same claim. The [source-tail evidence](../.qualification/multi-model-review/cad-hgb5-source-tail.json) retains the ten largest account trades and surrounding provider observations.

## Primary-source corroboration

Molson Coors' February 11, 2005 registration amendment reports that the merger closed on February 9. It describes the exchange of old Molson shares for new common or exchangeable shares and a C$5.44 special dividend for eligible holders of record on February 8. [SEC registration amendment](https://www.sec.gov/Archives/edgar/data/24545/000104746905003297/a2151382zposam.htm).

The company's amended first-quarter filing describes the available consideration in more detail: an old Molson class A share could become 0.360 new class B exchangeable shares; an old class B share could become 0.126 new class A plus 0.234 new class B shares. It also records the special dividend. [SEC filing, Note 2: Molson Merger](https://www.sec.gov/Archives/edgar/data/24545/000104746905020899/a2161532z10-qa.htm).

These filings support a corporate-action and issuer-continuity explanation for the exceptional price change. The inverse of 0.360 is about 2.778, close to the observed 2.770 price ratio. This numerical correspondence is an inference, not a sufficient reconstruction. The provider labels the jump one session before the documented completion date; predecessor share class, exact observation mapping, elections, fractional-share treatment and cash entitlement remain unresolved.

## Treatment and next work

Do not regard this trade or the affected account's reported profit as qualified economic alpha. Do not silently add a split, multiply prices by 0.360, remove the stock, or subtract the trade's profit and present the remainder as a corrected account. A correction changes features, fitted models, position sizing and later cash paths.

The next source-quality iteration should preserve an explicit event/issuer mapping with primary evidence, reconcile the price-date and share-unit boundary, and model any share/cash entitlement. Until that is possible, observations and positions crossing the unresolved boundary must be classified as unsuitable for qualified execution research. Any historical sensitivity needs a separately frozen definition and must retain the original comparison and all resulting failures.

Apply source checks to both upward and downward discontinuities across the universe. A large return is a review trigger, not sufficient evidence that a market move is erroneous. Review missing-event and identity issues before using performance to select a replacement series or adjustment. Existing paper holdings and policy are unaffected; this review does not place or change orders.

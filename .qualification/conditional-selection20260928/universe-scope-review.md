# Universe interpretation — preserved study

The reported **4,434** is the number of distinct eligible **USD-quoted, US-listed equity-security symbols** across the study. It is not a verified count of operating-company stocks, US-domiciled businesses or unique issuers. The candidate set includes closed-end fund shares, REIT shares and ADRs. Every saved forecast column was checked: all 4,434 carry the parser's coarse `asset_type="stock"` label; none carries the directory's ETF flag. All four examples below occur in the saved eligible population.

| Symbol | Frozen listing description | Independently corroborated instrument |
|---|---|---|
| EXG | Eaton Vance Tax-Managed Global Diversified Equity Income Fund Common Shares of Beneficial Interest | Closed-end fund; [issuer's August 2024 fund announcement](https://professionals.eatonvance.com/media/pr_cmbd_080124.pdf) |
| EVV | Eaton Vance Limited Duration Income Fund Common Shares of Beneficial Interest | Closed-end fund; [issuer's August 2024 fund announcement](https://professionals.eatonvance.com/media/pr_cmbd_080124.pdf) |
| AMH | American Homes 4 Rent Common Shares of Beneficial Interest | Operating real-estate company structured as a REIT; [issuer investor page](https://investors.amh.com/home/) |
| KEP | Korea Electric Power Corporation Common Stock | NYSE-listed ADR; [issuer listing disclosure](https://www.kepco.co.kr/eng/investor-relations/stock-information/shareholding-structure/conts.do) |

These issuer checks corroborate the examples; they do not constitute a complete historical security taxonomy. In particular, REITs and ADRs are not inherently unsuitable individual-company exposures, while a closed-end fund represents a pooled portfolio. A non-ETF flag does not distinguish these cases.

## Exact provenance

The study reuses source run `814780d48b4141b9a82a3fb917d1b85a`, itself reusing capture `90af4c840aad48f7ab58fba7a682f96a`. Its discovery snapshot is `20260918T201012673731Z-2da49ecfd9bb`, captured September 18, 2026 at 20:10:12.673731 UTC. Membership is explicitly **current listings at discovery**, not historical membership.

The frozen source contains 5,675 USD instruments: 5,661 coarse stock labels and 14 ETF labels. The 14 ETFs are present as allowed source/reference instruments but excluded from these stock-candidate signals by the feature mask. Liquidity, history and setup eligibility produce 4,434 distinct candidates and 3,133,575 stock/date rows; the distinct count does not mean all 4,434 are simultaneously eligible.

All four example rows originate in Nasdaq Trader's `otherlisted.txt`, with source vintage `0918202615:41`. The retained raw file is `data/research/universe/raw/other_us.73e39cbb8bf16f68493d68534fb7c689e0ac3edd50ca15da0f8216e76ac5d4e9.txt`; its bytes match that SHA-256. Each row has ETF=`N`. The frozen snapshot file hash is `d426bedf1b9bdce6ded0adab036d52e7f8bddec9bb1603630b64773f0dac43cc`; its sorted-JSON hash `0a7835cad3d64ce2c7fc961c83b701b71a343539c43149bea068898b9a4d5dc9` matches the source definition. Snapshot instruments exactly match the definition. The compact machine-readable findings are in `universe-scope-review.json`.

The US branch of `research_universe._exclusion` admits explicit common/ordinary/depositary-share names after other exclusions. `build_membership` then labels admitted non-ETF rows as `stock` and `common_ordinary_or_equity_depositary_shares`. Unlike its Canadian issuer-category checks, it has no separate US closed-end-fund classification. The term “Common Shares of Beneficial Interest” therefore admits both AMH and the Eaton Vance funds. The downstream model's stock mask faithfully uses this broad label.

## Reporting and subsequent strategy scope

Use **“4,434 eligible US-listed equity instruments, including fund shares, REITs and ADRs”** in this study's results. Preserve its returns, trades, training samples and source identities. Do not erase CEF trades, subtract their P&L or present a retrospectively filtered account as the original result.

Before a new individual-company strategy, declare issuer/security categories separately: operating-company common/ordinary equity, equity REIT, ADR/ADS, closed-end investment company, ETF and unresolved. Record classification source, effective dates, domicile, underlying issuer and depositary mapping. Decide REIT/ADR eligibility explicitly; keep CEFs in a separate declared strategy scope or exclude them from a newly versioned individual-company lane. Do not select categories by their observed profitability. A name regex can flag review candidates but cannot supply complete CEF/REIT/ADR counts or historically correct classifications. Any narrower training and account comparison would be a new, declared experiment with the original mixed universe retained as its control.

No code, membership, policy, account or experiment was changed for this scope review.

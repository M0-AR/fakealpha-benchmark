# Data Card: FakeAlpha Live ETF Panel

## 1. Dataset identity

| Field | Value |
|---|---|
| Name | FakeAlpha live ETF panel |
| Version | 0.1.0 |
| Source | Yahoo Finance chart API v8 (`query1.finance.yahoo.com`, fallback `query2`) |
| Price field | Adjusted close |
| Frequency | Daily, US trading days |
| Assets | 12 US-listed ETFs |
| Panel start | 2007-01-03 |
| Panel end | 2026-10-23 |
| Panel rows | 4,984 |
| Evaluation window | 2012-01-01 to 2025-12-31 |
| Evaluation rows | 3,520 |
| Manifest | `data/raw/manifest.json` |
| Processed files | `data/processed/prices.csv`, `data/processed/returns.csv` (committed) |

## 2. Symbols

| Symbol | Asset class | Rows | First date | Last date | Missing business-day fraction |
|---|---|---:|---|---|---:|
| SPY | US large-cap equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| QQQ | US technology equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| IWM | US small-cap equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| DIA | US large-cap equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| TLT | US long Treasury bonds | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| GLD | Gold | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| HYG | US high-yield credit | 4,917 | 2007-04-11 | 2026-10-23 | 0.035504 |
| EEM | Emerging-market equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| EFA | Developed-market equity | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| VNQ | US real estate | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| XLE | US energy | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |
| XLK | US technology | 5,487 | 2005-01-03 | 2026-10-23 | 0.035677 |

The missing-business-day fraction is measured against a generic Monday–Friday calendar and mostly reflects US exchange holidays. It is not a missing-price rate. HYG starts later because the ETF was not listed before 2007-04-11.

## 3. Processing

1. Parse `timestamp` and `indicators.adjclose.adjclose` from the raw chart response.
2. Convert timestamps to UTC dates; drop rows without a valid adjusted close.
3. Sort by date; reject duplicate dates.
4. Build a common panel on SPY's trading calendar.
5. Forward-fill at most three trading days. This handles rare vendor gaps without inventing long histories.
6. Restrict to `2007-01-01` through the configured end date.
7. Drop rows with no prices.
8. Write the panel and a daily return matrix.

Returns are simple close-to-close returns:

\[
r_{i,t}=\frac{P_{i,t}}{P_{i,t-1}}-1.
\]

The first return of each asset is missing and is treated as zero when the strategy return is formed; this affects only the first day of the asset's history.

## 4. Validation checks

Each symbol's manifest entry records:

- number of rows;
- first and last date;
- duplicate date count;
- maximum calendar-day gap;
- zero-return fraction;
- missing-business-day fraction;
- SHA-256 of the raw JSON;
- a `status` of `ok` or `fail`;
- the list of failed checks.

The fetch fails if any symbol has status `fail`. The current panel passes all checks for all twelve symbols.

## 5. Known issues and limitations

**Vendor data.** Yahoo Finance is convenient and public but not a point-in-time institutional database. Adjusted prices incorporate dividends and splits, and the vendor may revise history. The raw responses are cached and hashed, but the vendor's terms and availability are outside the project's control. The processed panel is committed so the benchmark can be reproduced without network access.

**Adjusted close.** Using adjusted close means the return series includes dividend and split adjustments. It does not model taxes, transaction costs, or the exact cash flows a trader would receive. The benchmark uses the same price field for honest and contaminated pipelines, so the comparison is internally consistent.

**Survivorship in the universe.** The twelve ETFs are selected because they are liquid and have long histories as of the analysis date. This is a form of survivorship in the *universe design*, independent of the explicit `survivorship` contamination family. The benchmark does not reconstruct a point-in-time ETF universe. Absolute performance should not be read as a live strategy result.

**HYG start date.** HYG begins on 2007-04-11. The first quarter of 2007 has eleven assets. Cross-sectional ranks and portfolio construction handle the missing asset, but the early panel is not a balanced twelve-asset panel.

**Forward fill.** A three-day forward fill can mask a short trading halt or a vendor gap. It is deliberately short. Longer gaps remain missing and are handled by the cross-sectional rules.

**No corporate-action event study.** The analysis uses adjusted prices, not raw prices plus dividends and splits. It does not test event-date alignment or announcement-time availability.

**No intraday data.** All decisions are made at daily closes. The benchmark cannot speak to intraday leakage, auction effects, or timestamp misalignment within a day.

**No shorting, borrow, or capacity.** The portfolio is long-only and fully invested. It does not model short-sale constraints, borrow fees, market impact, or capacity.

**Evaluation period.** 2012–2025 includes the COVID-19 shock, the 2022 rate cycle, and a strong US equity trend. Results are conditional on this period.

**Data license.** Yahoo Finance data is subject to Yahoo's terms. The repository caches raw responses locally for reproducibility but does not claim redistribution rights. Users should refetch the data subject to the vendor's terms.

## 6. Intended use

- Reproducing the FakeAlpha benchmark results.
- Teaching and researching backtest leakage, multiple testing, and reproducibility.
- Testing new detection diagnostics against a known contaminated/honest pair.
- Auditing the sensitivity of a diagnostic to leak size and mechanism.

## 7. Prohibited or inappropriate use

- Treating the ETF panel as a live trading signal or investment advice.
- Claiming that a strategy is profitable based on this benchmark.
- Using the data without complying with Yahoo's terms.
- Inferring the prevalence of leakage in academic or industry research from this sample.
- Using the panel as a point-in-time universe for survivorship-free inference.

## 8. Maintenance

The data is fetched on demand and cached. To refresh:

```bash
fakealpha fetch --config config/experiment.yaml --force
```

This rewrites the raw JSON, the manifest, and the processed panel. A changed raw file changes the SHA-256 and may change the results; record the new manifest and rerun the benchmark. Do not mix raw files from different fetch dates in one panel.

## 9. Citation

Cite the repository and the paper-style README. If you use the data independently, cite Yahoo Finance as the source and record the fetch date from the manifest.

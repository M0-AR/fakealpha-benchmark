# Model Card: FakeAlpha Honest Pipeline and Diagnostic Harness

## 1. Model details

| Field | Value |
|---|---|
| Name | FakeAlpha honest pipeline and diagnostic harness |
| Version | 0.1.0 |
| Date | 2026-10-25 |
| Owners | FakeAlpha contributors |
| Type | Deterministic long-only ETF allocation pipeline plus a benchmark harness for contamination detection |
| License | MIT |
| Repository | `fakealpha-benchmark` |
| Primary implementation | `src/fakealpha/` (Python 3.12) |
| Paper-style description | `README.md`; manuscript source in `paper/paper.md` |

This card describes two coupled objects. The first is the **honest pipeline**: a transparent, long-only, weekly-rebalanced ETF strategy used as the control. The second is the **diagnostic harness**: the six contamination families, the six diagnostics, and the calibration procedure used to measure detection. Neither object is a production trading model. The pipeline exists to give the benchmark a realistic, non-degenerate return series; the harness exists to measure whether diagnostics can tell that series apart from a contaminated one.

### 1.1 Pipeline architecture

- **Universe.** Twelve US-listed ETFs: `SPY, QQQ, IWM, DIA, TLT, GLD, HYG, EEM, EFA, VNQ, XLE, XLK`.
- **Inputs.** Adjusted daily closes from the Yahoo Finance chart API v8, cached, hashed, and validated.
- **Signals.** Sixteen causal signals: seven momentum windows (5, 10, 20, 40, 60, 120, 250 days), two low-volatility signals (20 and 60 days), negative 14-day RSI, a negated 20-day volatility z-score, a 20-day trend, a 60-day drawdown, two cross-sectional ranks (20-day momentum and 20-day low volatility), and a cross-sectional composite.
- **Candidates.** Every triple of signal, `k` in {1, 2, 3, 4}, and weighting in {equal, inverse volatility}: 128 candidates. Each replicate samples 40 without replacement.
- **Portfolio.** At each weekly close, rank available assets by the signal, select the top `k`, and assign equal or inverse-volatility weights. Long-only and fully invested; cash if fewer than `k` assets are valid.
- **Execution.** Signals formed at the close of day `t` are applied to the return on day `t+1` (lag 1). One-way turnover costs 5 basis points per unit of turnover.
- **Selection.** Annual expanding walk-forward. For test year `y`, select the candidate with the highest non-annualized Sharpe using data through 31 December of `y-1`, minus a two-trading-day embargo, requiring at least 126 observations. Apply the selected candidate to year `y`.
- **Outputs.** Daily strategy returns, annualized Sharpe ratios, gate scores, per-replicate tables, figures, and a reproducibility manifest.

### 1.2 Contamination variants

Each contaminated pipeline differs from the honest pipeline in exactly one mechanism:

| Family | Change |
|---|---|
| `same_bar_fill` | Lag 0: the signal at the close of `t` earns the return on `t`. |
| `target_feature` | Add `1.0 * zscore_cs(forward_5d_return)` to every base signal. |
| `full_sample_target_encoding` | Replace every signal with the asset's full-sample mean daily return. |
| `shuffled_cv` | Select by mean Sharpe across five randomly shuffled folds of the test window. |
| `survivorship` | Admit asset `i` at `t` only if its forward 252-day return is non-negative or missing. |
| `p_hacked_selection` | In each test year, select the candidate with the highest Sharpe in that same year. |

The variants are deliberately strong and clean. They are test instruments, not estimates of how leakage appears in practice.

### 1.3 Diagnostics

The harness evaluates the deflated Sharpe ratio (DSR), probability of backtest overfitting (PBO), a Šidák-adjusted reality check (RC), split-half degradation, a returns-only composite, and a paired artifact audit. The audit re-executes the honest pipeline and bootstraps the Sharpe difference with a paired circular block bootstrap (500 draws, 20-day blocks). Detection thresholds are the 95th percentile of the honest suspicion distribution, except the audit, which uses its nominal 5% level.

The composite is the maximum standardized value of PBO, reverse RC, and split-half. It excludes the DSR because the DSR moves in the wrong direction under leakage, and excludes the audit because the audit requires the honest comparator's return series.

## 2. Intended use

### 2.1 Primary uses

- Reproducing the FakeAlpha detection matrix and figures.
- Teaching backtest leakage, multiple testing, and the difference between publication filters and validity checks.
- Testing a new diagnostic against a paired honest/contaminated benchmark with a known mechanism.
- Auditing how detection power changes with the size of a leak.

### 2.2 Secondary uses

- A worked example of a causal walk-forward protocol for long-only ETF strategies.
- A template for data manifests, hashed raw inputs, and containerized reproduction.
- A cautionary example for research-methods discussions.

### 2.3 Out-of-scope uses

- Live trading, portfolio construction, or investment advice.
- Claims that any candidate or family is profitable after costs.
- Estimating the prevalence of leakage in academic or industry research.
- Treating the ETF panel as a point-in-time, survivorship-free universe.
- Using the contamination code to publish deceptive results. The variants are for testing detectors.

## 3. Factors

### 3.1 Universe and period

The panel covers 2007-01-03 through 2026-10-23 (4,984 rows). The evaluation window is 2012-01-01 through 2025-12-31 (3,520 rows). The first five years are training data. HYG begins on 2007-04-11, so the first quarter of 2007 has eleven assets.

### 3.2 Market benchmarks

Over the evaluation window, SPY has an annualized Sharpe ratio of 0.917 and volatility of 16.7%; an equal-weight portfolio of the twelve ETFs has a Sharpe ratio of 0.810 and volatility of 13.4%; a static 60% SPY / 40% TLT portfolio has a Sharpe ratio of 0.935. The honest pipeline's mean Sharpe across 80 replicates is 0.821 (median 0.842, standard deviation 0.087, range 0.550–0.953). It is a realistic long-only strategy, not an alpha claim.

### 3.3 Sampling and dependence

Each replicate samples 40 of 128 candidates with seed `20261025`. The candidate matrix is highly correlated: mean pairwise correlation 0.609, participation ratio 2.46, and 10 principal components explain 90% of the variance. The effective number of independent trials is much smaller than 40. This affects the DSR and reality-check calibration and is part of the object being studied, not a nuisance to be removed.

## 4. Metrics

| Metric | Definition | Direction |
|---|---|---|
| Annualized Sharpe | Mean daily return divided by daily standard deviation, times `sqrt(252)`; risk-free rate zero | Higher is better for the strategy, not for validity |
| DSR | Bailey–López de Prado deflated Sharpe probability | Higher is more publishable; `1 - DSR` is the suspicion score |
| PBO | Fraction of combinatorially symmetric splits where the in-sample winner is at or below the out-of-sample median | Higher is more suspicious |
| Reality check | Šidák-adjusted one-sided p-value for the best of `N` candidates | `1 - p_adj` is the suspicion score |
| Split-half | Standardized first-half minus second-half Sharpe | Higher is more suspicious (one-sided) |
| Audit | Paired block-bootstrap p-value for a positive Sharpe difference versus the honest re-execution | `1 - p_audit` is the suspicion score |
| Composite | Maximum standardized PBO, reverse RC, and split-half | Higher is more suspicious |

False-positive rates are computed on the 80 honest controls. True-positive rates are computed on the 80 contaminated replicates per family. Wilson 95% intervals and AUC are reported for the detection matrix. The AUC uses the 80 honest and 80 contaminated scores for each family.

## 5. Evaluation data

The evaluation data are the same live ETF panel used by the pipeline; there is no separate held-out dataset. The benchmark is a designed experiment, not a predictive model evaluation. The relevant "generalization" question is whether a diagnostic trained on honest controls flags a known contaminated pipeline, not whether the strategy generalizes to new assets.

Data are fetched from Yahoo Finance, cached as raw JSON, and validated for non-empty arrays, increasing dates, no duplicates, at least 500 rows, maximum calendar gap below 10 days, zero-return fraction below 20%, and missing-business-day fraction below 10%. All twelve symbols currently pass. The raw manifest records SHA-256 hashes, row counts, date ranges, and validation status. See `docs/data_card.md` for details.

## 6. Training and selection data

The honest selector uses only data before the test year, minus a two-trading-day embargo. The test window is never used for selection in the honest pipeline. The contaminated variants deliberately violate this rule: `shuffled_cv` and `p_hacked_selection` select on the test window; `target_feature` uses future five-day returns; `full_sample_target_encoding` uses full-sample statistics; `survivorship` uses forward 252-day returns; `same_bar_fill` uses the same bar's return. These violations are the treatment.

The benchmark does not train a machine-learning model. "Training" means candidate selection by historical Sharpe. There are no learned parameters beyond the selected candidate and the portfolio weights implied by the signal.

## 7. Quantitative analyses

### 7.1 Leakage inflation

| Family | Mean Sharpe | Mean inflation vs. honest |
|---|---:|---:|
| Honest | 0.821 | — |
| Same-bar fill | 2.048 | +1.227 |
| Target feature | 6.842 | +6.021 |
| Full-sample encoding | 0.980 | +0.159 |
| Shuffled CV | 0.990 | +0.169 |
| Survivorship | 1.198 | +0.377 |
| P-hacked selection | 1.477 | +0.656 |

Every family's paired inflation interval excludes zero. The ordering runs from a direct five-day future return (largest) to a same-bar close, then test-set selection and survivorship, then the two small leaks.

### 7.2 Publication filters

At the conventional DSR threshold of 0.95, 0.0% of honest controls are publishable, while 52.5–100% of contaminated pipelines are. At the nominal 5% reality-check threshold, 60.0% of honest controls are publishable and 98.8–100% of contaminated pipelines are. These are publication rates, not detection rates. The DSR and the nominal reality check answer questions about sampling and multiplicity, not about implementation validity.

### 7.3 Detection at a controlled false-positive rate

| Family | DSR | PBO | Reverse RC | Split-half | Composite | Audit |
|---|---:|---:|---:|---:|---:|---:|
| Same-bar fill | 0.000 | 0.000 | 1.000 | 0.350 | 1.000 | 1.000 |
| Target feature | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Full-sample encoding | 0.000 | 1.000 | 1.000 | 0.000 | 1.000 | 0.038 |
| Shuffled CV | 0.000 | 0.025 | 0.688 | 0.000 | 0.550 | 0.350 |
| Survivorship | 0.000 | 0.675 | 0.950 | 0.100 | 1.000 | 0.675 |
| P-hacked selection | 0.000 | 0.025 | 1.000 | 0.038 | 1.000 | 0.963 |
| **False-positive rate** | **0.038** | **0.025** | **0.038** | **0.025** | **0.038** | **0.000** |

The DSR's AUC is at or below 0.08 for every family, which means contaminated runs rank as *less* suspicious than honest ones. The audit's AUC is at least 0.988 for every family, but its fixed-level power collapses for small leaks. The audit's honest false-positive rate is zero by construction because the honest comparator is deterministic.

### 7.4 Union of composite and audit

The union of the composite and the audit flags 100% of same-bar, target, full-sample, survivorship, and p-hacked families, and 62.5% of shuffled CV, at a 3.8% false-positive rate. The incremental value of the audit on this benchmark is modest in true-positive terms; its value is mechanism-specific evidence that a returns-only screen cannot provide.

## 8. Ethical considerations

- **Not investment advice.** The benchmark is research software. It does not produce a deployable strategy, and its absolute Sharpe ratios are not net-of-real-world-cost estimates.
- **Data terms.** Yahoo Finance data are subject to Yahoo's terms. The repository caches raw responses locally for reproducibility and does not claim redistribution rights. Users should refetch the data subject to the vendor's terms.
- **No personal data.** The benchmark uses public market prices and contains no personal or sensitive data.
- **Dual use.** The contamination implementations could be misused to manufacture impressive but invalid backtests. They are included because detecting leakage requires known positive examples. Anyone using the code should preserve the honest/contaminated distinction and should not present a contaminated result as a valid strategy.
- **Research integrity.** The central claim is negative: no returns-only statistic establishes validity. The benchmark should not be cited as evidence that a particular published strategy is contaminated, nor as a universal detector.

## 9. Caveats and recommendations

**Constructed leaks.** The six families are clean and strong. Real leakage is often partial, intermittent, or entangled with legitimate feature engineering. The measured rates are detectability under controlled conditions, not prevalence.

**Limited universe.** Twelve US ETFs, long-only, weekly rebalance, no shorting, no leverage, no borrow, no capacity, no market impact, and no taxes. Detection rates may not transfer to equities, futures, intraday data, or large alpha libraries.

**Single period and seed.** The evaluation window is 2012–2025 and the seed is fixed. Regime dependence and seed robustness are not modeled. The family-level rates are descriptive; no formal test of differences between gates is performed.

**Audit assumptions.** The audit assumes a correctly specified, deterministic honest comparator. Its false-positive rate is zero by construction, not empirically estimated. The bootstrap is a confidence-distribution procedure, not a formal randomization test. Block length, bootstrap draws, and the Sharpe-difference statistic were not sensitivity-tested.

**DSR and reality check.** The DSR uses the variance of trial Sharpes, not the full covariance of trial returns. The Šidák reality check assumes independence and is not White's full bootstrap. Neither is a validity check.

**PBO and split-half.** PBO is blind to selection rules other than "pick the in-sample best column." The split-half test is one-sided and sensitive to the split date. Both are stability diagnostics, not leakage detectors.

**Degenerate matrices.** The full-sample family collapses the 40-candidate matrix to eight unique portfolios, so its across-replicate interval is artificially narrow. The narrow interval is a property of the design, not evidence of precision about the leak.

**Recommendation.** Treat an extreme Sharpe ratio as a trigger for a code-and-data audit, not as proof of alpha. Report DSR and reality-check p-values as publication filters, use PBO and split-half as cheap stability checks, and state the power limitations of any audit. Do not transplant the composite threshold to a different universe without recalibration.

## 10. Maintenance

The benchmark is deterministic given the same data and package versions. The seed, configuration, package versions, data manifest, and summary are recorded in `results/run_manifest.json`. To refresh the data:

```bash
fakealpha fetch --config config/experiment.yaml --force
fakealpha run --config config/experiment.yaml
```

A changed raw file changes its SHA-256 and may change the results. Record the new manifest and rerun the benchmark; do not mix raw files from different fetch dates in one panel. The Docker path in `docker-compose.yml` reproduces the run with pinned dependencies.

Questions and issues should be filed in the repository. The software is provided under the MIT license, without warranty.

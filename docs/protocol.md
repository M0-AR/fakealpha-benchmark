# Protocol

This document is the implementation-level protocol for the FakeAlpha benchmark. The paper-style overview, results, and interpretation are in `README.md`. This file is for readers who want to rerun, extend, or criticize the experiment without reverse-engineering the code.

## 1. Question and estimand

The benchmark estimates, for a known contamination mechanism \(f\) and a diagnostic \(g\),

\[
\mathrm{TPR}_g(f)=\Pr\left(g\text{ flags}\mid f\text{ is active}\right),
\]

at a false-positive rate calibrated on the honest pipeline:

\[
\mathrm{FPR}_g=\Pr\left(g\text{ flags}\mid \text{honest}\right)\approx0.05.
\]

The unit of analysis is a replicate-family pair. Each replicate draws a 40-candidate subset, runs the honest pipeline, runs each contaminated family on the same subset, and records the reported return series and gate scores. There are 80 replicates and 6 families, plus the honest control: 560 rows in `results/tables/per_replicate.csv`.

The estimand is not the prevalence of leakage in the literature and not the profitability of any strategy. It is the operating characteristic of each diagnostic under a controlled leak.

## 2. Data protocol

1. Fetch adjusted-close chart data from Yahoo Finance chart API v8 for the twelve configured symbols.
2. Cache the raw JSON per symbol. Validate:
   - non-empty timestamp and adjusted-close arrays;
   - strictly increasing dates;
   - no duplicate dates;
   - at least 500 rows;
   - maximum calendar gap below 10 days;
   - zero-return fraction below 20%;
   - missing-business-day fraction below 10%.
3. Build a common panel on SPY's trading calendar.
4. Forward-fill at most three trading days.
5. Restrict to the requested start and end dates.
6. Drop rows with no prices.
7. Write `data/processed/prices.csv` and `data/processed/returns.csv`.
8. Write `data/raw/manifest.json` with SHA-256, row counts, first/last dates, and validation checks.

The analysis start is 2007-01-01. The fetch history starts 2005-01-03 to provide warm-up for the 250-day momentum signal. The evaluation window is 2012-01-01 through 2025-12-31. The last data date is 2026-10-23.

No synthetic prices, no interpolation beyond the three-day forward fill, and no point-in-time universe reconstruction are used. The data card records the known limitations.

## 3. Honest pipeline

### 3.1 Signals

Sixteen signals are computed from prices up to and including date \(t\):

| Signal | Definition |
|---|---|
| `mom5`, `mom10`, `mom20`, `mom40`, `mom60`, `mom120`, `mom250` | \(P_t/P_{t-w}-1\) |
| `lowvol20`, `lowvol60` | Negative rolling volatility, annualized |
| `rsi14` | Negative 14-day RSI |
| `volz20` | Negative 20-day volatility z-score over 252 days |
| `trend20` | \(P_t/\mathrm{MA}_{20}(P_t)-1\) |
| `dd60` | \(P_t/\max_{60}(P)-1\) |
| `cs_mom20` | Cross-sectional percentile rank of 20-day momentum |
| `cs_vol20` | Cross-sectional percentile rank of negative 20-day volatility |
| `combo` | Sum of cross-sectional z-scores of `mom20`, `mom60`, `trend20` |

All rolling windows use only data available at \(t\). The honest signal path never reads `forward_1d`, `forward_5d`, `forward_252d`, or `full_sample_mean_return`.

### 3.2 Candidates

A candidate is `(signal, k, weighting)` with \(k\in\{1,2,3,4\}\) and weighting \(\in\{\text{equal},\text{invvol}\}\). The full pool is 128 candidates. Each replicate samples 40 without replacement.

For a signal row \(s_t\), the selected assets are the \(k\) largest finite values. Equal weights are \(1/k\). Inverse-volatility weights are

\[
w_i=\frac{1/\sigma_{i,t}}{\sum_{j\in\mathcal{S}}1/\sigma_{j,t}},
\]

where \(\sigma_{i,t}\) is 20-day annualized volatility. Non-finite or non-positive volatilities are replaced by the cross-sectional median of valid volatilities.

### 3.3 Rebalance, lag, and costs

- Rebalance dates: last trading day of each week (`W-FRI`).
- Honest lag: 1. A signal formed at the close of \(t\) earns the return on \(t+1\).
- Same-bar leak: lag 0. The signal formed at \(t\) earns the return on \(t\).
- Cost: 5 basis points per unit of one-way turnover, charged on the day the new target starts.
- Long-only, fully invested in the selected \(k\) assets; cash if fewer than \(k\) valid assets.

### 3.4 Walk-forward selection

For evaluation year \(y\):

1. Set `train_end = 31 December (y-1) - 2 trading days`.
2. Use all candidate daily returns through `train_end`.
3. Compute non-annualized Sharpe for each candidate with at least 126 observations.
4. Select the candidate with the highest finite Sharpe.
5. Apply its returns to year \(y\).
6. Add year \(y\) to the training window for the next year.

The reported series is the concatenation of the annual out-of-sample blocks. The selector never sees the current year. Each subsequent test year becomes training data for later years, which is standard expanding-window walk-forward.

### 3.5 Candidate sampling

Seed: `20261025`.

For replicate \(r\):

```python
rng = np.random.default_rng(seed)
indices = sorted(rng.choice(128, size=40, replace=False))
```

The same indices are used for the honest control and all six families. The audit seed is `seed + 101`; the shuffled-CV seed is `seed + 17`; the replicate seed is `seed + 1009*r`.

## 4. Contamination protocol

| Family | Code change | Matrix used for gates |
|---|---|---|
| `same_bar_fill` | `lag=0` in `returns_matrix` | Contaminated matrix |
| `target_feature` | Add `1.0 * zscore_cs(forward_5d)` to every z-scored base signal | Contaminated matrix |
| `full_sample_target_encoding` | Replace every signal with `full_sample_mean_return` | Contaminated matrix |
| `shuffled_cv` | Random 5-fold assignment on the evaluation window; select by mean fold Sharpe | Honest matrix |
| `survivorship` | Eligibility mask `forward_252d > 0 or forward_252d is NaN` | Contaminated matrix |
| `p_hacked_selection` | Annual oracle: select the best candidate in each evaluation year | Honest matrix |

The code paths are in `src/fakealpha/strategies.py` and `src/fakealpha/pipeline.py`.

## 5. Gates and calibration

### 5.1 Scores

| Gate | Score | Direction |
|---|---|---|
| DSR | \(1-\mathrm{DSR}\) | Higher = more publishable = more suspicious |
| PBO | \(\mathrm{PBO}\) | Higher = more overfit |
| Reality check | \(1-p_{\text{adj}}\) | Higher = more significant = more suspicious |
| Split-half | \(z_{\text{split}}\) | Higher = more first-half degradation |
| Audit | \(1-p_{\text{audit}}\) | Higher = reported Sharpe exceeds honest re-execution |
| Composite | max standardized PBO, reverse RC, split | Higher = any returns-only validity signal |

### 5.2 Thresholds

- DSR, PBO, reverse RC, split, composite: 95th percentile of the 80 honest scores (`method="higher"`).
- Audit: \(p_{\text{audit}}\le0.05\), i.e. suspicion \(\ge0.95\).
- Composite standardization: subtract the honest 95th percentile, divide by the honest interquartile range (floor \(10^{-6}\)), take the maximum over the three components.

The thresholds are written to `results/tables/thresholds.json`.

### 5.3 Metrics

- TPR: fraction of the 80 family replicates above threshold.
- FPR: fraction of the 80 honest replicates above threshold.
- Wilson 95% interval for TPR.
- AUC: `roc_auc_score` with 80 honest scores labeled 0 and 80 family scores labeled 1.
- `publishable_dsr`: \(\mathrm{DSR}\ge0.95\).
- `publishable_reality_check`: \(p_{\text{adj}}\le0.05\).

## 6. Audit

For each replicate-family pair:

1. Align the reported and honest daily return series by date.
2. If either series has fewer than 60 observations or zero variance, return \(p=1\).
3. Compute the observed annualized Sharpe difference.
4. If the difference is non-positive, return \(p=1\).
5. Draw 500 paired circular block bootstrap paths with block length 20.
6. Compute the bootstrap Sharpe difference for each path.
7. Return \((1+\#\{\Delta SR_b\le0\})/(B+1)\).

This is a paired bootstrap confidence-distribution test. It is not a formal randomization test and does not recenter the bootstrap distribution under the null. The honest control's p-value is exactly 1 because the reported and honest series are identical.

## 7. Outputs

| Path | Content |
|---|---|
| `data/raw/*.json` | Raw Yahoo responses (cached, gitignored) |
| `data/raw/manifest.json` | Hashes, row counts, validation |
| `data/processed/prices.csv` | Adjusted-close panel (committed) |
| `data/processed/returns.csv` | Daily returns (committed) |
| `results/tables/per_replicate.csv` | 560 replicate-family rows |
| `results/tables/summary.csv` | Family-level means, CIs, TPR/FPR/AUC |
| `results/tables/honest_controls.csv` | Honest descriptive statistics |
| `results/tables/thresholds.json` | Calibrated thresholds |
| `results/tables/descriptives.json` | Benchmarks, candidate correlation, audit quantiles |
| `results/figures/*.png` | Figures used in the paper |
| `results/run_manifest.json` | Config, versions, data manifest, panel hashes, summary |

## 8. Reproduction commands

```bash
fakealpha run --config config/experiment.yaml
fakealpha report --config config/experiment.yaml
pytest -q
ruff check src tests
```

To refresh the live panel instead of using the committed one:

```bash
fakealpha fetch --config config/experiment.yaml --force
```

Docker:

```bash
docker compose build
docker compose run --rm fakealpha
```

## 9. Protocol deviations and known issues

- The `full_sample_target_encoding` candidate matrix collapses to eight unique portfolios because all sixteen signal names share the same frame. Its across-replicate confidence interval is therefore not comparable to the other families.
- PBO for `shuffled_cv` and `p_hacked_selection` is computed on the honest candidate matrix, so its detection rate is the FPR by construction.
- The split-half test is one-sided. A two-sided variant is discussed in the README but is not the primary specification.
- The audit's honest false-positive rate is zero by construction, not estimated from independent reimplementations.
- The Šidák reality check is a conservative stand-in for White's bootstrap reality check; it ignores cross-trial dependence.
- The DSR implementation uses the variance of trial Sharpe ratios, not the full covariance matrix of trial returns.
- The data source is Yahoo Finance, not a point-in-time institutional database.
- The test period includes the COVID-19 shock and the 2022 rate cycle; regime dependence is not modeled.

## 10. Change control

If you change the universe, features, cost model, candidate pool, test window, seed, or gate definitions, the thresholds and TPR/FPR table are no longer comparable to the published results. Record the change in `results/run_manifest.json` and update the paper's protocol section. Do not hand-edit the CSV outputs; regenerate them with `fakealpha run` or `fakealpha report`.

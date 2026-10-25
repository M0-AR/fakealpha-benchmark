---
title: "Leakage Looks Like Alpha"
subtitle: "A Paired, Live-Market Benchmark for Detecting Contaminated Systematic Backtests"
author: "FakeAlpha contributors"
date: "Working paper v0.1 · October 2026"
abstract: |
  Backtest leakage is a validity failure, not a sampling fluctuation. It can raise a strategy's Sharpe ratio, stabilize its equity curve, and make an invalid specification look more publishable than an honest one. We build a controlled, fully reproducible benchmark to measure whether common backtest diagnostics detect that failure. The benchmark uses twelve liquid US ETFs, live Yahoo Finance chart data from 2005 through 23 October 2026, an honest weekly long-only walk-forward protocol, and six contamination families: same-bar fill, target-feature leakage, full-sample target encoding, shuffled cross-validation, survivorship filtering, and test-set p-hacking. Each family is paired with the honest pipeline on the same 40-candidate subset and the same random seed, for 80 replicates.

  Leakage raises the mean annualized Sharpe ratio from 0.821 in the honest control to 0.980–6.842 across families. The deflated Sharpe ratio (DSR) and the Šidák-adjusted reality check are not validity checks. As publication filters they are inverted or permissive: DSR would publish 0.0% of honest controls but 52.5–100% of contaminated pipelines; the nominal 5% reality check would publish 60.0% of honest controls and 98.8–100% of contaminated pipelines. A returns-only composite of probability of backtest overfitting (PBO), reverse reality-check significance, and split-half degradation detects five of six families at a 3.8% false-positive rate, but only 55.0% of the small shuffled-CV leak. A paired artifact audit—re-executing the honest pipeline and bootstrapping the Sharpe difference—detects large implementation leaks at 100% but only 3.8% of the +0.159 Sharpe full-sample leak. Detection power rises monotonically with the size of the leak; ranking can be near-perfect even when fixed-level power is low.

  The central conclusion is negative and practical: no returns-only statistic establishes backtest validity. Extreme performance should trigger a code-and-data audit, not substitute for one. DSR and reality-check p-values belong in the publication-filter column, not the validity column. PBO, split-half, and the audit have complementary blind spots.
keywords: "backtest overfitting, data leakage, deflated Sharpe ratio, probability of backtest overfitting, reality check, reproducibility, survivorship bias, cross-validation"
---

> Manuscript source for the FakeAlpha Benchmark v0.1. The paper-style `README.md` is the canonical, rendered overview. This file is intended for Pandoc/LaTeX processing with `paper/references.bib`; citations use Pandoc syntax. Render from the repository root with `pandoc paper/paper.md --citeproc --bibliography=paper/references.bib -o paper/paper.pdf`.

# 1. Introduction

A backtest is a specification search conducted on historical data. The search includes the universe, the features, the label, the model, the portfolio rule, the rebalance frequency, the cost model, and the evaluation window. When any part of that search uses information that would not have been available at the decision time, the resulting Sharpe ratio is not an estimate of deployable performance. It is an estimate of a contaminated joint distribution.

The problem is not merely that leakage inflates performance. The problem is that leakage can inflate precisely the statistics that researchers use to argue that performance is credible. A leak can make a strategy look stable across folds, robust to multiple testing, and highly significant. The diagnostics then certify the artifact.

This paper asks a narrow, measurable question:

> Given a known contamination mechanism and a paired honest pipeline, which commonly reported backtest diagnostics detect the contamination at a controlled false-positive rate, and which fail?

We answer with a benchmark rather than a new theorem. The design has four features that make the answer auditable. First, the data are live public prices, fetched from Yahoo Finance's chart API, cached as raw JSON, hashed, validated, and processed without synthetic fills. The panel covers twelve US ETFs from January 2007 through 23 October 2026. Second, honest and contaminated runs are paired: within a replicate they use the same candidate subset, the same walk-forward dates, the same cost model, and the same evaluation window. The only difference is the leak. Third, the mechanisms are known. Six families cover timing leaks, target leaks, full-sample statistics, cross-validation leaks, survivorship, and selection on the test set. Fourth, multiple diagnostics are evaluated on a common calibration: DSR, PBO, a Šidák reality check, split-half degradation, a returns-only composite, and a paired artifact audit, each measured at a 5% false-positive rate on the same 80 honest controls.

The headline result is an inversion. The DSR, designed to correct for selection and non-normality, is *higher* for contaminated pipelines than for honest ones. The reality check, designed to control data snooping, is *more permissive* than its nominal level suggests. Both answer a question about sampling and multiple testing; neither answers the question "was this backtest implemented without look-ahead?" PBO and split-half are closer to validity checks, but each has a structural blind spot. The artifact audit is the only diagnostic that directly tests implementation, and its power collapses for small leaks.

The contribution is fourfold. We provide a reproducible, live-market benchmark for backtest contamination with paired honest controls and six contamination families. We report a detection matrix at a controlled 5% false-positive rate, with Wilson intervals and AUC, showing where each diagnostic succeeds and where it is structurally blind. We show that DSR and the Šidák reality check are publication filters, not validity checks, and that their decisions can invert under leakage. We analyze the power of artifact auditing: detection rises with the size of the leak, but small leaks remain hard even when the auditor can re-execute the pipeline. The practical implication is a protocol that treats extreme performance as a trigger for audit rather than proof of alpha.

We do not claim that DSR, PBO, reality checks, or split-half are useless. Each answers a real question. We claim that those questions are not the question of implementation validity. We do not claim that the composite screen is optimal; it is a transparent heuristic calibrated on this benchmark. We do not claim external validity to equities, futures, intraday data, short-selling, or large alpha libraries. Those are open extensions.

# 2. Background and related work

## 2.1 The backtest as a specification search

The replication literature has established that many published return predictors are fragile. McLean and Pontiff [-@mclean2016does] document post-publication decay in anomaly returns, consistent with publication-driven selection and arbitrage. Hou, Xue, and Zhang [-@hou2020replicating] find that many anomalies fail to replicate under consistent methods, and Jensen, Kelly, and Pedersen [-@jensen2023replication] estimate that a substantial share of published factors do not survive rigorous replication. Campbell and Thompson [-@campbell2008predicting] and Welch and Goyal [-@welch2008comprehensive] show how sensitive out-of-sample predictability is to specification and evaluation choices. Gu, Kelly, and Xiu [-@gu2020empirical] and Israel, Kelly, and Moskowitz [-@israel2020machines] emphasize that machine-learning results in finance depend heavily on protocol details.

These findings motivate a distinction between *statistical* significance and *implementation* validity. A backtest can be free of look-ahead and still fail out of sample because the signal is weak. A backtest can be contaminated and look strong in sample and out of sample. The two failure modes require different diagnostics.

## 2.2 Leakage taxonomy

Leakage arises whenever a feature, label, normalization, universe rule, or selection procedure uses information unavailable at the decision time. Common forms include same-bar execution, target leakage, full-sample normalization or target encoding, shuffled cross-validation, survivorship-filtered universes, and selection on the evaluation window. López de Prado [-@lopezdeprado2018advances] catalogues many of these mechanisms in the context of financial machine learning; Arnott, Harvey, and Markowitz [-@arnott2019backtesting] propose a protocol to reduce them; Bailey, Borwein, López de Prado, and Zhu [-@bailey2014pseudo] warn that backtest overfitting can produce impressive but spurious results.

The benchmark does not attempt to reproduce every real-world leak. It constructs one clean, strong instance of each of six mechanisms, so that a diagnostic's blind spots can be attributed to the mechanism rather than to noise in the leak.

## 2.3 Multiple-testing and overfitting diagnostics

White's reality check [-@white2000reality] and Hansen's superior predictive ability test [-@hansen2005test] control data snooping when many strategies are compared. Romano and Wolf [-@romano2005stepwise] extend the idea to stepwise multiple testing. Sullivan, Timmermann, and White [-@sullivan1999data] apply the bootstrap reality check to technical trading rules. Harvey, Liu, and Zhu [-@harvey2016cross] argue that a higher t-statistic threshold is needed in asset pricing given the number of tested factors; Harvey and Liu [-@harvey2015backtesting] survey backtesting practices.

The deflated Sharpe ratio [-@bailey2014dsr] adjusts an observed Sharpe ratio for the number of trials, their dispersion, skewness, and kurtosis. The probability of backtest overfitting [-@bailey2017pbo] uses combinatorially symmetric cross-validation to estimate how often the in-sample winner underperforms out of sample. Lo [-@lo2002statistics] gives the sampling theory of Sharpe ratios, and Politis and Romano [-@politis1994stationary] and Künsch [-@kunsch1989jackknife] provide the block-bootstrap foundations used by the audit. Efron and Tibshirani [-@efron1993bootstrap] provide the general bootstrap framework.

## 2.4 The gap

Existing work either studies a single strategy, evaluates diagnostics on synthetic return distributions, or focuses on multiple testing without a known contamination mechanism. What is missing is a *paired, live-market* design in which the honest and contaminated pipelines share everything except the leak, so that detection rates can be attributed to the diagnostic rather than to differences in data, universe, or protocol. This paper fills that gap with a small, transparent benchmark.

# 3. Benchmark design

## 3.1 Data

The universe is twelve liquid US-listed ETFs spanning equities, duration, credit, gold, real estate, energy, and technology:

`SPY, QQQ, IWM, DIA, TLT, GLD, HYG, EEM, EFA, VNQ, XLE, XLK`.

Prices are adjusted closes from the Yahoo Finance chart API v8. The fetcher requests `query1.finance.yahoo.com/v8/finance/chart/{symbol}` with a browser-like User-Agent and gzip encoding, falls back to `query2` on failure, retries with backoff, and caches the raw JSON. The processed panel uses SPY's trading calendar, forward-fills at most three days, and drops dates with no prices. No synthetic prices are generated.

The raw response for every symbol is hashed with SHA-256 and recorded in `data/raw/manifest.json`, together with row counts, first and last dates, duplicate counts, maximum gaps, zero-return counts, and validation status. The processed panel and the manifest are the reproducibility boundary.

The requested history starts on 3 January 2005, which provides at least 250 trading days of warm-up for the longest momentum signal before the analysis start. The analysis panel starts on 3 January 2007 and ends on 23 October 2026. The evaluation period is 1 January 2012 through 31 December 2025, a fourteen-year window with 3,520 trading days. The 2007–2011 period is used only for walk-forward training; each subsequent test year is added to the training window for later years.

HYG begins on 11 April 2007, so the first quarter of 2007 has eleven assets. Cross-sectional operations ignore missing values; the portfolio rule requires at least `k` valid assets and otherwise holds cash. The missing-business-day fraction is about 3.56% for the eleven full-history symbols and 3.55% for HYG; these are exchange holidays, not missing prices. Table 1 summarizes the data.

**Table 1.** Data summary.

| Item | Value |
|---|---:|
| Assets | 12 ETFs |
| Panel rows | 4,984 |
| First panel date | 2007-01-03 |
| Last panel date | 2026-10-23 |
| Evaluation rows | 3,520 |
| Evaluation window | 2012-01-01 to 2025-12-31 |
| Full-history symbols | 11 |
| Late-start symbol | HYG, 2007-04-11, 4,917 rows |
| Raw-data validation | all symbols `ok` |
| Manifest | SHA-256 per raw JSON |

Over the evaluation window, SPY has an annualized Sharpe ratio of 0.917 and volatility of 16.7%; an equal-weight portfolio of the twelve ETFs has a Sharpe ratio of 0.810 and volatility of 13.4%; a static 60% SPY / 40% TLT portfolio has a Sharpe ratio of 0.935. The honest strategy's mean Sharpe is 0.821. The benchmark is about validity, not about beating the market.

## 3.2 Honest pipeline

The candidate pool uses sixteen signals, all computed from adjusted closes up to and including date \(t\):

- momentum over 5, 10, 20, 40, 60, 120, and 250 trading days;
- negative 20-day and 60-day realized volatility (`lowvol20`, `lowvol60`);
- negative 14-day RSI (`rsi14`);
- 20-day volatility z-score, negated (`volz20`);
- 20-day price-to-moving-average trend (`trend20`);
- 60-day drawdown from the running maximum (`dd60`);
- cross-sectional 20-day momentum rank (`cs_mom20`);
- cross-sectional 20-day low-volatility rank (`cs_vol20`);
- a composite of cross-sectionally z-scored 20-day momentum, 60-day momentum, and 20-day trend (`combo`).

A candidate is a triple of signal, \(k\in\{1,2,3,4\}\), and weighting in {equal, inverse volatility}, for \(16\times4\times2=128\) candidates. At each weekly rebalance, the strategy ranks the available assets by the signal, selects the top \(k\), and assigns either equal weights \(1/k\) or inverse-volatility weights normalized to sum to one. It is long-only and fully invested in the selected assets; if fewer than \(k\) assets are valid, it holds cash for that period.

Let \(w_{i,t+1}\) be the target weight for asset \(i\) formed from the close at \(t\) and applied to the return on \(t+1\). The daily strategy return is

$$
r^{\text{strat}}_{t+1}=\sum_i w_{i,t+1}r_{i,t+1}-c_{t+1},
$$

where \(c_{t+1}\) is the one-way turnover cost, 5 basis points per unit of turnover, charged when the new target is installed. The honest protocol uses lag 1: a signal formed at the close of \(t\) cannot earn the return on \(t\). The same-bar family uses lag 0 and therefore earns the return on the signal date.

For each evaluation year \(y\), the selector uses all daily returns through 31 December of \(y-1\), minus a two-trading-day embargo, and chooses the candidate with the highest non-annualized Sharpe ratio, provided it has at least 126 observations. The selected candidate is applied to the following year. If no candidate has enough history, the selector falls back to the candidate with the most valid observations. This is an expanding-window walk-forward, not a shuffled or k-fold procedure.

## 3.3 Candidate sampling and dependence

Choosing from all 128 candidates in every replicate is computationally feasible, but it makes the selection problem easier than a realistic research process in which a small number of ideas is tried. We therefore sample 40 candidates without replacement for each replicate, using seed `20261025`, and use the same subset for the honest and contaminated runs. The process is repeated 80 times. The 40-candidate search is the basis for the DSR and reality-check trial counts.

The candidate matrix is highly correlated. Over the evaluation window, the mean pairwise correlation is 0.609, the participation ratio of the correlation eigenvalues is 2.46, and 10 principal components explain 90% of the variance. The effective number of independent trials is therefore much smaller than 40. This weakens the multiple-testing penalty and helps explain the DSR inversion. The dependence is a feature of the object being studied, not a nuisance to be removed.

## 3.4 Contamination families

Each family changes exactly one part of the pipeline. The honest pipeline is the control; the contaminated pipeline is otherwise identical. Table 2 summarizes the mechanisms.

**Table 2.** Contamination families.

| Family | What changes | Implementation | Real-world analogue | Expected signature |
|---|---|---|---|---|
| `same_bar_fill` | Timing | Lag 0 instead of lag 1 | Using the same bar's close to fill an order and earn that bar's return | Sharpe rises because the signal and return share the same close |
| `target_feature` | Features | Add \(1.0\times z_{\text{cs}}(r_{t+1:t+5})\) to every base signal | Peeking at future returns; target leakage in feature construction | Very large Sharpe; signal is partly the future |
| `full_sample_target_encoding` | Features / normalization | Replace every signal with the asset's full-sample mean daily return | Computing target statistics or normalizations on the full sample | Static tilt toward ex-post winners; modest but persistent inflation |
| `shuffled_cv` | Selection / validation | Assign test-window observations to five random folds and select by mean fold Sharpe | Shuffled cross-validation that ignores time order and uses the test window | Modest inflation; selection uses future test data |
| `survivorship` | Universe | Include asset \(i\) at \(t\) only if \(r_{i,t+1:t+252}\ge0\) or the forward return is missing | Selecting the current universe with hindsight; survivorship-filtered data | Moderate inflation; portfolio avoids future losers |
| `p_hacked_selection` | Selection | In each test year, choose the candidate with the highest Sharpe in that same year | Test-set p-hacking; choosing the best backtest after seeing the test period | Moderate inflation; the reported rule changes every year |

**Same-bar fill.** The signal at the close of \(t\) is applied to the return on \(t\). This is the simplest timing leak: the backtest assumes it can trade at a price that is only known at the end of the bar and still earn that bar's return. The implementation keeps the weekly rebalance and cost model; only the lag changes from 1 to 0.

**Target-feature leakage.** For each base signal \(s_{i,t}\), the contaminated signal is

$$
\tilde s_{i,t}=z_{\text{cs}}(s_{i,t})+\lambda\,z_{\text{cs}}(r_{i,t+1:t+5}),
\qquad \lambda=1.0.
$$

The second term is the cross-sectional z-score of the next five trading days' return, computed with `prices.shift(-5)`. The signal is standardized cross-sectionally before the leak is added; the leak is not a small perturbation. It is a direct forecast of the near future. This family is intentionally extreme: it tests whether a diagnostic can detect a leak that dominates the signal.

**Full-sample target encoding.** Every one of the sixteen signals is replaced by the same frame: the asset's mean daily return over the full sample, repeated on every date. The resulting signal is a static per-asset tilt toward assets that did well over the entire sample. The name reflects the mechanism—computing a target statistic on the full sample and using it as a feature—not a categorical target encoder. Because all sixteen signal names share the same frame, the 40-candidate matrix contains only eight unique portfolios (four \(k\) values times two weightings). The selected portfolio is stable across replicates, so the across-replicate confidence interval is very narrow. That narrow interval is a property of the degenerate candidate matrix, not evidence of precision about the leak.

**Shuffled cross-validation.** The evaluation window is partitioned into five folds by a random assignment that ignores time order. For each candidate, the mean Sharpe across folds is computed, and the candidate with the highest mean is selected. The reported return series is that candidate's return over the entire evaluation window. This mimics a cross-validation procedure that shuffles observations, selects on the test window, and then reports full-window performance. It is a selection leak, not a return-column leak: the candidate matrix is the honest matrix.

**Survivorship.** At each rebalance date \(t\), asset \(i\) is eligible only if its forward 252-trading-day return is non-negative or missing:

$$
u_{i,t}=\mathbf{1}\{r_{i,t+1:t+252}\ge0\ \text{or}\ r_{i,t+1:t+252}\ \text{is missing}\}.
$$

The portfolio selects the top \(k\) among eligible assets. This is an extreme form of survivorship: it removes assets that will underperform over the next year. Real survivorship bias usually operates through delistings and database membership, not through a perfect one-year forecast. The family is deliberately strong so that a diagnostic has a fair chance to detect it.

**Test-set p-hacking.** For each calendar year in the evaluation window, the oracle selects the candidate with the highest Sharpe ratio *in that same year*, then concatenates the selected returns across years. This is the clearest form of test-set selection: the reported rule is chosen with knowledge of the test outcome, and it can change every year. The candidate matrix is the honest matrix; the leak is entirely in the selection procedure.

## 3.5 Diagnostics and orientations

Table 3 fixes the interpretation used throughout. The column "suspicion score" is the quantity calibrated at a 5% false-positive rate on honest controls; higher means more suspicious. For publication filters, the suspicion score is oriented so that a *more publishable* result is *more suspicious*, because leakage manufactures publishability. For validity heuristics, a higher failure probability or larger instability is suspicious. The audit is a direct paired test.

**Table 3.** Diagnostics.

| Diagnostic | Question it answers | Suspicion score | Publication rule | Structural blind spot |
|---|---|---|---|---|
| Deflated Sharpe ratio (DSR) | Is the reported Sharpe surprising given the number and dispersion of trials? | \(1-\mathrm{DSR}\) | \(\mathrm{DSR}\ge0.95\) | Tests sampling and selection, not implementation; leakage can raise DSR |
| Reality check (Šidák) | Is the best strategy significant after adjusting for \(N\) trials? | \(1-p_{\text{adj}}\) | \(p_{\text{adj}}\le0.05\) | Treats a significant result as *good*; ignores dependence; not White's full bootstrap |
| Probability of backtest overfitting (PBO) | Is the in-sample winner stable out of sample? | \(\mathrm{PBO}\) | \(\mathrm{PBO}\le0.05\) (not used here) | Only evaluates the "pick the in-sample best column" rule; blind to other selection rules |
| Split-half degradation | Did the first half outperform the second half? | \(z_{\text{split}}\) | \(z_{\text{split}}\le0\) (not used here) | One-sided; misses leaks that improve the second half; misses static leaks |
| Artifact audit | Is the reported Sharpe higher than a re-executed honest pipeline? | \(1-p_{\text{audit}}\) | \(p_{\text{audit}}\le0.05\) | Requires pipeline and data access; low power for small leaks; assumes the honest comparator is correct |
| Composite screen | Does any returns-only validity signal fire? | \(\max\) standardized PBO, reverse RC, split | 95th percentile of honest | Heuristic; inherits every component's blind spot |

Two conventions matter. First, the **reality-check suspicion score is \(1-p\), not \(p\)**. A very small adjusted p-value means the strategy looks unusually significant. Under the leakage hypothesis, that is a warning sign, not a clean bill of health. This is a *reverse* use of the reality check. The nominal publication rule \(p\le0.05\) is reported separately and is not the same object.

Second, the **composite excludes DSR**. The DSR is a publication filter whose suspicion score moves in the wrong direction under leakage: contaminated pipelines have *higher* DSR, hence *lower* \(1-\mathrm{DSR}\). Including it in a max-score composite dilutes detection and raises the honest threshold. The composite also excludes the audit because the audit requires a different data requirement (the honest comparator's return series). The composite is therefore a returns-only triage, not a validity proof.

## 3.6 Calibration and metrics

For every gate except the audit, the threshold is the 95th percentile of the honest suspicion distribution (empirical, `method="higher"`). For the audit, the threshold is the nominal 5% level, \(p\le0.05\). The composite standardizes each component by the honest interquartile range, takes the maximum, and thresholds at the 95th percentile of the honest composite. The false-positive rate (FPR) is the fraction of honest replicates flagged; the true-positive rate (TPR) is the fraction of contaminated replicates flagged. Wilson [-@wilson1927probable] 95% intervals are reported for TPR. AUC is computed across the 80 honest and 80 contaminated scores for each family; 0.5 is chance and 0.0 is a perfectly inverted score.

# 4. Results

## 4.1 Leakage inflates the Sharpe ratio

Table 4 reports the mean annualized Sharpe ratio for the honest control and each family, with 95% confidence intervals across 80 replicates and the mean inflation relative to the paired honest run.

**Table 4.** Reported Sharpe ratios and paired inflation.

| Family | Mean SR | 95% CI | Mean inflation | 95% CI |
|---|---:|---:|---:|---:|
| Honest | 0.821 | [0.802, 0.840] | — | — |
| Same-bar fill | 2.048 | [2.021, 2.075] | +1.227 | [1.189, 1.265] |
| Target feature | 6.842 | [6.824, 6.859] | +6.021 | [5.992, 6.049] |
| Full-sample encoding | 0.980 | [0.980, 0.980] | +0.159 | [0.140, 0.178] |
| Shuffled CV | 0.990 | [0.974, 1.007] | +0.169 | [0.150, 0.188] |
| Survivorship | 1.198 | [1.160, 1.236] | +0.377 | [0.341, 0.412] |
| P-hacked selection | 1.477 | [1.459, 1.495] | +0.656 | [0.628, 0.684] |

Every family's inflation interval excludes zero. The ordering is intuitive: a direct five-day future return is the largest leak; a same-bar close is next; test-set selection and survivorship are moderate; full-sample encoding and shuffled CV are small. The full-sample interval is narrow because the candidate matrix collapses to eight unique portfolios, as explained in Section 3.4.

![Reported annualized Sharpe ratio by pipeline family across 80 replicates. The honest control is centered below 1; every contamination family is shifted upward. The full-sample family has almost no visible dispersion because its candidate matrix is degenerate.](../results/figures/sr_by_family.png){#fig:sr}

## 4.2 Publication filters are not validity checks

Table 5 applies the two most common publication rules: DSR at least 0.95, and the nominal Šidák-adjusted reality check at most 0.05.

**Table 5.** Nominal publication rates.

| Family | Publishable by DSR | Publishable by nominal RC |
|---|---:|---:|
| Honest | 0.000 | 0.600 |
| Same-bar fill | 1.000 | 1.000 |
| Target feature | 1.000 | 1.000 |
| Full-sample encoding | 1.000 | 1.000 |
| Shuffled CV | 0.525 | 1.000 |
| Survivorship | 0.988 | 0.988 |
| P-hacked selection | 1.000 | 1.000 |

The DSR column is an inversion. Not a single honest replicate reaches the 0.95 publication threshold, while every replicate of four families and 98.8% of survivorship do. The mechanism is not subtle. Leakage raises the reported Sharpe and makes the candidate returns more similar; the estimated variance of trial Sharpes falls, the expected maximum under the null falls, and the DSR rises. The DSR is answering "is this Sharpe surprising given the trial dispersion?", and leakage makes the answer "no, it is exactly what a strong signal would produce."

The reality-check column is permissive. The honest mean Sharpe is 0.821; with 3,520 daily observations and 40 trials, a Sharpe of roughly 0.8 is often significant after the Šidák adjustment. Sixty percent of honest controls pass the nominal 5% rule. The filter is not calibrated to a 5% false-positive rate in this sample; it is a publication rule with low specificity. The contaminated families pass at 98.8–100%. A researcher who treats \(p_{\text{adj}}\le0.05\) as evidence of validity will publish both honest and contaminated backtests at high rates.

This is why the benchmark separates the *publication filter* role from the *detection* role. A significant result is not a validity certificate. A non-significant result is not proof of leakage. The two questions are different.

## 4.3 Detection matrix

Table 6 is the central result. Each column is a suspicion score calibrated at a 5% false-positive rate on the honest controls, except the audit, which uses its nominal 5% level. The table reports TPR; the last row reports FPR. Wilson 95% intervals are in Appendix B.

**Table 6.** Detection at a 5% false-positive rate (TPR unless noted).

| Family | DSR | PBO | Reverse RC | Split-half | Composite | Audit |
|---|---:|---:|---:|---:|---:|---:|
| Same-bar fill | 0.000 | 0.000 | 1.000 | 0.350 | 1.000 | 1.000 |
| Target feature | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Full-sample encoding | 0.000 | 1.000 | 1.000 | 0.000 | 1.000 | 0.038 |
| Shuffled CV | 0.000 | 0.025 | 0.688 | 0.000 | 0.550 | 0.350 |
| Survivorship | 0.000 | 0.675 | 0.950 | 0.100 | 1.000 | 0.675 |
| P-hacked selection | 0.000 | 0.025 | 1.000 | 0.038 | 1.000 | 0.963 |
| **FPR** | **0.038** | **0.025** | **0.038** | **0.025** | **0.038** | **0.000** |

![True-positive rate at a 5% false-positive rate by family and diagnostic. The DSR is uniformly zero; the reverse reality check and composite are strong on large leaks; the audit is the only diagnostic that catches same-bar and p-hacked selection without relying on extreme Sharpe alone.](../results/figures/detection_tpr.png){#fig:tpr}

The DSR's detection rate is zero for every family. Its AUC is 0.000 for same-bar, target, full-sample, and p-hacked; 0.080 for shuffled; and 0.002 for survivorship. A value below 0.5 means the score ranks contaminated runs as *less* suspicious than honest ones. This is the inversion in ranking form, not just a threshold artifact.

PBO has a distinctive pattern. It detects full-sample encoding at 100% and survivorship at 67.5%, but it is zero for same-bar and target, and 2.5% for shuffled and p-hacked. The zeroes are not a failure to see the leak; they are a consequence of what PBO measures. Same-bar and target leakage produce a candidate that is genuinely better out of sample, so the in-sample winner remains strong; PBO sees stability, not contamination. For shuffled and p-hacked selection, the candidate matrix is the honest matrix, so PBO is identical to the honest control by construction. PBO is a selection-stability diagnostic, not a leakage detector.

The reverse reality check is the strongest returns-only score on this benchmark: 100% for same-bar, target, full-sample, and p-hacked; 95.0% for survivorship; 68.8% for shuffled. The interpretation is not that the reality check is a good validity test. It is that leakage makes strategies look *too significant*, and a reverse significance screen picks that up. The same statistic used as a publication filter would publish 60% of honest controls (Table 5). The orientation determines whether it looks like a solution or a failure.

Split-half degradation is complementary but narrow. It detects target leakage at 100% and same-bar at 35.0%, but it misses full-sample and shuffled entirely. For p-hacked selection, the median split-half z is negative (\(-0.37\)): the second half is often *better* than the first because annual oracle selection picks winners. A one-sided degradation test cannot see that. The two-sided variant discussed in Section 4.6 would raise p-hacked detection but lower same-bar detection; neither variant dominates.

The composite screen—maximum standardized PBO, reverse RC, and split-half—detects 100% of five families and 55.0% of shuffled CV at a 3.8% FPR. It is a useful triage, not a proof. It is dominated by the reverse RC on high-Sharpe leaks; it catches full-sample through PBO; and it catches survivorship through the combination of PBO and reverse RC. The shuffled-CV leak is small enough (+0.169 Sharpe) that no returns-only score is reliable.

The audit is the only diagnostic that directly tests implementation. It detects same-bar and target leakage at 100%, p-hacked selection at 96.3%, survivorship at 67.5%, shuffled CV at 35.0%, and full-sample encoding at 3.8%. Its AUC is 1.000 for same-bar, target, full-sample, and p-hacked; 0.994 for survivorship; and 0.988 for shuffled. The gap between AUC and TPR is the story of Section 4.4.

![Suspicion-score distributions for the honest control and all contaminated families. The DSR panel is shifted the wrong way: contaminated runs have lower \(1-\mathrm{DSR}\). The PBO panel is bimodal because stable leaks and unstable leaks behave differently.](../results/figures/gate_distributions.png){#fig:dist}

## 4.4 The audit is powerful but power-limited

Table 7 reports the audit p-value distribution and the flag rate at \(p\le0.05\).

**Table 7.** Audit p-values and flag rates.

| Family | 5th percentile | Median | Flag rate |
|---|---:|---:|---:|
| Honest | 1.000 | 1.000 | 0.000 |
| Same-bar fill | 0.002 | 0.002 | 1.000 |
| Target feature | 0.002 | 0.002 | 1.000 |
| Full-sample encoding | 0.082 | 0.271 | 0.038 |
| Shuffled CV | 0.008 | 0.133 | 0.350 |
| Survivorship | 0.002 | 0.017 | 0.675 |
| P-hacked selection | 0.002 | 0.008 | 0.963 |

The audit's detection rate is a monotone function of the size of the leak. Full-sample encoding adds 0.159 Sharpe and is flagged 3.8% of the time; shuffled CV adds 0.169 and is flagged 35.0%; survivorship adds 0.377 and is flagged 67.5%; p-hacked selection adds 0.656 and is flagged 96.3%; same-bar and target add more than 1.2 and are flagged 100%. The AUC is near 1 for every family, including full-sample. Almost every contaminated replicate has a positive Sharpe difference (97.5% for shuffled CV and 98.8% for survivorship; all replicates in the other families); the problem is that a fourteen-year sample cannot always distinguish a 0.16 Sharpe difference from noise at the 5% level.

This is the correct way to read the audit. It is a *validity check with a power curve*, not a binary oracle. A non-significant audit is not a clean bill of health, especially when the reported Sharpe is only modestly above the honest benchmark. A significant audit is strong evidence that the reported pipeline is not reproducing the honest pipeline, but it does not prove *which* leak is responsible; the code and data still need to be inspected.

![Detection power versus mean Sharpe inflation for the composite screen and the artifact audit. Both rise with the size of the leak. The audit is stronger on same-bar and p-hacked selection; the composite is stronger on full-sample encoding; both are weak on the small shuffled-CV leak.](../results/figures/audit_vs_combined.png){#fig:power}

The union of the composite and the audit detects 100% of same-bar, target, full-sample, survivorship, and p-hacked families, and 62.5% of shuffled CV, at a 3.8% FPR. That sounds stronger than it is. The composite already catches five families at 100%; the audit adds only 7.5 percentage points on shuffled CV and no incremental detection on the others. The audit's value is not incremental TPR on this benchmark. It is *mechanism-specific evidence*: it can distinguish a high-Sharpe strategy that reproduces honestly from one that does not, which a returns-only screen cannot do.

## 4.5 Why the diagnostics disagree

The disagreements are not noise. They follow from the questions the diagnostics ask.

- **DSR and RC** are functions of the reported Sharpe and the trial count. Leakage raises the numerator and often increases trial correlation, which lowers the effective number of trials. Both effects make the result look more credible. These diagnostics answer "is this result surprising under a null of no skill?"; they do not observe the implementation.
- **PBO** is a function of the candidate matrix and the rule "pick the in-sample best." It observes stability, not causality. Stable leaks look stable; selection rules that are not "pick the in-sample best" are invisible.
- **Split-half** observes the time path of the selected return series. It catches degradation, not improvement, and it cannot see a static leak whose return path is smooth in both halves.
- **The audit** observes the implementation, but only through the lens of a Sharpe difference. It has power when the leak moves the Sharpe enough relative to sampling noise; it has little power when the leak is small.
- **The composite** is a max of standardized returns-only scores. It inherits the strengths and blind spots of its components. It is a triage rule, not a structural test.

## 4.6 Supplementary analyses

**Two-sided split-half.** The one-sided definition is a design choice. Using \(|z_{\text{split}}|\) raises p-hacked detection from 3.8% to 23.7% but lowers same-bar detection from 35.0% to 2.5%. There is no free lunch: the two-sided test sees improvement as well as degradation, but it also loses power against leaks that produce a first-half advantage.

**Audit and composite are not substitutes.** The audit is the only gate that uses the honest comparator's return series. The composite is the only gate that requires nothing beyond the candidate matrix and the reported returns. A practical workflow can use the composite as a triage and the audit as a confirmation, but it should not treat either as a proof of validity.

**Universe design is itself a survivorship choice.** The twelve ETFs are selected because they are liquid and have long histories as of the analysis date. This is a form of survivorship in the universe design, independent of the explicit `survivorship` family. The benchmark does not reconstruct a point-in-time ETF universe, and absolute performance should not be read as a live strategy result.

# 5. A practical protocol

The results support a conservative workflow, not a single test.

1. **Freeze the implementation and the data.** Record a manifest with file hashes, row counts, date ranges, and package versions. The benchmark's `data/raw/manifest.json` and `results/run_manifest.json` are examples.
2. **Use nested walk-forward evaluation with an embargo.** Never select on the evaluation window. The honest protocol selects through the prior year minus two trading days and applies the choice to the next year.
3. **Report the candidate count and the correlation structure.** A DSR or reality check with 40 highly correlated trials is not the same as one with 40 independent trials. In this benchmark the participation ratio is 2.46, so the effective trial count is far below 40.
4. **Treat DSR and reality-check p-values as publication filters.** Report them, but do not describe a high DSR or a small adjusted p-value as evidence that the backtest is valid. The DSR can be inverted by leakage; the nominal reality check can publish 60% of honest controls.
5. **Use PBO and split-half as stability diagnostics.** They are cheap and complementary. PBO catches unstable selection and static tilts; split-half catches first-half degradation. Neither is a leakage detector on its own.
6. **Audit any extreme result.** Re-execute the honest pipeline on the same data and compare the reported and honest return series. A paired block bootstrap gives a power-aware p-value. If the audit is underpowered, say so; do not interpret a non-significant audit as validation.
7. **Report effect sizes and intervals.** A Sharpe inflation of 0.16 is economically small but statistically detectable in some samples and not others. A binary "pass/fail" hides the power problem.
8. **Pre-register the candidate pool when possible.** The number of trials is a design choice. A pre-registered pool is more credible than a post hoc count, even if the count is honest.
9. **Separate the question "is it significant?" from "is it real?"** The first is a statistical question; the second is an implementation and data question.

# 6. Limitations

**Constructed leaks.** The six families are deliberately clean and strong. Real leakage is often partial, intermittent, or entangled with legitimate feature engineering. The benchmark measures detectability under controlled conditions, not prevalence.

**Universe and asset class.** Twelve US ETFs, long-only, weekly rebalance, no shorting, no leverage, no borrow, no capacity, no market impact, and no taxes. The mechanisms are generic, but the detection rates are not necessarily transferable to equities, futures, intraday data, or large alpha libraries.

**Cost model.** Five basis points per unit of one-way turnover is a simple approximation. It does not model bid-ask spreads, market impact, borrow costs, or financing. The honest and contaminated pipelines use the same cost model, so the comparison is internally valid, but the absolute Sharpe levels are not deployable.

**Evaluation period.** 2012–2025 includes the COVID-19 shock, the 2022 rate cycle, and a strong US equity trend. Regime dependence is not modeled. A different period could change the relative performance of signals and the power of the audit.

**Replicates and inference.** Eighty replicates give Wilson intervals of roughly \(\pm0.1\) for TPRs near 0.5 and \(\pm0.05\) for TPRs near 1. The family-level rates are descriptive; we do not test differences between gates formally. A single seed is used. A seed-robustness study would be a useful extension.

**Audit assumptions.** The audit compares the reported series with a deterministic honest comparator. The honest control's false-positive rate is zero by construction, not empirically estimated. The bootstrap is a confidence-distribution procedure, not a formal randomization test. Block length, the number of bootstrap draws, and the choice of Sharpe difference are tuning choices; we did not perform a sensitivity analysis. The audit also assumes the honest comparator is correctly specified. If the "honest" pipeline contains a subtle leak, the audit will not catch it.

**DSR and reality check.** The DSR implementation uses the variance of trial Sharpe ratios, not the full covariance matrix of trial returns, and relies on asymptotic normality and skew/kurtosis corrections. The Šidák reality check assumes independence and is conservative; it is not White's full bootstrap and does not account for cross-trial dependence. The nominal 5% publication rate for honest controls (60%) shows that the adjustment is not calibrated to this sample.

**PBO.** PBO is computed on the candidate matrix and assumes the selection rule is "pick the in-sample best column." It is structurally blind to shuffled CV, annual oracle selection, and other selection procedures that are not column selection. Ties and near-degenerate candidate matrices can also distort PBO; the full-sample family is an example.

**Split-half.** The one-sided definition is a choice. It catches degradation, not improvement, and it is sensitive to the split date. A two-sided or rolling variant would give different results.

**Survivorship.** The forward-252-day filter is an extreme form of survivorship. Real survivorship operates through delistings, database membership, and backfilled returns. The family should be read as a stress test, not a calibration of real survivorship bias.

**Data.** Yahoo Finance adjusted closes are convenient and public but not a point-in-time institutional database. Adjusted prices incorporate dividends and splits, but the vendor may revise history. The raw responses are cached and hashed, but the vendor's terms and availability are outside our control. HYG starts in April 2007; the first ten weeks have eleven assets. Forward-fill is limited to three days; no attempt is made to reconstruct a point-in-time universe.

**Multiple comparisons.** Six families and six diagnostics produce a 6×6 matrix. We report the matrix descriptively and do not adjust family-level comparisons for multiplicity. The benchmark is a designed experiment, not a confirmatory clinical trial.

**External validity of the composite.** The composite is calibrated on the honest controls in this benchmark. Its 3.8% FPR and high TPR are in-sample properties of the calibration. A different universe or period could shift the thresholds. The composite should be re-calibrated, not transplanted.

# 7. Reproducibility

## 7.1 Requirements

- Python 3.12.
- The packages in `pyproject.toml`; `constraints.txt` pins the versions used for the reported results.
- Docker 24+ for the container path.

## 7.2 Local commands

```bash
cd fakealpha-benchmark
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt

fakealpha fetch --config config/experiment.yaml
fakealpha run --config config/experiment.yaml
fakealpha report --config config/experiment.yaml

pytest -q
ruff check src tests
```

The full run takes about 48 seconds on the development machine used for this paper, plus data-fetch time. The `fetch` step writes `data/raw/*.json`, `data/raw/manifest.json`, `data/processed/prices.csv`, and `data/processed/returns.csv`. The `run` step writes `results/tables/per_replicate.csv`, `summary.csv`, `honest_controls.csv`, `thresholds.json`, the figures, and `results/run_manifest.json`.

## 7.3 Docker

```bash
docker compose build
docker compose run --rm fakealpha
```

The Compose service runs `python -m fakealpha reproduce --config config/experiment.yaml` and mounts `./data` and `./results`. The Docker image pins the package versions in `constraints.txt`, copies the tests and documentation, and uses `MPLBACKEND=Agg`.

## 7.4 What is recorded

- Raw Yahoo JSON per symbol, with SHA-256 hashes in `data/raw/manifest.json`.
- The processed panel and return matrix.
- Per-replicate scores for all 560 replicate-family rows.
- The summary table, honest-control table, thresholds, and figures.
- `results/run_manifest.json`, which records the config, Python version, platform, package versions, data manifest, metadata, and summary.
- The test suite (21 tests at the time of writing) and the lint configuration.

## 7.5 Determinism

The random seed is `20261025`. Candidate subsets, bootstrap indices, and shuffled-CV fold assignments are derived from it. The honest and contaminated runs within a replicate share the candidate subset and the seed. The pipeline is deterministic given the same data and package versions. Minor numerical differences can appear across BLAS, NumPy, or SciPy versions; the manifest records the versions used.

## 7.6 Data availability

The raw Yahoo responses are cached locally and hashed. They are not redistributed as a dataset in this repository; users should refetch them subject to Yahoo's terms. The processed panel can be rebuilt from the cached raw responses with `fakealpha fetch` (which reuses the cache unless `--force` is set). The manifest is sufficient to detect a changed raw file.

# 8. Conclusion

Leakage looks like alpha. It raises the Sharpe ratio, stabilizes the candidate matrix, and makes the backtest look more publishable. The diagnostics that researchers commonly use to argue that a backtest is credible are not designed to detect this failure. The deflated Sharpe ratio can move in the wrong direction; the Šidák reality check can publish a majority of honest controls at its nominal 5% level; PBO sees stability, not causality; split-half sees degradation, not improvement; and the artifact audit, the only direct implementation check, is underpowered for small leaks.

The practical implication is not that backtesting is hopeless. It is that validity is an implementation property, not a p-value. A high Sharpe ratio should trigger a code-and-data audit. A low DSR or a high reality-check p-value should not be treated as proof of leakage, and a high DSR or a small p-value should not be treated as proof of validity. Use PBO and split-half as cheap stability diagnostics, use the reverse reality check as a "too good to be true" trigger, and audit the pipeline when the result matters.

The benchmark is deliberately small and reproducible. Its value is not a leaderboard of detectors but a demonstration of *where* each detector is blind. The code, data manifest, tests, tables, and figures are released so that the demonstration can be repeated, criticized, and extended.

# Appendix A. Gate definitions

## A.1 Sharpe ratio

For daily returns \(r_t\),

$$
\widehat{SR}=\frac{\bar r}{s_r}\sqrt{252},
$$

where \(s_r\) is the sample standard deviation with \(n-1\) denominator. The risk-free rate is set to zero. All Sharpe ratios in the tables are annualized unless stated otherwise.

## A.2 Deflated Sharpe ratio

Let \(\widehat{SR}_n\) be the non-annualized Sharpe of trial \(n\), \(N\) the number of trials, and \(\widehat{\mathrm{Var}}(\widehat{SR}_n)\) the sample variance of the trial Sharpes. The expected maximum under the null is

$$
\widehat{SR}_0=
\sqrt{\widehat{\mathrm{Var}}(\widehat{SR}_n)}
\left[(1-\gamma)z_{1-1/N}+\gamma z_{1-1/(Ne)}\right],
$$

where \(\gamma=0.5772156649\) is the Euler–Mascheroni constant and \(z\) is the standard normal quantile. The DSR is

$$
\mathrm{DSR}=\Phi\!\left(
\frac{(\widehat{SR}-\widehat{SR}_0)\sqrt{T-1}}
{\sqrt{1-\widehat{\gamma}_3\widehat{SR}
+\frac{\widehat{\gamma}_4-1}{4}\widehat{SR}^2}}
\right).
$$

The implementation uses the 40 candidate columns in the replicate's matrix and the same reported return series as the other gates.

## A.3 PBO

With \(S=10\) contiguous blocks and all \(\binom{10}{5}=252\) splits, the in-sample best column \(c^*\) is selected by Sharpe. Its out-of-sample rank \(\omega_{c^*}\) is the fraction of columns with lower out-of-sample Sharpe, with ties resolved by the implementation's strict comparison. The logit is

$$
\lambda_{c^*}=\log\!\left(\frac{\omega_{c^*}}{1-\omega_{c^*}}\right),
$$

and

$$
\mathrm{PBO}=\frac{1}{|\mathcal{S}|}\sum_{s\in\mathcal{S}}\mathbf{1}\{\lambda_{c^*,s}\le0\}.
$$

## A.4 Reality check

$$
p_{\text{single}}=1-\Phi\!\left(\frac{\bar r}{s_r}\sqrt{T}\right),
\qquad
p_{\text{adj}}=1-(1-p_{\text{single}})^N.
$$

The suspicion score is \(1-p_{\text{adj}}\). The nominal publication rule is \(p_{\text{adj}}\le0.05\).

## A.5 Split-half

$$
z_{\text{split}}=
\frac{\widehat{SR}_1-\widehat{SR}_2}
{\sqrt{\frac{1}{n_1}+\frac{1}{n_2}}},
$$

where \(\widehat{SR}_1\) and \(\widehat{SR}_2\) are non-annualized Sharpe ratios in the two halves. The suspicion score is \(z_{\text{split}}\).

## A.6 Audit

For bootstrap path \(b\),

$$
\Delta SR_b=
SR(\tilde r_b^{\text{reported}})-SR(\tilde r_b^{\text{honest}}),
$$

and

$$
p_{\text{audit}}=\frac{1+\#\{b:\Delta SR_b\le0\}}{B+1},
$$

with \(B=500\) and circular blocks of 20 trading days. The suspicion score is \(1-p_{\text{audit}}\).

## A.7 Composite

Let \(x_{g,i}\) be the suspicion score for gate \(g\) and replicate \(i\), \(q_g\) the honest 95th percentile, and \(s_g\) the honest interquartile range. The composite is

$$
C_i=\max_{g\in\{\mathrm{PBO},\mathrm{RC},\mathrm{split}\}}
\frac{x_{g,i}-q_g}{\max(s_g,10^{-6})}.
$$

The threshold is the honest 95th percentile of \(C_i\). DSR and audit are excluded, as explained in Section 3.5.

# Appendix B. Additional results

## B.1 Honest controls

| Statistic | Value |
|---|---:|
| Replicates | 80 |
| Mean Sharpe | 0.821 |
| Median Sharpe | 0.842 |
| Standard deviation | 0.087 |
| Minimum Sharpe | 0.550 |
| Maximum Sharpe | 0.953 |
| Publishable by DSR | 0.000 |
| Publishable by nominal RC | 0.600 |
| Mean suspicion, DSR | 0.158 |
| Mean suspicion, PBO | 0.216 |
| Mean suspicion, reverse RC | 0.931 |
| Mean suspicion, split-half | −0.123 |
| Mean suspicion, audit | 0.000 |

## B.2 Thresholds

| Gate | Honest 95th percentile of suspicion | Detection rule |
|---|---:|---|
| DSR | 0.317 | \(1-\mathrm{DSR}>0.317\) |
| PBO | 0.353 | \(\mathrm{PBO}>0.353\) |
| Reverse RC | 0.990 | \(1-p_{\text{adj}}>0.990\) |
| Split-half | 0.485 | \(z_{\text{split}}>0.485\) |
| Composite | 0.051 | \(C_i>0.051\) |
| Audit | 0.950 | \(1-p_{\text{audit}}>0.950\), i.e. \(p_{\text{audit}}\le0.05\) |

## B.3 Wilson intervals for composite and audit TPR

| Family | Composite TPR | 95% CI | Audit TPR | 95% CI |
|---|---:|---:|---:|---:|
| Same-bar fill | 1.000 | [0.954, 1.000] | 1.000 | [0.954, 1.000] |
| Target feature | 1.000 | [0.954, 1.000] | 1.000 | [0.954, 1.000] |
| Full-sample encoding | 1.000 | [0.954, 1.000] | 0.038 | [0.013, 0.105] |
| Shuffled CV | 0.550 | [0.441, 0.654] | 0.350 | [0.255, 0.459] |
| Survivorship | 1.000 | [0.954, 1.000] | 0.675 | [0.566, 0.768] |
| P-hacked selection | 1.000 | [0.954, 1.000] | 0.963 | [0.895, 0.987] |

## B.4 AUC by diagnostic

| Family | DSR | PBO | Reverse RC | Split-half | Audit |
|---|---:|---:|---:|---:|---:|
| Same-bar fill | 0.000 | 0.000 | 1.000 | 0.808 | 1.000 |
| Target feature | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| Full-sample encoding | 0.000 | 1.000 | 1.000 | 0.775 | 1.000 |
| Shuffled CV | 0.080 | 0.500 | 0.950 | 0.674 | 0.988 |
| Survivorship | 0.002 | 0.876 | 0.981 | 0.493 | 0.994 |
| P-hacked selection | 0.000 | 0.500 | 1.000 | 0.311 | 1.000 |

## B.5 Reproduction checklist

- [ ] `git status` is clean and the commit hash is recorded.
- [ ] `constraints.txt` matches the package versions in `results/run_manifest.json`.
- [ ] `data/raw/manifest.json` has status `ok` for all symbols.
- [ ] `fakealpha fetch` reproduces the panel row count (4,984) and date range.
- [ ] `pytest -q` passes all tests.
- [ ] `ruff check src tests` passes.
- [ ] `fakealpha run` reproduces the summary table within numerical tolerance.
- [ ] Figures are regenerated from the per-replicate CSV, not hand-edited.
- [ ] The Docker path produces the same table schema and FPR/TPR pattern.
- [ ] Any deviation is documented in the paper or the manifest.

# References

::: {#refs}
:::

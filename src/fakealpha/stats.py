"""Selection-aware and reproducibility statistics.

The benchmark separates three roles. Publication filters (the deflated Sharpe
ratio and the multiple-testing-adjusted reality check) ask whether a result
looks publishable; because leakage inflates that appearance, the corresponding
suspicion scores are ``1 - DSR`` and ``1 - p``. Validity heuristics (PBO and
split-half degradation) treat overfitting or instability as suspicious. The
artifact audit is a paired re-execution test in which a small p-value is
suspicious. Calibration is always performed on honest controls at a 5%
false-positive rate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

TRADING_DAYS = 252
EULER_GAMMA = 0.5772156649015329


def sharpe(returns: pd.Series | np.ndarray, annualize: bool = True) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3 or values.std(ddof=1) == 0:
        return float("nan")
    ratio = values.mean() / values.std(ddof=1)
    return float(ratio * np.sqrt(TRADING_DAYS)) if annualize else float(ratio)


def deflated_sharpe(returns: pd.Series, candidate_matrix: pd.DataFrame) -> dict:
    """Bailey & Lopez de Prado (2014) deflated Sharpe ratio.

    The trial variance is estimated from the cross-section of candidate
    Sharpes. Returns the non-annualized SR, the expected maximum SR under the
    null, and the deflated probability.
    """
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 60 or values.std(ddof=1) == 0:
        return {"sr": float("nan"), "sr0": float("nan"), "dsr": float("nan")}

    sr = values.mean() / values.std(ddof=1)
    trial_srs = np.array(
        [
            candidate_matrix[c].mean() / candidate_matrix[c].std(ddof=1)
            for c in candidate_matrix.columns
            if candidate_matrix[c].notna().sum() >= 60
            and candidate_matrix[c].std(ddof=1) > 0
        ]
    )
    if trial_srs.size < 2:
        return {"sr": float(sr), "sr0": float("nan"), "dsr": float("nan")}

    trials = trial_srs.size
    sr_variance = np.var(trial_srs, ddof=1)
    z1 = norm.ppf(1.0 - 1.0 / trials)
    z2 = norm.ppf(1.0 - 1.0 / (trials * np.e))
    sr0 = np.sqrt(sr_variance) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)

    skewness = float(skew(values, bias=False))
    kurt = float(kurtosis(values, fisher=False, bias=False))
    denominator = np.sqrt(max(1e-12, 1.0 - skewness * sr + (kurt - 1.0) / 4.0 * sr**2))
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(values.size - 1) / denominator))
    return {"sr": float(sr), "sr0": float(sr0), "dsr": dsr, "trials": int(trials)}


def pbo(matrix: pd.DataFrame, n_blocks: int = 10) -> float:
    """Combinatorially symmetric cross-validation estimate of PBO."""
    aligned = matrix.dropna(how="any")
    if len(aligned) < n_blocks * 10 or aligned.shape[1] < 2:
        return float("nan")
    values = aligned.to_numpy(dtype=float)
    blocks = np.array_split(np.arange(len(values)), n_blocks)
    sums = np.array([values[b].sum(axis=0) for b in blocks])
    sumsq = np.array([(values[b] ** 2).sum(axis=0) for b in blocks])
    counts = np.array([len(b) for b in blocks], dtype=float)

    from itertools import combinations

    logits = []
    for chosen in combinations(range(n_blocks), n_blocks // 2):
        other = [b for b in range(n_blocks) if b not in chosen]
        n_is = counts[list(chosen)].sum()
        n_oos = counts[other].sum()
        mean_is = sums[list(chosen)].sum(axis=0) / n_is
        var_is = sumsq[list(chosen)].sum(axis=0) / n_is - mean_is**2
        sr_is = mean_is / np.sqrt(np.maximum(var_is, 1e-18))
        if not np.isfinite(sr_is).any():
            continue
        best = int(np.nanargmax(sr_is))
        mean_oos = sums[other].sum(axis=0) / n_oos
        var_oos = sumsq[other].sum(axis=0) / n_oos - mean_oos**2
        sr_oos = mean_oos / np.sqrt(np.maximum(var_oos, 1e-18))
        if not np.isfinite(sr_oos[best]):
            continue
        rank = float((sr_oos < sr_oos[best]).sum() + 1)
        logits.append(np.log(rank / (len(sr_oos) + 1.0 - rank)))
    if not logits:
        return float("nan")
    return float(np.mean(np.asarray(logits) <= 0.0))


def sidak_reality_check(returns: pd.Series, n_trials: int) -> float:
    """Sidak-adjusted p-value for the best of n_trials strategies.

    This is a conservative, fast stand-in for White's reality check. The
    single-strategy one-sided p-value is adjusted for the number of candidates
    that were searched.
    """
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 60 or values.std(ddof=1) == 0 or n_trials < 1:
        return float("nan")
    t_stat = values.mean() / values.std(ddof=1) * np.sqrt(values.size)
    p_single = 1.0 - norm.cdf(t_stat)
    return float(1.0 - (1.0 - p_single) ** n_trials)


def split_half_z(returns: pd.Series) -> float:
    """Positive values mean the first half was better than the second half."""
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 60 or values.std(ddof=1) == 0:
        return float("nan")
    mid = values.size // 2
    first, second = values[:mid], values[mid:]
    if first.std(ddof=1) == 0 or second.std(ddof=1) == 0:
        return float("nan")
    sr_first = first.mean() / first.std(ddof=1)
    sr_second = second.mean() / second.std(ddof=1)
    standard_error = np.sqrt(1.0 / first.size + 1.0 / second.size)
    return float((sr_first - sr_second) / standard_error)


def circular_block_indices(
    n: int, n_boot: int, block: int, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def audit_p_value(
    reported: pd.Series,
    honest: pd.Series,
    n_boot: int = 500,
    block: int = 20,
    seed: int = 0,
) -> float:
    """Bootstrap p-value for the audit hypothesis reported <= honest.

    The test compares the Sharpe ratio of the reported strategy with the
    Sharpe ratio of the same replicate's fully re-executed honest pipeline.
    It is exact only when the pipeline is deterministic; the bootstrap makes
    the comparison robust to serial dependence.
    """
    joined = pd.concat([reported.rename("reported"), honest.rename("honest")], axis=1).dropna()
    if len(joined) < 60:
        return 1.0
    rep = joined["reported"].to_numpy(dtype=float)
    hon = joined["honest"].to_numpy(dtype=float)
    if rep.std(ddof=1) == 0 or hon.std(ddof=1) == 0:
        return 1.0
    observed = (rep.mean() / rep.std(ddof=1)) - (hon.mean() / hon.std(ddof=1))
    if observed <= 0:
        return 1.0
    idx = circular_block_indices(len(joined), n_boot, block, seed)
    rep_b = rep[idx]
    hon_b = hon[idx]
    rep_sr = rep_b.mean(axis=1) / rep_b.std(axis=1, ddof=1)
    hon_sr = hon_b.mean(axis=1) / hon_b.std(axis=1, ddof=1)
    diffs = rep_sr - hon_sr
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return 1.0
    return float((1.0 + np.sum(diffs <= 0.0)) / (diffs.size + 1.0))


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return (float("nan"), float("nan"))
    p = successes / trials
    denominator = 1.0 + z**2 / trials
    center = (p + z**2 / (2 * trials)) / denominator
    half = z * np.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator
    return (float(max(0.0, center - half)), float(min(1.0, center + half)))

"""Cross-sectional strategy construction and daily return generation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import SIGNAL_NAMES, signal_frames, zscore_cs

TOP_K_CHOICES = (1, 2, 3, 4)
WEIGHTING_CHOICES = ("equal", "invvol")


@dataclass(frozen=True)
class Candidate:
    signal: str
    top_k: int
    weighting: str

    @property
    def id(self) -> str:
        return f"{self.signal}|k{self.top_k}|{self.weighting}"


def candidate_pool() -> list[Candidate]:
    return [
        Candidate(signal, top_k, weighting)
        for signal in SIGNAL_NAMES
        for top_k in TOP_K_CHOICES
        for weighting in WEIGHTING_CHOICES
    ]


def rebalance_dates(index: pd.DatetimeIndex, frequency: str = "W-FRI") -> pd.DatetimeIndex:
    dates = pd.Series(index=index, data=index).resample(frequency).last().dropna()
    return pd.DatetimeIndex(dates.to_numpy())


def _target_weights(signal_row: np.ndarray, vol_row: np.ndarray, top_k: int, weighting: str):
    valid = np.where(np.isfinite(signal_row))[0]
    if valid.size < top_k:
        return None
    order = valid[np.argsort(-signal_row[valid], kind="stable")[:top_k]]
    if weighting == "equal":
        weights = np.full(top_k, 1.0 / top_k)
    else:
        vols = vol_row[order]
        fallback = np.nanmedian(vols) if np.isfinite(vols).any() else 1.0
        vols = np.where(np.isfinite(vols) & (vols > 0), vols, fallback)
        inverse = 1.0 / vols
        weights = inverse / inverse.sum()
    return order, weights


def build_weight_matrix(
    prices: pd.DataFrame,
    signal: pd.DataFrame,
    volatility: pd.DataFrame,
    candidate: Candidate,
    cost_bps: float,
    lag: int,
    universe: pd.DataFrame | None,
    rebalance: pd.DatetimeIndex,
) -> tuple[np.ndarray, np.ndarray]:
    """Return daily target weights and the cost charged when they change.

    `lag=1` is honest: a signal formed at close t earns the return from t+1.
    `lag=0` is the same-bar leak: the return on t is earned with a weight
    formed from t's close.
    """
    n_days, n_assets = prices.shape
    signals = signal.to_numpy(dtype=float)
    vols = volatility.to_numpy(dtype=float)
    mask = universe.to_numpy(dtype=bool) if universe is not None else None
    positions = prices.index.get_indexer(rebalance)
    positions = positions[positions >= 0]

    weights = np.zeros((n_days, n_assets), dtype=float)
    costs = np.zeros(n_days, dtype=float)
    previous = np.zeros(n_assets, dtype=float)

    for j, ti in enumerate(positions):
        row = signals[ti].copy()
        if mask is not None:
            row[~mask[ti]] = np.nan
        target = _target_weights(row, vols[ti], candidate.top_k, candidate.weighting)
        if target is None:
            continue
        order, chosen = target
        start = ti + lag
        if start >= n_days:
            continue
        end = positions[j + 1] + lag if j + 1 < len(positions) else n_days
        end = min(max(end, start), n_days)
        if end <= start:
            continue
        weights[start:end, :] = 0.0
        weights[start:end, order] = chosen
        current = np.zeros(n_assets, dtype=float)
        current[order] = chosen
        costs[start] += np.abs(current - previous).sum() * cost_bps / 10_000.0
        previous = current
    return weights, costs


def _returns_from_weights(
    weights: np.ndarray, returns: np.ndarray, costs: np.ndarray, index: pd.DatetimeIndex
) -> pd.Series:
    return pd.Series((weights * returns).sum(axis=1) - costs, index=index, name="return")


def returns_matrix(
    prices: pd.DataFrame,
    signals: dict[str, pd.DataFrame],
    volatility: pd.DataFrame,
    candidates: list[Candidate],
    cost_bps: float,
    lag: int,
    universe: pd.DataFrame | None,
    rebalance: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build a T x N matrix of candidate daily strategy returns.

    Candidates that share the same signal frame, top_k, weighting, lag, and
    universe are identical; the cache makes the full-sample leak cheap.
    """
    returns = prices.pct_change(fill_method=None).fillna(0.0).to_numpy(dtype=float)
    cache: dict[tuple, pd.Series] = {}
    columns = {}
    for candidate in candidates:
        frame = signals[candidate.signal]
        key = (id(frame), candidate.top_k, candidate.weighting, lag, id(universe))
        if key not in cache:
            weights, costs = build_weight_matrix(
                prices,
                frame,
                volatility,
                candidate,
                cost_bps,
                lag,
                universe,
                rebalance,
            )
            cache[key] = _returns_from_weights(weights, returns, costs, prices.index)
        columns[candidate.id] = cache[key]
    return pd.DataFrame(columns)


def honest_signals(features: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return signal_frames(features)


def target_feature_signals(
    features: dict[str, pd.DataFrame], lam: float
) -> dict[str, pd.DataFrame]:
    leak = zscore_cs(features["forward_5d"])
    base = signal_frames(features)
    return {name: zscore_cs(frame) + lam * leak for name, frame in base.items()}


def full_sample_signals(features: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    frame = features["full_sample_mean_return"]
    return {name: frame for name in SIGNAL_NAMES}


def survivorship_universe(features: dict[str, pd.DataFrame]) -> pd.DataFrame:
    forward = features["forward_252d"]
    return (forward > 0.0) | forward.isna()

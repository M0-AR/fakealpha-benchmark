"""Causal feature construction for the honest protocol.

Every feature at date t is computed only from adjusted closes up to and
including t. The strategy then applies the resulting weights to t+1, so the
honest protocol never earns a return that was visible when the signal was
formed. Contamination modules deliberately break this rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MOMENTUM_WINDOWS = (5, 10, 20, 40, 60, 120, 250)


def zscore_cs(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score within each date."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0.0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0).replace([np.inf, -np.inf], np.nan)


def _rsi(prices: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    delta = prices.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    alpha = 1.0 / window
    avg_gain = gains.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
    avg_loss = losses.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def compute_features(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ret = prices.pct_change(fill_method=None)
    features: dict[str, pd.DataFrame] = {"ret1": ret}
    for window in MOMENTUM_WINDOWS:
        features[f"mom{window}"] = prices.pct_change(window, fill_method=None)

    vol20 = ret.rolling(20).std() * np.sqrt(TRADING_DAYS)
    vol60 = ret.rolling(60).std() * np.sqrt(TRADING_DAYS)
    features["vol20"] = vol20
    features["vol60"] = vol60
    features["rsi14"] = _rsi(prices, 14)
    features["volz20"] = (
        vol20 - vol20.rolling(TRADING_DAYS).mean()
    ) / vol20.rolling(TRADING_DAYS).std().replace(0.0, np.nan)
    features["trend20"] = prices / prices.rolling(20).mean() - 1.0
    features["dd60"] = prices / prices.rolling(60).max() - 1.0
    features["cs_mom20"] = features["mom20"].rank(axis=1, pct=True)
    features["cs_vol20"] = (-vol20).rank(axis=1, pct=True)
    features["combo"] = (
        zscore_cs(features["mom20"])
        + zscore_cs(features["mom60"])
        + zscore_cs(features["trend20"])
    )

    # Full-sample statistics are stored for the leakage modules, never for the
    # honest signal path.
    full_mean = ret.mean(axis=0, skipna=True)
    features["full_sample_mean_return"] = pd.DataFrame(
        np.tile(full_mean.to_numpy(), (len(prices), 1)),
        index=prices.index,
        columns=prices.columns,
    )
    features["forward_1d"] = prices.shift(-1) / prices - 1.0
    features["forward_5d"] = prices.shift(-5) / prices - 1.0
    features["forward_252d"] = prices.shift(-252) / prices - 1.0
    return features


SIGNAL_NAMES = (
    "mom5",
    "mom10",
    "mom20",
    "mom40",
    "mom60",
    "mom120",
    "mom250",
    "lowvol20",
    "lowvol60",
    "rsi14",
    "volz20",
    "trend20",
    "dd60",
    "cs_mom20",
    "cs_vol20",
    "combo",
)


def signal_frame(features: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    if name.startswith("mom"):
        return features[name]
    if name == "lowvol20":
        return -features["vol20"]
    if name == "lowvol60":
        return -features["vol60"]
    if name == "rsi14":
        return -features["rsi14"]
    if name == "volz20":
        return -features["volz20"]
    if name in {"trend20", "dd60", "cs_mom20", "cs_vol20", "combo"}:
        return features[name]
    raise KeyError(f"unknown signal {name}")


def signal_frames(features: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: signal_frame(features, name) for name in SIGNAL_NAMES}

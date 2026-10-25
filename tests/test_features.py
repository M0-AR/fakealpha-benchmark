import numpy as np
import pandas as pd

from fakealpha.features import compute_features, signal_frames, zscore_cs


def _prices(n=400, assets=4, seed=0):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0003, 0.01, size=(n, assets))
    prices = 100 * np.exp(np.cumsum(ret, axis=0))
    index = pd.bdate_range("2015-01-01", periods=n)
    return pd.DataFrame(prices, index=index, columns=[f"A{i}" for i in range(assets)])


def test_features_are_causal():
    prices = _prices()
    altered = prices.copy()
    altered.iloc[250:] *= 2.0
    original = compute_features(prices)
    changed = compute_features(altered)
    for name in ("mom5", "mom20", "vol20", "rsi14", "trend20", "dd60"):
        pd.testing.assert_frame_equal(
            original[name].iloc[:250], changed[name].iloc[:250]
        )


def test_full_sample_feature_is_lookahead_by_construction():
    prices = _prices()
    altered = prices.copy()
    altered.iloc[250:] *= 2.0
    original = compute_features(prices)["full_sample_mean_return"]
    changed = compute_features(altered)["full_sample_mean_return"]
    assert not original.equals(changed)


def test_zscore_cs_is_per_date():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [3.0, 4.0], "C": [5.0, 6.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    scored = zscore_cs(frame)
    assert np.allclose(scored.mean(axis=1), 0.0)
    assert np.allclose(scored.std(axis=1), 1.0)


def test_signal_frames_cover_pool():
    frames = signal_frames(compute_features(_prices()))
    assert "mom20" in frames
    assert "lowvol20" in frames
    assert "combo" in frames

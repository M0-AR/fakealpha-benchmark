import numpy as np
import pandas as pd

from fakealpha.stats import (
    audit_p_value,
    deflated_sharpe,
    pbo,
    sharpe,
    sidak_reality_check,
    split_half_z,
)


def _returns(mean=0.0005, std=0.01, n=1500, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, std, n), index=pd.bdate_range("2010-01-01", periods=n))


def test_sharpe_sign_and_scale():
    positive = _returns(mean=0.001)
    negative = _returns(mean=-0.001)
    assert sharpe(positive) > 0
    assert sharpe(negative) < 0
    assert np.isnan(sharpe(pd.Series([0.0, 0.0, 0.0])))


def test_dsr_increases_with_information_ratio():
    rng = np.random.default_rng(1)
    matrix = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(1500, 20)),
        index=pd.bdate_range("2010-01-01", periods=1500),
    )
    weak = _returns(mean=0.0002, seed=2)
    strong = _returns(mean=0.0015, seed=3)
    assert deflated_sharpe(strong, matrix)["dsr"] > deflated_sharpe(weak, matrix)["dsr"]


def test_pbo_low_for_dominant_candidate():
    rng = np.random.default_rng(4)
    base = rng.normal(0.0, 0.01, size=(1000, 5))
    base[:, 0] += 0.002
    matrix = pd.DataFrame(base)
    assert pbo(matrix) < 0.2


def test_reality_check_reacts_to_signal():
    strong = _returns(mean=0.002)
    weak = _returns(mean=0.0)
    assert sidak_reality_check(strong, 20) < sidak_reality_check(weak, 20)


def test_split_half_detects_degradation():
    strong_then_weak = pd.concat([_returns(0.002, seed=5), _returns(-0.001, seed=6)])
    assert split_half_z(strong_then_weak) > 0


def test_audit_is_exact_for_identical_series():
    series = _returns(mean=0.0005, seed=7)
    assert audit_p_value(series, series) == 1.0


def test_audit_detects_inflated_series():
    honest = _returns(mean=0.0002, seed=8)
    inflated = honest + 0.001
    assert audit_p_value(inflated, honest, n_boot=200) < 0.05

import numpy as np
import pandas as pd

from fakealpha.strategies import (
    Candidate,
    build_weight_matrix,
    candidate_pool,
    rebalance_dates,
)


def _panel(n=30, assets=4):
    index = pd.bdate_range("2020-01-01", periods=n)
    prices = pd.DataFrame(
        100.0 + np.arange(n)[:, None] + np.arange(assets)[None, :],
        index=index,
        columns=[f"A{i}" for i in range(assets)],
    )
    signal = pd.DataFrame(0.0, index=index, columns=prices.columns)
    signal.iloc[10, 2] = 10.0
    vol = pd.DataFrame(1.0, index=index, columns=prices.columns)
    return prices, signal, vol


def test_candidate_pool_is_unique():
    pool = candidate_pool()
    assert len(pool) == len({c.id for c in pool})
    assert len(pool) >= 100


def test_honest_lag_does_not_trade_on_signal_day():
    prices, signal, vol = _panel()
    candidate = Candidate("mom20", 1, "equal")
    rebalance = pd.DatetimeIndex([prices.index[10]])
    weights, costs = build_weight_matrix(
        prices, signal, vol, candidate, 5.0, 1, None, rebalance
    )
    assert weights[10].sum() == 0.0
    assert weights[11].sum() == 1.0
    assert weights[11, 2] == 1.0
    assert costs[11] > 0.0


def test_same_bar_lag_trades_on_signal_day():
    prices, signal, vol = _panel()
    candidate = Candidate("mom20", 1, "equal")
    rebalance = pd.DatetimeIndex([prices.index[10]])
    weights, _ = build_weight_matrix(
        prices, signal, vol, candidate, 5.0, 0, None, rebalance
    )
    assert weights[10, 2] == 1.0


def test_rebalance_dates_are_week_ends():
    prices, _, _ = _panel(60)
    dates = rebalance_dates(prices.index)
    assert len(dates) > 5
    assert all(date in prices.index for date in dates)

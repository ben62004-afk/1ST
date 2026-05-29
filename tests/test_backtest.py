import numpy as np
import pandas as pd
import pytest

from qld_ewma.backtest import run_backtest, buy_and_hold
from qld_ewma.signals import generate_signal


def _make_prices(n=300, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    ndx = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    qqq = ndx.copy()
    qld = 100 * np.cumprod(1 + 2 * np.diff(np.log(np.r_[ndx[0], ndx])))
    shy = 80 * np.cumprod(1 + rng.normal(0.0001, 0.0008, n))
    return pd.DataFrame({"NDX": ndx, "QQQ": qqq, "QLD": qld, "SHY": shy}, index=idx)


def test_no_lookahead_position_is_lagged_target():
    p = _make_prices()
    res = run_backtest(p, span=20)
    target = generate_signal(p["NDX"], span=20)
    # Executed position must equal the target shifted by one day.
    expected = target.shift(1).fillna(0.0)
    pd.testing.assert_series_equal(
        res.position, expected, check_names=False
    )


def test_no_lookahead_future_does_not_change_past_positions():
    # Truncating the series must not change earlier executed positions.
    p = _make_prices(n=300)
    full = run_backtest(p, span=20)
    trunc = run_backtest(p.iloc[:200], span=20)
    common = trunc.position.index
    pd.testing.assert_series_equal(
        full.position.loc[common], trunc.position.loc[common], check_names=False
    )


def test_return_chaining_reconstructs_equity():
    p = _make_prices()
    res = run_backtest(p, span=20)
    rebuilt = (1.0 + res.returns).cumprod()
    np.testing.assert_allclose(res.equity.to_numpy(), rebuilt.to_numpy(), rtol=1e-12)


def test_costs_charged_only_on_switch_days():
    p = _make_prices()
    free = run_backtest(p, span=20, fee=0.0, slippage=0.0)
    costly = run_backtest(p, span=20, fee=0.01, slippage=0.0)
    diff = (free.returns - costly.returns)
    switch_days = free.position.diff().abs() > 0
    # Cost difference appears exactly on switch days.
    assert (diff[switch_days] > 0).all()
    assert np.allclose(diff[~switch_days].to_numpy(), 0.0, atol=1e-15)
    # Each switch costs 2 * cost_per_side.
    np.testing.assert_allclose(diff[switch_days].to_numpy(), 2 * 0.01, rtol=1e-9)


def test_costs_reduce_total_return():
    p = _make_prices()
    free = run_backtest(p, span=20, fee=0.0, slippage=0.0)
    costly = run_backtest(p, span=20)
    if costly.switches > 0:
        assert costly.equity.iloc[-1] < free.equity.iloc[-1]


def test_all_risk_on_matches_qld_buy_hold_when_costless():
    # Force a permanently rising signal so the strategy is always in QLD.
    p = _make_prices()
    p["NDX"] = np.linspace(100, 400, len(p))  # monotone up
    p["QQQ"] = p["NDX"]
    res = run_backtest(p, span=20, fee=0.0, slippage=0.0)
    # After warmup the strategy holds QLD; compare returns where position==1.
    bh = buy_and_hold(p, "QLD")
    held = res.position == 1
    # On held days strategy daily return equals QLD daily return.
    qld_ret = p["QLD"].pct_change()
    np.testing.assert_allclose(
        res.returns[held].to_numpy(), qld_ret[held].to_numpy(), rtol=1e-9
    )


def test_exposure_and_switches_consistent():
    p = _make_prices()
    res = run_backtest(p, span=20)
    assert 0.0 <= res.exposure <= 1.0
    assert res.switches == int((res.position.diff().abs() > 0).sum())


def test_deterministic_repeat():
    p = _make_prices()
    a = run_backtest(p, span=20)
    b = run_backtest(p, span=20)
    pd.testing.assert_series_equal(a.equity, b.equity)

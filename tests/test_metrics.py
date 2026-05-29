import numpy as np
import pandas as pd
import pytest

from qld_ewma.metrics import (
    cagr,
    max_drawdown,
    calmar,
    sharpe,
    sortino,
    annual_volatility,
    performance_metrics,
    drawdown_series,
)


def _equity_from_returns(returns, start="2010-01-01"):
    idx = pd.bdate_range(start, periods=len(returns) + 1)
    eq = pd.Series(np.r_[1.0, np.cumprod(1 + np.asarray(returns))], index=idx)
    return eq


def test_cagr_known_doubling_over_one_year():
    # 252 trading days, exactly ~1 year, doubling.
    idx = pd.bdate_range("2010-01-04", periods=2)
    idx = pd.DatetimeIndex([pd.Timestamp("2010-01-01"), pd.Timestamp("2011-01-01")])
    eq = pd.Series([1.0, 2.0], index=idx)
    assert cagr(eq) == pytest.approx(1.0, rel=1e-3)  # 100% per year


def test_max_drawdown_simple():
    eq = pd.Series(
        [1.0, 1.2, 0.6, 0.9, 1.5],
        index=pd.bdate_range("2010-01-01", periods=5),
    )
    # Peak 1.2 -> trough 0.6 => -50%.
    assert max_drawdown(eq) == pytest.approx(-0.5)


def test_drawdown_series_nonpositive():
    eq = pd.Series(
        [1.0, 1.1, 1.05, 1.2, 1.0],
        index=pd.bdate_range("2010-01-01", periods=5),
    )
    dd = drawdown_series(eq)
    assert (dd <= 1e-12).all()
    assert dd.iloc[-1] == pytest.approx(1.0 / 1.2 - 1.0)


def test_calmar_is_cagr_over_mdd():
    eq = _equity_from_returns(np.random.default_rng(0).normal(0.0005, 0.01, 600))
    assert calmar(eq) == pytest.approx(cagr(eq) / abs(max_drawdown(eq)))


def test_sharpe_zero_for_constant_returns():
    r = pd.Series([0.001] * 100, index=pd.bdate_range("2010-01-01", periods=100))
    assert np.isnan(sharpe(r))  # zero variance -> undefined


def test_sharpe_sign_matches_mean():
    rng = np.random.default_rng(3)
    pos = pd.Series(rng.normal(0.001, 0.005, 500))
    neg = pd.Series(rng.normal(-0.001, 0.005, 500))
    assert sharpe(pos) > 0
    assert sharpe(neg) < 0


def test_sortino_ge_zero_for_positive_drift():
    rng = np.random.default_rng(4)
    r = pd.Series(rng.normal(0.001, 0.005, 1000))
    assert sortino(r) > 0


def test_annual_vol_scaling():
    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0, 0.01, 100000))
    # daily std ~0.01 -> annualised ~0.01*sqrt(252).
    assert annual_volatility(r) == pytest.approx(0.01 * np.sqrt(252), rel=0.05)


def test_performance_metrics_keys():
    eq = _equity_from_returns(np.random.default_rng(1).normal(0.0004, 0.01, 800))
    m = performance_metrics(eq)
    for k in ["CAGR", "MDD", "Calmar", "Sharpe", "Sortino", "AnnVol", "TotalReturn"]:
        assert k in m

import numpy as np
import pandas as pd
import pytest

from qld_ewma.signals import ewma, sma, generate_signal


def _series(vals):
    idx = pd.bdate_range("2020-01-01", periods=len(vals))
    return pd.Series(vals, index=idx, dtype=float)


def test_ewma_alpha_matches_specification():
    # alpha = 2/(span+1) -> for span=200 that is 2/201.
    s = _series(np.arange(1, 11))
    got = ewma(s, span=200)
    alpha = 2.0 / 201.0
    # Manual non-adjusted recursion.
    exp = [s.iloc[0]]
    for x in s.iloc[1:]:
        exp.append(alpha * x + (1 - alpha) * exp[-1])
    np.testing.assert_allclose(got.to_numpy(), np.array(exp), rtol=1e-12)


def test_ewma_matches_pandas_adjust_false():
    s = _series([10, 11, 9, 12, 15, 14, 13, 16, 18, 17])
    got = ewma(s, span=5)
    exp = s.ewm(span=5, adjust=False).mean()
    np.testing.assert_allclose(got.to_numpy(), exp.to_numpy(), rtol=1e-12)


def test_ewma_constant_series_is_constant():
    s = _series([5.0] * 50)
    got = ewma(s, span=200)
    np.testing.assert_allclose(got.to_numpy(), 5.0, rtol=1e-12)


def test_signal_boundary_close_equal_trend_is_risk_off():
    # If close == trend exactly, rule is close > trend -> False -> SHY (0).
    s = _series([5.0] * 30)  # EWMA equals the constant => close == trend
    pos = generate_signal(s, span=10, method="ewma")
    assert (pos == 0).all()


def test_signal_above_trend_is_risk_on():
    # Strictly rising series sits above its own EWMA -> risk-on after warmup.
    s = _series(np.linspace(100, 200, 60))
    pos = generate_signal(s, span=10, method="ewma")
    assert pos.iloc[-1] == 1.0
    assert pos.iloc[5:].mean() > 0.8


def test_sma_window_min_periods():
    s = _series(np.arange(1, 21))
    m = sma(s, window=5)
    assert m.iloc[:4].isna().all()
    assert m.iloc[4] == pytest.approx(np.mean([1, 2, 3, 4, 5]))


def test_buffer_band_reduces_switches():
    rng = np.random.default_rng(0)
    # Choppy series oscillating around a level to provoke whipsaw.
    base = 100 + np.cumsum(rng.normal(0, 1, 400))
    s = _series(base)
    no_buf = generate_signal(s, span=20, method="ewma", buffer=0.0)
    with_buf = generate_signal(s, span=20, method="ewma", buffer=0.02)
    switches_no = (no_buf.diff().abs() > 0).sum()
    switches_buf = (with_buf.diff().abs() > 0).sum()
    assert switches_buf <= switches_no


def test_invalid_span_and_method():
    s = _series([1, 2, 3])
    with pytest.raises(ValueError):
        ewma(s, span=0)
    with pytest.raises(ValueError):
        generate_signal(s, method="bogus")

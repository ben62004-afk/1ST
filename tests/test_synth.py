"""Tests for the synthetic-QLD core maths (written before the implementation)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qld_data import synth
from qld_data.config import EXPENSE_RATIO, LEVERAGE, TRADING_DAYS_PER_YEAR


def test_formula_matches_definition_scalar_rf():
    # r_QLD = L*r_NDX - (L-1)*rf/252 - ER/252
    r_ndx = pd.Series([0.01, -0.02, 0.0])
    rf = 0.02
    got = synth.synthetic_qld_returns(r_ndx, rf_annual=rf)
    expected = (
        LEVERAGE * r_ndx
        - (LEVERAGE - 1) * rf / TRADING_DAYS_PER_YEAR
        - EXPENSE_RATIO / TRADING_DAYS_PER_YEAR
    )
    pd.testing.assert_series_equal(got, expected)


def test_zero_ndx_return_gives_small_negative_drag():
    # Flat index: QLD loses financing + expense drag each day.
    got = synth.synthetic_qld_returns(pd.Series([0.0]), rf_annual=0.02)
    drag = (LEVERAGE - 1) * 0.02 / TRADING_DAYS_PER_YEAR + EXPENSE_RATIO / TRADING_DAYS_PER_YEAR
    assert got.iloc[0] == pytest.approx(-drag)


def test_leverage_amplifies_moves():
    r_ndx = pd.Series([0.05])
    got = synth.synthetic_qld_returns(r_ndx, rf_annual=0.0, expense_ratio=0.0)
    # With no financing/expense, a +5% index day -> exactly +10% leveraged day.
    assert got.iloc[0] == pytest.approx(0.10, rel=1e-9)


def test_rf_can_be_series_aligned_by_index():
    idx = pd.to_datetime(["2001-01-02", "2001-01-03"])
    r_ndx = pd.Series([0.01, 0.01], index=idx)
    rf = pd.Series([0.02, 0.10], index=idx)
    got = synth.synthetic_qld_returns(r_ndx, rf_annual=rf)
    # Higher rf on day 2 -> larger financing drag -> lower QLD return.
    assert got.iloc[1] < got.iloc[0]


def test_build_synthetic_close_anchors_to_real_value():
    # Synthetic close must equal the anchor value on the anchor date.
    idx = pd.bdate_range("2001-01-01", periods=10)
    ndx_close = pd.Series(np.linspace(1000, 1100, 10), index=idx)
    anchor_date = idx[5]
    anchor_value = 50.0
    sc = synth.build_synthetic_close(
        ndx_close, anchor_date=anchor_date, anchor_value=anchor_value, rf_annual=0.02
    )
    assert sc.loc[anchor_date] == pytest.approx(anchor_value)
    assert (sc > 0).all()


def test_build_synthetic_close_is_deterministic():
    idx = pd.bdate_range("2001-01-01", periods=20)
    ndx_close = pd.Series(np.linspace(1000, 900, 20), index=idx)
    a = synth.build_synthetic_close(ndx_close, idx[10], 40.0, rf_annual=0.02)
    b = synth.build_synthetic_close(ndx_close, idx[10], 40.0, rf_annual=0.02)
    pd.testing.assert_series_equal(a, b)

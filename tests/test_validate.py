"""Tests for the validation checks (the 5 acceptance criteria)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qld_data import validate


def test_continuity_zero_gaps_on_real_sessions():
    # Use real exchange sessions -> no missing trading days.
    sessions = validate.trading_sessions("2021-01-01", "2021-03-31")
    df = pd.DataFrame({"adj_close": 1.0}, index=sessions)
    report = validate.continuity_report(df)
    assert report["missing_count"] == 0


def test_continuity_detects_a_gap():
    sessions = validate.trading_sessions("2021-01-01", "2021-03-31")
    df = pd.DataFrame({"adj_close": 1.0}, index=sessions.delete(10))  # drop one session
    report = validate.continuity_report(df)
    assert report["missing_count"] == 1


def test_cross_source_within_tolerance_passes():
    idx = pd.bdate_range("2020-01-01", periods=5)
    a = pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=idx)
    b = pd.DataFrame({"close": [100.1, 100.9, 102.2, 103.0, 104.3]}, index=idx)
    res = validate.cross_source_check(a, b, tol=0.005)
    assert res["max_rel_diff"] < 0.005
    assert res["breaches"] == 0


def test_cross_source_breach_raises():
    idx = pd.bdate_range("2020-01-01", periods=3)
    a = pd.DataFrame({"close": [100, 100, 100]}, index=idx)
    b = pd.DataFrame({"close": [100, 100, 110]}, index=idx)  # 10% off
    with pytest.raises(ValueError):
        validate.cross_source_check(a, b, tol=0.005)


def test_seam_correlation_high_for_aligned_series():
    idx = pd.bdate_range("2006-06-21", periods=120)
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.02, len(idx))
    real = pd.Series(50 * np.cumprod(1 + base), index=idx)
    synth = pd.Series(48 * np.cumprod(1 + base + rng.normal(0, 0.0005, len(idx))), index=idx)
    corr = validate.seam_correlation(real, synth)
    assert corr > 0.98


def test_dataframe_hash_is_stable_and_order_independent():
    idx = pd.bdate_range("2020-01-01", periods=4, name="date")
    df = pd.DataFrame({"adj_close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    h1 = validate.dataframe_hash(df)
    h2 = validate.dataframe_hash(df.iloc[::-1])  # reversed order -> same hash
    assert h1 == h2
    assert len(h1) == 64


def test_drawdown_is_negative_for_decline():
    idx = pd.bdate_range("2008-01-01", periods=260)
    series = pd.Series(np.linspace(100, 40, 260), index=idx)  # -60% decline
    dd = validate.max_drawdown(series)
    assert dd < -0.5

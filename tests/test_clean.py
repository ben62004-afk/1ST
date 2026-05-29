"""Tests for the cleaning / splicing layer (synthetic + real QLD)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from qld_data import clean


def _write_stooq(raw_dir, key, df):
    """Helper: write a canonical frame back out as a Stooq-style CSV fixture."""
    out = df.reset_index()
    out.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    (raw_dir / f"{key}_stooq.csv").write_text(out.to_csv(index=False))


def _make_frames():
    # NDX spans 2006-01 .. 2006-09 ; QLD (real) starts at inception 2006-06-21.
    ndx_idx = pd.bdate_range("2006-01-02", "2006-09-29")
    rng = np.random.default_rng(0)
    ndx_close = pd.Series(2000 * np.cumprod(1 + rng.normal(0, 0.01, len(ndx_idx))), index=ndx_idx)
    ndx = pd.DataFrame(
        {
            "open": ndx_close,
            "high": ndx_close,
            "low": ndx_close,
            "close": ndx_close,
            "volume": 0,
        }
    )
    inception = pd.Timestamp("2006-06-21")
    qld_idx = ndx_idx[ndx_idx >= inception]
    qld_close = pd.Series(50 * np.cumprod(1 + 2 * rng.normal(0, 0.01, len(qld_idx))), index=qld_idx)
    qld = pd.DataFrame(
        {
            "open": qld_close,
            "high": qld_close,
            "low": qld_close,
            "close": qld_close,
            "volume": 0,
        }
    )
    return ndx, qld, inception


def test_clean_produces_synthetic_before_and_real_after(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ndx, qld, inception = _make_frames()
    _write_stooq(raw, "ndx", ndx)
    _write_stooq(raw, "qld", qld)

    combined = clean.build_qld_combined(raw_dir=raw, inception=inception)

    before = combined[combined.index < inception]
    after = combined[combined.index >= inception]
    assert before["is_synthetic"].all()
    assert not after["is_synthetic"].any()
    assert (before["source"] == "synthetic").all()
    assert (after["source"] == "stooq").all()
    # Real part preserves actual QLD prices.
    assert after.loc[inception, "adj_close"] == qld.loc[inception, "close"]


def test_seam_is_continuous(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ndx, qld, inception = _make_frames()
    _write_stooq(raw, "ndx", ndx)
    _write_stooq(raw, "qld", qld)

    combined = clean.build_qld_combined(raw_dir=raw, inception=inception)
    # Day-over-day return at the seam should be a sane daily move (no jump).
    rets = combined["adj_close"].pct_change().dropna()
    seam_ret = rets.loc[inception]
    assert abs(seam_ret) < 0.25  # not a discontinuous level jump


def test_clean_all_writes_three_parquets(tmp_path):
    raw = tmp_path / "raw"
    proc = tmp_path / "processed"
    raw.mkdir()
    ndx, qld, inception = _make_frames()
    _write_stooq(raw, "ndx", ndx)
    _write_stooq(raw, "qld", qld)

    out = clean.clean_all(raw_dir=raw, processed_dir=proc, inception=inception)
    for name in ("qld", "ndx", "rf"):
        assert (proc / f"{name}.parquet").exists()
        assert name in out
    rf = pd.read_parquet(proc / "rf.parquet")
    assert "rf_annual" in rf.columns


def test_clean_all_is_deterministic(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ndx, qld, inception = _make_frames()
    _write_stooq(raw, "ndx", ndx)
    _write_stooq(raw, "qld", qld)

    a = clean.build_qld_combined(raw_dir=raw, inception=inception)
    b = clean.build_qld_combined(raw_dir=raw, inception=inception)
    pd.testing.assert_frame_equal(a, b)

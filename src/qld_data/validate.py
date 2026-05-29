"""Validation layer: the 5 acceptance checks.

1. Trading-day continuity (no gaps vs the exchange calendar).
2. Cross-source agreement (Stooq vs Tiingo close, |Δ|/close < 0.5%).
3. Synthetic seam (real vs synthetic QLD return correlation > 0.98).
4. Reproducibility (stable content hash of processed data).
5. Drawdown sanity (known 2008 / 2020-03 / 2022 declines are present).

Checks that fail raise so bad data cannot silently enter the database.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from .config import (
    CROSS_SOURCE_TOL,
    EXCHANGE_CALENDAR,
    SEAM_CORR_MIN,
)


# ---------------------------------------------------------------------------
# 1. Trading-day continuity
# ---------------------------------------------------------------------------
def trading_sessions(start, end) -> pd.DatetimeIndex:
    """Return exchange trading sessions in [start, end] (tz-naive)."""
    import exchange_calendars as xcals

    # Widen the calendar bounds so we can cover the 2000 dot-com era.
    cal = xcals.get_calendar(EXCHANGE_CALENDAR, start=pd.Timestamp("1995-01-01"))
    sessions = cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    return pd.DatetimeIndex(sessions).tz_localize(None).normalize()


def continuity_report(df: pd.DataFrame) -> dict:
    """Report trading days expected by the calendar but missing from ``df``."""
    idx = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    expected = trading_sessions(idx.min(), idx.max())
    missing = expected.difference(idx)
    extra = idx.difference(expected)
    return {
        "expected": len(expected),
        "present": len(idx),
        "missing_count": int(len(missing)),
        "missing_dates": [d.strftime("%Y-%m-%d") for d in missing],
        "extra_count": int(len(extra)),
    }


# ---------------------------------------------------------------------------
# 2. Cross-source agreement
# ---------------------------------------------------------------------------
def cross_source_check(
    a: pd.DataFrame, b: pd.DataFrame, tol: float = CROSS_SOURCE_TOL
) -> dict:
    """Compare ``close`` on overlapping dates; raise if any |Δ|/close >= tol."""
    common = a.index.intersection(b.index)
    if len(common) == 0:
        raise ValueError("no overlapping dates between sources")
    rel = (a.loc[common, "close"] - b.loc[common, "close"]).abs() / b.loc[common, "close"]
    breaches = rel[rel >= tol]
    res = {
        "compared": int(len(common)),
        "max_rel_diff": float(rel.max()),
        "breaches": int(len(breaches)),
    }
    if len(breaches) > 0:
        worst = breaches.idxmax()
        raise ValueError(
            f"cross-source breach: {len(breaches)} day(s) exceed {tol:.3%}; "
            f"worst {worst.date()} = {breaches.max():.3%}"
        )
    return res


# ---------------------------------------------------------------------------
# 3. Synthetic seam correlation
# ---------------------------------------------------------------------------
def seam_correlation(real_close: pd.Series, synth_close: pd.Series) -> float:
    """Pearson correlation of daily returns over the overlapping window."""
    common = real_close.index.intersection(synth_close.index)
    r = real_close.loc[common].pct_change().dropna()
    s = synth_close.loc[common].pct_change().dropna()
    common2 = r.index.intersection(s.index)
    return float(r.loc[common2].corr(s.loc[common2]))


def assert_seam(real_close: pd.Series, synth_close: pd.Series, min_corr: float = SEAM_CORR_MIN) -> float:
    corr = seam_correlation(real_close, synth_close)
    if corr < min_corr:
        raise ValueError(f"seam correlation {corr:.4f} < required {min_corr}")
    return corr


# ---------------------------------------------------------------------------
# 4. Reproducibility hash
# ---------------------------------------------------------------------------
def dataframe_hash(df: pd.DataFrame) -> str:
    """Deterministic, order-independent SHA256 of a DataFrame's content."""
    d = df.sort_index()
    d = d.reindex(sorted(d.columns), axis=1)
    row_hashes = pd.util.hash_pandas_object(d, index=True)
    payload = "|".join(map(str, d.columns)) + "||" + ",".join(map(str, row_hashes.values))
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# 5. Drawdown sanity
# ---------------------------------------------------------------------------
def max_drawdown(close: pd.Series) -> float:
    """Maximum drawdown (most negative peak-to-trough) of a price series."""
    running_max = close.cummax()
    drawdown = close / running_max - 1.0
    return float(drawdown.min())


def drawdown_in_window(close: pd.Series, start, end) -> float:
    window = close.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    if window.empty:
        return float("nan")
    return max_drawdown(window)

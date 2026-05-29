"""Trend-following signal construction (EWMA / SMA + regime mapping).

The signal is computed on the *signal instrument* (NDX, or QQQ proxy) and never
on QLD itself, so that leverage decay does not distort the trend estimate.

Conventions
-----------
* EWMA uses ``adjust=False`` recursion with ``alpha = 2 / (span + 1)``, i.e. for
  ``span=200`` the smoothing factor is ``2/201`` exactly as specified.
* Regime rule (long-only switch):
      close >  trend  -> risk-on  (hold QLD)   -> position = 1
      close <= trend  -> risk-off (hold SHY)   -> position = 0
  The boundary (close == trend) maps to risk-off by specification.
* An optional symmetric buffer band (``buffer``) suppresses whipsaw: the state
  only flips to risk-on when close > trend*(1+buffer) and back to risk-off when
  close < trend*(1-buffer); inside the band the prior state is held.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ewma(series: pd.Series, span: int = 200) -> pd.Series:
    """Exponentially weighted moving average, ``alpha = 2/(span+1)``.

    Uses the standard non-adjusted recursion ``e_t = a*x_t + (1-a)*e_{t-1}``
    seeded with the first observation, matching ``pandas.Series.ewm(span=span,
    adjust=False).mean()``.
    """
    if span < 1:
        raise ValueError("span must be >= 1")
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int = 200) -> pd.Series:
    """Simple moving average over ``window`` observations."""
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.rolling(window=window, min_periods=window).mean()


def _apply_buffer(
    close: pd.Series, trend: pd.Series, buffer: float
) -> pd.Series:
    """Stateful hysteresis band. Returns 0/1 position with index of ``close``."""
    upper = trend * (1.0 + buffer)
    lower = trend * (1.0 - buffer)
    pos = np.zeros(len(close), dtype=float)
    state = 0  # start risk-off until the trend is established
    c = close.to_numpy()
    u = upper.to_numpy()
    l = lower.to_numpy()
    t = trend.to_numpy()
    for i in range(len(c)):
        if np.isnan(t[i]):
            state = 0
        elif c[i] > u[i]:
            state = 1
        elif c[i] < l[i]:
            state = 0
        # else: inside band -> hold previous state
        pos[i] = state
    return pd.Series(pos, index=close.index)


def generate_signal(
    close: pd.Series,
    span: int = 200,
    method: str = "ewma",
    buffer: float = 0.0,
) -> pd.Series:
    """Compute the desired *target* position (1=QLD, 0=SHY) at each close.

    This is the position **decided at the close of day t**; execution is handled
    downstream by shifting one day (T+1) to avoid look-ahead.

    Parameters
    ----------
    close : adjusted-close series of the signal instrument.
    span : EWMA span / SMA window.
    method : 'ewma' or 'sma'.
    buffer : symmetric buffer band as a fraction (e.g. 0.01 for +/-1%).
    """
    if method == "ewma":
        trend = ewma(close, span=span)
    elif method == "sma":
        trend = sma(close, window=span)
    else:
        raise ValueError(f"unknown method: {method!r}")

    if buffer and buffer > 0:
        return _apply_buffer(close, trend, buffer)

    # Plain rule: 1 where close > trend, else 0. NaN trend -> 0 (no signal yet).
    pos = (close > trend).astype(float)
    pos[trend.isna()] = 0.0
    return pos

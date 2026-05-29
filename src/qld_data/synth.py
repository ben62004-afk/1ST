"""Synthetic-QLD core maths.

This is the only module containing the financial leverage model, so it is kept
as pure functions (Series in -> Series out, no IO) to be trivially testable.

Formula (daily):
    r_QLD = L * r_NDX - (L - 1) * r_f / 252 - ER / 252
"""

from __future__ import annotations

import pandas as pd

from .config import EXPENSE_RATIO, LEVERAGE, RF_CONST_ANNUAL, TRADING_DAYS_PER_YEAR


def synthetic_qld_returns(
    ndx_returns: pd.Series,
    rf_annual: float | pd.Series = RF_CONST_ANNUAL,
    leverage: float = LEVERAGE,
    expense_ratio: float = EXPENSE_RATIO,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Return daily synthetic-QLD returns from daily NDX returns.

    ``rf_annual`` may be a scalar (constant financing cost) or a Series aligned
    to ``ndx_returns.index`` (time-varying SOFR / Fed Funds).
    """
    financing_drag = (leverage - 1) * rf_annual / trading_days
    expense_drag = expense_ratio / trading_days
    return leverage * ndx_returns - financing_drag - expense_drag


def build_synthetic_close(
    ndx_close: pd.Series,
    anchor_date,
    anchor_value: float,
    rf_annual: float | pd.Series = RF_CONST_ANNUAL,
    leverage: float = LEVERAGE,
    expense_ratio: float = EXPENSE_RATIO,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Build a synthetic QLD close-price series from an NDX close series.

    The series is scaled so it exactly equals ``anchor_value`` on
    ``anchor_date`` (the real QLD price at inception), giving a continuous seam
    between synthetic (pre-inception) and real (post-inception) QLD.
    """
    anchor_ts = pd.Timestamp(anchor_date)
    if anchor_ts not in ndx_close.index:
        raise ValueError(f"anchor_date {anchor_ts.date()} not in NDX index")

    r_ndx = ndx_close.pct_change()
    r_qld = synthetic_qld_returns(
        r_ndx,
        rf_annual=rf_annual,
        leverage=leverage,
        expense_ratio=expense_ratio,
        trading_days=trading_days,
    )
    # Cumulative growth from an arbitrary base of 1.0 (first return is NaN -> 0).
    growth = (1.0 + r_qld.fillna(0.0)).cumprod()
    scale = anchor_value / growth.loc[anchor_ts]
    return growth * scale

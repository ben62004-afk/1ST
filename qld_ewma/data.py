"""Price-data loading for the QLD/SHY EWMA backtest.

Data resolution order (deterministic, cached):
    1. Local CSV cache under ``data/cache`` (fastest, fully reproducible).
    2. Live download via ``yfinance`` (total-return / auto-adjusted close),
       written to the cache so subsequent runs are deterministic.
    3. A *seeded synthetic* fallback used only when neither the cache nor the
       network is available (e.g. a locked-down CI sandbox).  Numbers produced
       from synthetic data are ILLUSTRATIVE ONLY and are flagged as such by
       the ``synthetic`` field on the returned :class:`PriceData`.

All series are *adjusted close* (dividends reinvested) so that bond-leg
distributions (SHY) and ETF distributions are captured as total return.

The signal instrument is the Nasdaq-100 index (``^NDX``); if unavailable we
fall back to QQQ adjusted close as a proxy.  We never compute the trend signal
from QLD itself (leverage decay would distort the trend).
"""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

import numpy as np
import pandas as pd

# QLD (ProShares Ultra QQQ) first traded 2006-06-21.
INCEPTION_QLD = "2006-06-21"

# Expense ratios / structural drags used by the synthetic generator and
# documented in the report.
_ER_QQQ = 0.0020   # 0.20% Invesco QQQ
_ER_QLD = 0.0095   # 0.95% ProShares Ultra QQQ
_ER_SHY = 0.0015   # 0.15% iShares 1-3yr Treasury

_CACHE_DIR_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache"
)

TRADING_DAYS = 252


@dataclasses.dataclass
class PriceData:
    """Container for the adjusted-close series used by the backtest."""

    prices: pd.DataFrame  # columns: NDX, QQQ, QLD, SHY ; DatetimeIndex
    source: str           # 'cache' | 'yfinance' | 'synthetic'
    synthetic: bool

    @property
    def signal(self) -> pd.Series:
        """The trend-signal instrument (NDX, else QQQ proxy)."""
        col = "NDX" if "NDX" in self.prices and self.prices["NDX"].notna().any() else "QQQ"
        return self.prices[col].dropna()


def _cache_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "prices.csv")


def _read_cache(cache_dir: str) -> Optional[pd.DataFrame]:
    path = _cache_path(cache_dir)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df


def _write_cache(df: pd.DataFrame, cache_dir: str) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(_cache_path(cache_dir))


def _download_yfinance(start: str, end: Optional[str]) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
    except Exception:
        return None

    frames = {}
    # ^NDX is the index; QQQ/QLD/SHY are the tradable ETFs (auto_adjust=True
    # gives dividend-reinvested total-return close).
    tickers = {"NDX": "^NDX", "QQQ": "QQQ", "QLD": "QLD", "SHY": "SHY"}
    for name, sym in tickers.items():
        try:
            raw = yf.download(
                sym, start=start, end=end, progress=False, auto_adjust=True
            )
            if raw is None or len(raw) == 0:
                continue
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):  # multiindex when single ticker
                close = close.iloc[:, 0]
            frames[name] = close
        except Exception:
            continue

    if "QLD" not in frames or "SHY" not in frames:
        return None
    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df.dropna(how="all")


def _synthesize(start: str, end: Optional[str], seed: int) -> pd.DataFrame:
    """Deterministic, regime-aware synthetic total-return series.

    NDX is a geometric random walk with a simple two-state (calm/stress)
    volatility process so that bull runs and drawdowns both occur.  QQQ is NDX
    net of its expense ratio.  QLD is built from the *actual* 2x daily-rebalanced
    leveraged-ETF mechanics (``2 * r_ndx`` net of fees) so that volatility decay
    emerges naturally rather than being assumed.  SHY is a low-volatility bond
    total-return series.
    """
    rng = np.random.default_rng(seed)
    end = end or pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)

    # --- NDX daily total return with volatility regimes -------------------
    # Calibrated so the full-period path resembles the real Nasdaq-100: a
    # secular bull (~13-16% CAGR) punctuated by a handful of bear markets.
    mu_annual = 0.16
    mu_daily = mu_annual / TRADING_DAYS  # ~0.000635
    vol_calm = 0.011      # ~17.5% annualised
    vol_stress = 0.032    # ~51% annualised (bear/crisis)
    # Persistent regime via a slow Markov chain: stress onset is rare
    # (~once every few years) and lasts a few months on average.
    p_stay_calm = 0.999     # mean calm run ~1000 trading days
    p_stay_stress = 0.978   # mean stress run ~45 trading days
    state = np.zeros(n, dtype=bool)  # False=calm, True=stress
    cur = False
    for i in range(n):
        if cur:
            cur = rng.random() < p_stay_stress
        else:
            cur = rng.random() > p_stay_calm
        state[i] = cur
    vol = np.where(state, vol_stress, vol_calm)
    # Stress regimes carry a negative drift (bear markets).
    drift = np.where(state, -0.0020, mu_daily)
    ndx_ret = drift + vol * rng.standard_normal(n)

    ndx = 2000.0 * np.cumprod(1.0 + ndx_ret)

    # --- QQQ: NDX net of expense ratio -----------------------------------
    qqq_ret = ndx_ret - _ER_QQQ / TRADING_DAYS
    qqq = 40.0 * np.cumprod(1.0 + qqq_ret)

    # --- QLD: 2x daily rebalanced, net of fees ---------------------------
    qld_ret = 2.0 * ndx_ret - _ER_QLD / TRADING_DAYS
    qld = 20.0 * np.cumprod(1.0 + qld_ret)

    # --- SHY: short-term treasury total return ---------------------------
    shy_mu = 0.02 / TRADING_DAYS
    shy_vol = 0.0008
    shy_ret = shy_mu + shy_vol * rng.standard_normal(n) - _ER_SHY / TRADING_DAYS
    shy = 80.0 * np.cumprod(1.0 + shy_ret)

    df = pd.DataFrame(
        {"NDX": ndx, "QQQ": qqq, "QLD": qld, "SHY": shy}, index=dates
    )
    df.index.name = "Date"
    return df


def load_prices(
    start: str = INCEPTION_QLD,
    end: Optional[str] = None,
    cache_dir: str = _CACHE_DIR_DEFAULT,
    seed: int = 42,
    allow_download: bool = True,
    use_cache: bool = True,
    force_synthetic: bool = False,
) -> PriceData:
    """Load adjusted-close prices for NDX, QQQ, QLD, SHY.

    Parameters mirror the data-resolution order documented in the module
    docstring.  The result is cached to CSV for deterministic re-runs.
    """
    if force_synthetic:
        df = _synthesize(start, end, seed)
        return PriceData(prices=df, source="synthetic", synthetic=True)

    if use_cache:
        cached = _read_cache(cache_dir)
        if cached is not None and len(cached) > 0:
            return PriceData(prices=cached, source="cache", synthetic=False)

    if allow_download:
        dl = _download_yfinance(start, end)
        if dl is not None and len(dl) > 0:
            _write_cache(dl, cache_dir)
            return PriceData(prices=dl, source="yfinance", synthetic=False)

    # Fallback: synthetic (flagged). Cache it so the run is reproducible, but
    # under a distinct filename so it never masquerades as real data.
    df = _synthesize(start, end, seed)
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(os.path.join(cache_dir, "prices_synthetic.csv"))
    return PriceData(prices=df, source="synthetic", synthetic=True)

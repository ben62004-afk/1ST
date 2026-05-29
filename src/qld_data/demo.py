"""DEMO data generator -- NOT REAL MARKET DATA.

This exists ONLY so the full pipeline (synthetic splice -> DuckDB -> validation)
can be exercised end-to-end in an environment without access to Stooq / Tiingo.
It produces deterministic NDX and QLD series on real exchange sessions, with
crisis windows (dot-com, GFC, COVID, 2022) injected so the drawdown sanity
checks have something to find.

To get the REAL database, run `python -m qld_data.pipeline fetch` where
stooq.com / api.tiingo.com are reachable, then `... build`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import LEVERAGE, QLD_INCEPTION, RAW_DIR
from .validate import trading_sessions

# (start, end, daily_drift) crisis overlays applied to NDX.
_CRISES = [
    ("2000-03-13", "2002-10-09", -0.0028),
    ("2008-01-02", "2009-03-09", -0.0035),
    ("2020-02-19", "2020-03-23", -0.030),
    ("2022-01-03", "2022-12-28", -0.0016),
]


def _ndx_returns(sessions: pd.DatetimeIndex, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.012, len(sessions))  # mild upward drift
    rets = pd.Series(r, index=sessions)
    for start, end, drift in _CRISES:
        mask = (rets.index >= pd.Timestamp(start)) & (rets.index <= pd.Timestamp(end))
        rets.loc[mask] += drift
    return rets


def _to_stooq_csv(close: pd.Series) -> str:
    df = pd.DataFrame(
        {
            "Date": close.index.strftime("%Y-%m-%d"),
            "Open": close.values,
            "High": close.values * 1.005,
            "Low": close.values * 0.995,
            "Close": close.values,
            "Volume": 1_000_000,
        }
    )
    return df.to_csv(index=False)


def generate_demo_raw(raw_dir: Path = RAW_DIR, seed: int = 42) -> dict[str, Path]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    sessions = trading_sessions("1999-01-04", "2024-12-31")
    r_ndx = _ndx_returns(sessions, seed)
    ndx_close = 1500.0 * (1.0 + r_ndx).cumprod()

    inception = pd.Timestamp(QLD_INCEPTION)
    qld_sessions = sessions[sessions >= inception]
    rng = np.random.default_rng(seed + 1)
    # Real QLD ~ leveraged NDX with small idiosyncratic tracking noise.
    r_qld = LEVERAGE * r_ndx.loc[qld_sessions] + rng.normal(0, 0.0006, len(qld_sessions))
    qld_close = 50.0 * (1.0 + r_qld).cumprod()

    paths = {
        "ndx": raw_dir / "ndx_stooq.csv",
        "qld": raw_dir / "qld_stooq.csv",
    }
    from .fetch import _write_meta, parse_stooq_csv

    for key, close in (("ndx", ndx_close), ("qld", qld_close)):
        text = _to_stooq_csv(close)
        paths[key].write_text(text)
        _write_meta(paths[key], "demo", "synthetic://demo-not-real-data", text,
                    len(parse_stooq_csv(text)))
    return paths

"""Cleaning layer: standardise raw series and splice synthetic + real QLD.

Pipeline (all recomputed from the immutable raw layer):
  1. Load raw Stooq CSVs for QLD and NDX -> canonical OHLCV frames.
  2. Build a financing-cost (r_f) series (constant for now; TODO real SOFR).
  3. Synthesise QLD before its 2006 inception from NDX returns, anchored to the
     real QLD price at inception so the seam is continuous.
  4. Concatenate synthetic (pre-inception) + real (post-inception).
  5. Write processed/ parquet files.

Design decision: splice on *returns* (anchored price), not raw price levels, so
the synthetic and real segments join without a water-level jump.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import synth
from .config import (
    PROCESSED_DIR,
    QLD_INCEPTION,
    RAW_DIR,
    RF_CONST_ANNUAL,
)
from .fetch import parse_stooq_csv

OUTPUT_COLS = [
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "is_synthetic",
]


def load_raw_stooq(key: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load and parse a raw Stooq CSV into the canonical OHLCV frame."""
    path = Path(raw_dir) / f"{key}_stooq.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing raw file: {path}")
    return parse_stooq_csv(path.read_text())


def build_rf_series(index: pd.DatetimeIndex, rf_annual: float = RF_CONST_ANNUAL) -> pd.DataFrame:
    """Annual financing-cost series. Constant for now.

    TODO: replace the constant with historical SOFR / Fed Funds rates.
    """
    return pd.DataFrame({"rf_annual": rf_annual}, index=index).rename_axis("date")


def build_qld_combined(
    raw_dir: Path = RAW_DIR,
    inception=QLD_INCEPTION,
    rf_annual: float = RF_CONST_ANNUAL,
) -> pd.DataFrame:
    """Return the spliced QLD series: synthetic before inception, real after."""
    inception = pd.Timestamp(inception)
    ndx = load_raw_stooq("ndx", raw_dir)
    qld_real = load_raw_stooq("qld", raw_dir)

    # Anchor on the first real QLD day at or after the configured inception.
    real_from = qld_real.index[qld_real.index >= inception]
    if len(real_from) == 0:
        raise ValueError("no real QLD data at/after inception")
    anchor_date = real_from[0]
    if anchor_date not in ndx.index:
        raise ValueError(f"anchor date {anchor_date.date()} missing from NDX series")
    anchor_value = qld_real.loc[anchor_date, "adj_close"]

    # --- Real segment (inception onward) ---
    real = qld_real[qld_real.index >= anchor_date].copy()
    real["source"] = "stooq"
    real["is_synthetic"] = False

    # --- Synthetic segment (before inception) ---
    rf = build_rf_series(ndx.index, rf_annual)["rf_annual"]
    synth_close = synth.build_synthetic_close(
        ndx["close"], anchor_date=anchor_date, anchor_value=anchor_value, rf_annual=rf
    )
    pre = ndx.index < anchor_date
    syn = pd.DataFrame(index=ndx.index[pre])
    syn.index.name = "date"
    syn["open"] = pd.NA
    syn["high"] = pd.NA
    syn["low"] = pd.NA
    syn["close"] = synth_close[pre]
    syn["adj_close"] = synth_close[pre]
    syn["volume"] = pd.NA
    syn["source"] = "synthetic"
    syn["is_synthetic"] = True

    combined = pd.concat([syn[OUTPUT_COLS], real[OUTPUT_COLS]]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.index.name = "date"
    return combined


def build_ndx(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    ndx = load_raw_stooq("ndx", raw_dir).copy()
    ndx["source"] = "stooq"
    ndx["is_synthetic"] = False
    return ndx[OUTPUT_COLS]


def clean_all(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    inception=QLD_INCEPTION,
    rf_annual: float = RF_CONST_ANNUAL,
) -> dict[str, Path]:
    """Build all processed parquet files from the raw layer."""
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    qld = build_qld_combined(raw_dir, inception=inception, rf_annual=rf_annual)
    ndx = build_ndx(raw_dir)
    rf = build_rf_series(ndx.index, rf_annual)

    paths = {
        "qld": processed_dir / "qld.parquet",
        "ndx": processed_dir / "ndx.parquet",
        "rf": processed_dir / "rf.parquet",
    }
    qld.to_parquet(paths["qld"])
    ndx.to_parquet(paths["ndx"])
    rf.to_parquet(paths["rf"])
    return paths

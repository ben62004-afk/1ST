"""Central configuration: every magic number lives here (single source of truth).

Design decision: keeping all parameters in one module means a zero-programming
user can tune leverage / fees / tolerances without reading the pipeline code.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Project root = two levels up from this file (src/qld_data/config.py -> root).
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DUCKDB_PATH = DATA_DIR / "backtest.duckdb"

# ---------------------------------------------------------------------------
# Synthetic-QLD model parameters
# ---------------------------------------------------------------------------
# r_QLD = L * r_NDX - (L - 1) * r_f / 252 - ER / 252
LEVERAGE = 2.0            # L: 2x NASDAQ-100
EXPENSE_RATIO = 0.0095    # ER: QLD annual expense ratio (0.95%)
TRADING_DAYS_PER_YEAR = 252
# r_f annual financing cost. TODO: replace constant with real SOFR / Fed Funds.
RF_CONST_ANNUAL = 0.02

# ---------------------------------------------------------------------------
# Series / symbols
# ---------------------------------------------------------------------------
# QLD launched 2006-06-21 (first day with a computable daily return).
# Before this date QLD is synthesised from NDX returns.
QLD_INCEPTION = "2006-06-21"

# Stooq symbols (US suffix for ETF; ^ndx for the index).
STOOQ_SYMBOLS = {"qld": "qld.us", "ndx": "^ndx"}
# Tiingo symbols (validation source). Tiingo has QLD; NDX index needs IEX/other,
# so NDX cross-check is best-effort (see fetch.py).
TIINGO_SYMBOLS = {"qld": "QLD", "ndx": "QQQ"}  # QQQ as NDX proxy for cross-check

# ---------------------------------------------------------------------------
# Validation tolerances
# ---------------------------------------------------------------------------
CROSS_SOURCE_TOL = 0.005       # |Δclose|/close must be < 0.5%
SEAM_CORR_MIN = 0.98           # synthetic vs real QLD return correlation
SEAM_WINDOW_DAYS = 120         # overlap window after inception used for the check
MAX_GAP_TRADING_DAYS = 0       # allowed missing trading days (must be 0)

# Exchange calendar used for trading-day continuity (XNYS = NYSE; QLD trades on
# NYSE Arca which follows the same sessions).
EXCHANGE_CALENDAR = "XNYS"

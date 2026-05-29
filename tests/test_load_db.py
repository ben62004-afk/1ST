"""Tests for loading processed parquet into DuckDB."""

from __future__ import annotations

import duckdb
import pandas as pd

from qld_data import load_db


def _make_processed(proc):
    proc.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2020-01-01", periods=5, name="date")
    for name in ("qld", "ndx"):
        pd.DataFrame(
            {
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": range(5),
                "adj_close": range(5),
                "volume": 0,
                "source": "stooq",
                "is_synthetic": False,
            },
            index=idx,
        ).to_parquet(proc / f"{name}.parquet")
    pd.DataFrame({"rf_annual": 0.02}, index=idx).to_parquet(proc / "rf.parquet")


def test_load_creates_tables(tmp_path):
    proc = tmp_path / "processed"
    _make_processed(proc)
    db = tmp_path / "backtest.duckdb"

    load_db.load_to_duckdb(processed_dir=proc, db_path=db)

    con = duckdb.connect(str(db))
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert {"qld", "ndx", "rf"} <= tables
    n = con.execute("SELECT COUNT(*) FROM qld").fetchone()[0]
    assert n == 5
    # date column is queryable and ordered
    first = con.execute("SELECT min(date), max(date) FROM qld").fetchone()
    assert str(first[0]) == "2020-01-01"
    con.close()


def test_load_is_idempotent(tmp_path):
    proc = tmp_path / "processed"
    _make_processed(proc)
    db = tmp_path / "backtest.duckdb"
    load_db.load_to_duckdb(processed_dir=proc, db_path=db)
    load_db.load_to_duckdb(processed_dir=proc, db_path=db)  # rerun must not duplicate
    con = duckdb.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM qld").fetchone()[0] == 5
    con.close()

"""End-to-end integration: build -> delete processed -> rebuild -> identical.

Covers the reproducibility acceptance criterion and that DuckDB is queryable.
Uses a small (2005-2009) deterministic dataset so it stays fast.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from qld_data import load_db, pipeline, validate
from qld_data.config import LEVERAGE


def _write_small_raw(raw_dir):
    raw_dir.mkdir(parents=True, exist_ok=True)
    sessions = validate.trading_sessions("2005-01-03", "2009-06-30")
    rng = np.random.default_rng(7)
    r = rng.normal(0.0004, 0.012, len(sessions))
    rets = pd.Series(r, index=sessions)
    # Inject a 2008 crash so the drawdown sanity check has something to find.
    crash = (rets.index >= "2008-01-01") & (rets.index <= "2009-03-09")
    rets.loc[crash] -= 0.0035
    ndx = 1500.0 * (1 + rets).cumprod()

    inception = pd.Timestamp("2006-06-21")
    qs = sessions[sessions >= inception]
    rq = LEVERAGE * rets.loc[qs] + rng.normal(0, 0.0006, len(qs))
    qld = 50.0 * (1 + rq).cumprod()

    for key, close in (("ndx", ndx), ("qld", qld)):
        df = pd.DataFrame(
            {
                "Date": close.index.strftime("%Y-%m-%d"),
                "Open": close.values,
                "High": close.values,
                "Low": close.values,
                "Close": close.values,
                "Volume": 1,
            }
        )
        (raw_dir / f"{key}_stooq.csv").write_text(df.to_csv(index=False))


def test_build_is_reproducible_after_deleting_processed(tmp_path):
    raw = tmp_path / "raw"
    proc = tmp_path / "processed"
    db = tmp_path / "backtest.duckdb"
    _write_small_raw(raw)

    pipeline.run_build(raw_dir=raw, processed_dir=proc, db_path=db)
    h1 = validate.dataframe_hash(pd.read_parquet(proc / "qld.parquet"))

    # Delete processed + db, rebuild only from raw.
    (proc / "qld.parquet").unlink()
    (proc / "ndx.parquet").unlink()
    (proc / "rf.parquet").unlink()
    db.unlink()

    pipeline.run_build(raw_dir=raw, processed_dir=proc, db_path=db)
    h2 = validate.dataframe_hash(pd.read_parquet(proc / "qld.parquet"))

    assert h1 == h2  # reproducible from raw


def test_duckdb_query_finds_2008_drawdown(tmp_path):
    raw = tmp_path / "raw"
    proc = tmp_path / "processed"
    db = tmp_path / "backtest.duckdb"
    _write_small_raw(raw)
    pipeline.run_build(raw_dir=raw, processed_dir=proc, db_path=db)

    con = duckdb.connect(str(db))
    # Peak-to-trough over 2008-2009 must be a deep (leveraged) drawdown.
    row = con.execute(
        """
        WITH s AS (
            SELECT date, adj_close,
                   max(adj_close) OVER (ORDER BY date) AS peak
            FROM qld WHERE date BETWEEN '2008-01-01' AND '2009-03-31'
        )
        SELECT min(adj_close/peak - 1) FROM s
        """
    ).fetchone()[0]
    con.close()
    assert row < -0.4

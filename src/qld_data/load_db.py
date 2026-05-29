"""Load layer: write processed parquet into DuckDB with a date index.

Design decision: DuckDB (single-file, embedded, reads parquet directly, SQL).
Tradeoff: not distributed, but this is a single-machine backtest store.

Tables are fully rebuilt from parquet on each run (CREATE OR REPLACE), so the
load step is idempotent and always reflects the current processed layer.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .config import DUCKDB_PATH, PROCESSED_DIR

TABLES = ("qld", "ndx", "rf")


def load_to_duckdb(
    processed_dir: Path = PROCESSED_DIR,
    db_path: Path = DUCKDB_PATH,
) -> Path:
    """(Re)build DuckDB tables from processed parquet files."""
    processed_dir = Path(processed_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    try:
        for name in TABLES:
            parquet = processed_dir / f"{name}.parquet"
            if not parquet.exists():
                raise FileNotFoundError(f"missing processed file: {parquet}")
            con.execute(
                f"CREATE OR REPLACE TABLE {name} AS "
                f"SELECT * REPLACE (CAST(date AS DATE) AS date) "
                f"FROM read_parquet('{parquet.as_posix()}') ORDER BY date"
            )
            # Date index for fast range queries.
            con.execute(f"CREATE INDEX IF NOT EXISTS idx_{name}_date ON {name}(date)")
    finally:
        con.close()
    return db_path

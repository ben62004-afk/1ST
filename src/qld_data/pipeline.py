"""Pipeline orchestration + CLI: fetch -> clean -> load -> validate -> report.

Usage (run from project root):
    python -m qld_data.pipeline fetch        # download raw (needs network)
    python -m qld_data.pipeline build        # clean + load + validate + report
    python -m qld_data.pipeline all          # fetch then build
    python -m qld_data.pipeline demo         # generate DEMO raw data (no network)

The ``fetch`` step requires outbound access to stooq.com / api.tiingo.com.
Set TIINGO_API_KEY in the environment to enable the cross-source check.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from . import clean, fetch, load_db, validate
from .config import (
    DATA_DIR,
    DUCKDB_PATH,
    PROCESSED_DIR,
    QLD_INCEPTION,
    RAW_DIR,
    SEAM_WINDOW_DAYS,
)

REPORT_PATH = DATA_DIR / "coverage_report.md"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def run_fetch(raw_dir: Path = RAW_DIR) -> None:
    fetch.fetch_stooq("ndx", raw_dir=raw_dir)
    fetch.fetch_stooq("qld", raw_dir=raw_dir)
    key = os.environ.get("TIINGO_API_KEY")
    if key:
        fetch.fetch_tiingo("qld", api_key=key, raw_dir=raw_dir)
    else:
        print("TIINGO_API_KEY not set -> skipping cross-source fetch.")


# ---------------------------------------------------------------------------
# Validate (over processed parquet + raw, returns a report dict)
# ---------------------------------------------------------------------------
def run_validation(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    inception=QLD_INCEPTION,
) -> dict:
    inception = pd.Timestamp(inception)
    qld = pd.read_parquet(processed_dir / "qld.parquet")
    ndx = pd.read_parquet(processed_dir / "ndx.parquet")
    report: dict = {"checks": {}}

    # 1. Continuity
    report["checks"]["continuity_qld"] = validate.continuity_report(qld)
    report["checks"]["continuity_ndx"] = validate.continuity_report(ndx)

    # 2. Cross-source (only if a Tiingo raw file exists)
    tiingo_path = raw_dir / "qld_tiingo.json"
    if tiingo_path.exists():
        qld_stooq = clean.load_raw_stooq("qld", raw_dir)
        qld_tiingo = fetch.parse_tiingo_json(tiingo_path.read_text())
        report["checks"]["cross_source_qld"] = validate.cross_source_check(
            qld_stooq, qld_tiingo
        )
    else:
        report["checks"]["cross_source_qld"] = "skipped (no Tiingo raw)"

    # 3. Synthetic seam correlation
    real = clean.load_raw_stooq("qld", raw_dir)
    ndx_raw = clean.load_raw_stooq("ndx", raw_dir)
    anchor = real.index[real.index >= inception][0]
    window_end = anchor + pd.Timedelta(days=SEAM_WINDOW_DAYS * 2)
    real_win = real.loc[anchor:window_end, "adj_close"]
    synth_full = clean.synth.build_synthetic_close(
        ndx_raw["close"], anchor_date=anchor, anchor_value=real.loc[anchor, "adj_close"]
    )
    # Extend synthetic into the overlap window using the same model on NDX.
    synth_win = synth_full.loc[anchor:window_end]
    corr = validate.seam_correlation(real_win, synth_win)
    report["checks"]["seam_correlation"] = {
        "corr": corr,
        "passes": corr > 0.98,
    }

    # 4. Reproducibility: rebuild from raw, serialize the same way, compare hash.
    h_before = validate.dataframe_hash(qld)
    rebuilt = clean.build_qld_combined(raw_dir=raw_dir, inception=inception)
    tmp = processed_dir / "_qld_repro_check.parquet"
    rebuilt.to_parquet(tmp)
    h_after = validate.dataframe_hash(pd.read_parquet(tmp))
    tmp.unlink()
    report["checks"]["reproducibility"] = {
        "hash": h_before,
        "rebuilt_hash": h_after,
        "stable": h_before == h_after,
    }

    # 5. Drawdown sanity for known crisis windows.
    close = qld["adj_close"]
    windows = {
        "dotcom_2000_2002": ("2000-03-01", "2002-12-31"),
        "gfc_2008": ("2008-01-01", "2009-03-31"),
        "covid_2020_03": ("2020-02-01", "2020-04-30"),
        "bear_2022": ("2022-01-01", "2022-12-31"),
    }
    dd = {
        name: validate.drawdown_in_window(close, s, e) for name, (s, e) in windows.items()
    }
    report["checks"]["drawdowns"] = dd

    return report


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(report: dict, qld: pd.DataFrame, path: Path = REPORT_PATH) -> Path:
    c = report["checks"]
    syn = int(qld["is_synthetic"].sum())
    real = int((~qld["is_synthetic"]).sum())
    lines = [
        "# QLD Backtest Data — Coverage Report",
        "",
        f"- Date range: **{qld.index.min().date()} -> {qld.index.max().date()}**",
        f"- Total rows: **{len(qld)}** (synthetic: {syn}, real: {real})",
        "",
        "## Validation",
        f"- Continuity (QLD) missing trading days: **{c['continuity_qld']['missing_count']}**",
        f"- Continuity (NDX) missing trading days: **{c['continuity_ndx']['missing_count']}**",
        f"- Cross-source (Stooq vs Tiingo): **{c['cross_source_qld']}**",
        f"- Synthetic seam correlation: **{c['seam_correlation']['corr']:.4f}** "
        f"(pass>0.98: {c['seam_correlation']['passes']})",
        f"- Reproducibility hash stable: **{c['reproducibility']['stable']}** "
        f"(`{c['reproducibility']['hash'][:16]}...`)",
        "",
        "## Known drawdowns (max peak-to-trough in window)",
    ]
    for name, val in c["drawdowns"].items():
        pretty = "n/a" if pd.isna(val) else f"{val:.1%}"
        lines.append(f"- {name}: **{pretty}**")
    lines.append("")
    path.write_text("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# Build (clean + load + validate + report)
# ---------------------------------------------------------------------------
def run_build(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    db_path: Path = DUCKDB_PATH,
    inception=QLD_INCEPTION,
) -> dict:
    clean.clean_all(raw_dir=raw_dir, processed_dir=processed_dir, inception=inception)
    load_db.load_to_duckdb(processed_dir=processed_dir, db_path=db_path)
    report = run_validation(raw_dir, processed_dir, inception)
    qld = pd.read_parquet(processed_dir / "qld.parquet")
    write_report(report, qld)
    print(json.dumps(report, indent=2, default=str))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="QLD backtest data pipeline")
    parser.add_argument("command", choices=["fetch", "build", "all", "demo"])
    args = parser.parse_args(argv)

    if args.command in ("fetch", "all"):
        run_fetch()
    if args.command == "demo":
        from .demo import generate_demo_raw

        generate_demo_raw()
        print("Demo raw data written to", RAW_DIR)
    if args.command in ("build", "all", "demo"):
        run_build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

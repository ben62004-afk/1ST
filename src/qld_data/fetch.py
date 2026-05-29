"""Fetch layer: download raw price data and persist it immutably.

Design decisions / tradeoffs:
* The raw layer stores the *original* CSV text verbatim, plus a sidecar
  ``.meta.json`` recording source / fetch time / SHA256. All cleaning later
  recomputes from this, so the raw layer is the auditable ground truth.
* Network IO is injected via a ``downloader`` callable so parsers and the
  append/idempotency logic can be tested offline (no real network in CI).
* Incremental: when a raw file already exists we only request rows after its
  last date and append them, so reruns neither duplicate nor rewrite history.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from .config import RAW_DIR, STOOQ_SYMBOLS, TIINGO_SYMBOLS

CANON_COLS = ["open", "high", "low", "close", "adj_close", "volume"]
Downloader = Callable[[str], str]


# ---------------------------------------------------------------------------
# Network (only used outside tests)
# ---------------------------------------------------------------------------
def _http_get(url: str) -> str:
    import requests

    resp = requests.get(url, timeout=30, headers={"User-Agent": "qld-data/1.0"})
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Parsers (raw text -> canonical DataFrame)
# ---------------------------------------------------------------------------
def parse_stooq_csv(text: str) -> pd.DataFrame:
    """Parse a Stooq daily CSV into the canonical schema.

    Stooq prices are already split/dividend adjusted, so ``adj_close`` mirrors
    ``close``.
    """
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["adj_close"] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = pd.NA
    return df[CANON_COLS]


def parse_tiingo_json(text: str) -> pd.DataFrame:
    """Parse a Tiingo daily JSON payload into the canonical schema."""
    data = json.loads(text) if isinstance(text, str) else text
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.rename(columns={"adjClose": "adj_close"})
    if "adj_close" not in df.columns:
        df["adj_close"] = df["close"]
    return df[CANON_COLS]


# ---------------------------------------------------------------------------
# Raw persistence helpers
# ---------------------------------------------------------------------------
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_meta(path: Path, source: str, source_url: str, text: str, rows: int) -> None:
    meta = {
        "source": source,
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(text),
        "rows": rows,
    }
    path.with_suffix(".csv.meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def _last_date(path: Path, parser) -> pd.Timestamp | None:
    if not path.exists():
        return None
    df = parser(path.read_text())
    return None if df.empty else df.index.max()


def _merge_stooq_text(existing_text: str | None, new_text: str) -> str:
    """Append new Stooq rows to existing CSV text, de-duplicating by date."""
    new_df = parse_stooq_csv(new_text)
    if existing_text is None:
        combined = new_df
    else:
        combined = pd.concat([parse_stooq_csv(existing_text), new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    out = combined.reset_index()[
        ["date", "open", "high", "low", "close", "volume"]
    ].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    return out.to_csv(index=False)


# ---------------------------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------------------------
def fetch_stooq(
    key: str,
    downloader: Downloader = _http_get,
    raw_dir: Path = RAW_DIR,
) -> Path:
    """Fetch a Stooq series into ``raw_dir/<key>_stooq.csv`` (incremental)."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    symbol = STOOQ_SYMBOLS[key]
    path = raw_dir / f"{key}_stooq.csv"

    last = _last_date(path, parse_stooq_csv)
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    if last is not None:
        d1 = (last + pd.Timedelta(days=1)).strftime("%Y%m%d")
        url += f"&d1={d1}"

    new_text = downloader(url)
    try:
        parse_stooq_csv(new_text)
        has_rows = True
    except Exception:
        has_rows = False  # empty/no-new-data response

    existing = path.read_text() if path.exists() else None
    merged = _merge_stooq_text(existing, new_text) if has_rows else (existing or "")
    path.write_text(merged)
    df = parse_stooq_csv(merged)
    _write_meta(path, "stooq", url, merged, len(df))
    return path


def fetch_tiingo(
    key: str,
    api_key: str,
    downloader: Downloader = _http_get,
    raw_dir: Path = RAW_DIR,
) -> Path:
    """Fetch a Tiingo series into ``raw_dir/<key>_tiingo.csv`` (saved as JSON text).

    Tiingo returns the full requested range; we request from the day after the
    last stored date for incremental updates.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    symbol = TIINGO_SYMBOLS[key]
    path = raw_dir / f"{key}_tiingo.json"

    last = _last_date(path, parse_tiingo_json)
    url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?token={api_key}&format=json"
    if last is not None:
        start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        url += f"&startDate={start}"

    new_text = downloader(url)
    new_df = parse_tiingo_json(new_text)
    if path.exists():
        combined = pd.concat([parse_tiingo_json(path.read_text()), new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = new_df
    out = combined.reset_index().rename(columns={"adj_close": "adjClose"})
    out["date"] = out["date"].dt.strftime("%Y-%m-%dT00:00:00.000Z")
    text = out.to_json(orient="records")
    path.write_text(text)
    _write_meta(path, "tiingo", url.split("token=")[0] + "token=***", text, len(combined))
    return path

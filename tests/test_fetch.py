"""Tests for the fetch layer. No real network is used: a fake downloader is
injected, and parsers are exercised against small fixtures."""

from __future__ import annotations

import json

import pandas as pd

from qld_data import fetch

STOOQ_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2006-06-21,50.0,51.0,49.5,50.5,1000\n"
    "2006-06-22,50.5,52.0,50.0,51.5,1200\n"
)

TIINGO_JSON = json.dumps(
    [
        {
            "date": "2006-06-21T00:00:00.000Z",
            "open": 50.0,
            "high": 51.0,
            "low": 49.5,
            "close": 50.5,
            "volume": 1000,
            "adjClose": 25.1,
        },
        {
            "date": "2006-06-22T00:00:00.000Z",
            "open": 50.5,
            "high": 52.0,
            "low": 50.0,
            "close": 51.5,
            "volume": 1200,
            "adjClose": 25.6,
        },
    ]
)


def test_parse_stooq_canonical_schema():
    df = fetch.parse_stooq_csv(STOOQ_CSV)
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert df.index.name == "date"
    assert df.index.is_monotonic_increasing
    # Stooq close is already split/dividend adjusted -> adj_close mirrors close.
    assert (df["adj_close"] == df["close"]).all()
    assert df.loc[pd.Timestamp("2006-06-22"), "close"] == 51.5


def test_parse_tiingo_uses_adjclose():
    df = fetch.parse_tiingo_json(TIINGO_JSON)
    assert df.loc[pd.Timestamp("2006-06-21"), "adj_close"] == 25.1
    assert df.loc[pd.Timestamp("2006-06-21"), "close"] == 50.5


def test_fetch_writes_raw_and_meta_with_sha256(tmp_path):
    calls = []

    def fake_dl(url):
        calls.append(url)
        return STOOQ_CSV

    path = fetch.fetch_stooq("qld", downloader=fake_dl, raw_dir=tmp_path)
    assert path.exists()
    assert path.read_text() == STOOQ_CSV  # raw saved verbatim
    meta = json.loads(path.with_suffix(".csv.meta.json").read_text())
    import hashlib

    assert meta["sha256"] == hashlib.sha256(STOOQ_CSV.encode()).hexdigest()
    assert meta["rows"] == 2
    assert meta["source"] == "stooq"


def test_fetch_is_idempotent_when_no_new_rows(tmp_path):
    def fake_dl(url):
        return STOOQ_CSV

    p1 = fetch.fetch_stooq("qld", downloader=fake_dl, raw_dir=tmp_path)
    text1 = p1.read_text()
    meta1 = (p1.with_suffix(".csv.meta.json")).read_text()

    # Second run: downloader returns only already-known rows -> no change.
    def fake_dl_same(url):
        return STOOQ_CSV

    p2 = fetch.fetch_stooq("qld", downloader=fake_dl_same, raw_dir=tmp_path)
    assert p2.read_text() == text1
    # sha256 of content is unchanged (fetched_at may differ but content stable).
    assert json.loads(meta1)["sha256"] == json.loads(
        p2.with_suffix(".csv.meta.json").read_text()
    )["sha256"]


def test_fetch_appends_only_new_rows(tmp_path):
    def dl_first(url):
        return STOOQ_CSV

    fetch.fetch_stooq("qld", downloader=dl_first, raw_dir=tmp_path)

    new_rows = (
        "Date,Open,High,Low,Close,Volume\n"
        "2006-06-23,51.5,53.0,51.0,52.5,1300\n"
    )

    def dl_more(url):
        return new_rows

    path = fetch.fetch_stooq("qld", downloader=dl_more, raw_dir=tmp_path)
    df = fetch.parse_stooq_csv(path.read_text())
    assert len(df) == 3
    assert df.index.max() == pd.Timestamp("2006-06-23")
    assert df.index.is_unique

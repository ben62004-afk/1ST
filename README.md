# QLD Backtest Database

A **reproducible, single-source-risk-resistant** daily price database for
backtesting the *QLD-Resonance* strategy (DCA into QLD, filtered by the NDX
200-day moving average).

It builds two daily series:

- **QLD** — the 2x NASDAQ-100 ETF. QLD only launched **2006-06-21**, so it
  misses the 2000–2002 dot-com crash (when NDX fell ~−83%). Before inception we
  **synthesise QLD** from NDX returns so 2x tail risk is captured.
- **^NDX** — the NASDAQ-100 index.

### Synthetic-QLD model

```
r_QLD = L · r_NDX − (L − 1) · r_f / 252 − ER / 252
```

| Symbol | Meaning | Value |
|---|---|---|
| `L`  | leverage | `2` |
| `r_f`| annual financing cost | **constant `0.02` for now — TODO: real SOFR / Fed Funds** |
| `ER` | QLD expense ratio | `0.0095` |

---

## Data layout

```
data/
├── raw/         # immutable: original CSV + .meta.json (source, fetched_at, SHA256)
├── processed/   # rebuilt from raw/: unified OHLCV + synthetic series (parquet)
└── backtest.duckdb
```

- **`raw/` is never overwritten** — all cleaning recomputes from it.
- `processed/`, `backtest.duckdb` and `coverage_report.md` are **derived** and
  git-ignored (recomputable any time).

---

## How to reproduce (zero programming background)

### 0. One-time setup

```bash
pip install -r requirements.txt        # pinned versions for determinism
```

### 1a. Build with REAL data (needs internet)

The fetch step downloads from **Stooq** (primary) and, if you set an API key,
**Tiingo** (cross-check). These hosts must be reachable.

```bash
export TIINGO_API_KEY=your_key_here    # optional, enables cross-source check
PYTHONPATH=src python -m qld_data.pipeline all
```

> If you are on Claude Code on the web, `stooq.com` / `api.tiingo.com` must be
> in your environment's network allowlist; otherwise run this step locally.

### 1b. Try it now with DEMO data (no internet)

Generates deterministic, clearly-labelled **non-real** data so you can see the
whole pipeline run end-to-end:

```bash
PYTHONPATH=src python -m qld_data.pipeline demo
```

### 2. What you get

- `data/backtest.duckdb` with tables `qld`, `ndx`, `rf` (indexed by `date`).
- `data/coverage_report.md` summarising coverage and all validations.

### 3. Query it

```bash
PYTHONPATH=src python -c "
import duckdb; con=duckdb.connect('data/backtest.duckdb')
print(con.execute('SELECT min(date), max(date), count(*) FROM qld').fetchall())
"
```

---

## Pipeline commands

| Command | Does |
|---|---|
| `python -m qld_data.pipeline fetch` | download raw -> `raw/` (+ SHA256 meta), incremental |
| `python -m qld_data.pipeline build` | clean -> processed parquet -> DuckDB -> validate -> report |
| `python -m qld_data.pipeline all`   | `fetch` then `build` |
| `python -m qld_data.pipeline demo`  | generate DEMO raw data, then `build` |

Run with `PYTHONPATH=src` from the project root.

---

## Modules

| File | Role |
|---|---|
| `src/qld_data/config.py`   | all parameters / paths / tolerances (single source of truth) |
| `src/qld_data/synth.py`    | synthetic-QLD maths (pure functions) |
| `src/qld_data/fetch.py`    | download raw + SHA256 meta, incremental & idempotent |
| `src/qld_data/clean.py`    | standardise + splice synthetic (pre-2006) & real QLD |
| `src/qld_data/load_db.py`  | processed parquet -> DuckDB with date index |
| `src/qld_data/validate.py` | the 5 acceptance checks |
| `src/qld_data/pipeline.py` | orchestration + CLI |
| `src/qld_data/demo.py`     | deterministic DEMO data (NOT real market data) |

---

## Validation (acceptance criteria)

| Check | Rule |
|---|---|
| Trading-day continuity | 0 missing sessions vs the NYSE (`XNYS`) calendar |
| Cross-source agreement | Stooq vs Tiingo same-day close, `|Δ|/close < 0.5%` (else raises) |
| Synthetic seam | real vs synthetic QLD return correlation **> 0.98** |
| Reproducibility | delete `processed/`, rebuild from `raw/` -> identical content hash |
| Drawdown sanity | DuckDB shows the 2008 / 2020-03 / 2022 declines |

Run the tests (tests-before-implementation throughout):

```bash
PYTHONPATH=src python -m pytest -q
```

---

## Determinism

- All dependency versions are pinned in `requirements.txt`.
- No randomness in the production path; the synthetic model is a pure
  deterministic calculation.
- The raw layer is immutable; cleaning always recomputes from it, so reruns and
  rebuilds produce byte-stable processed output.

## Known limitations / TODO

- **Financing cost `r_f` is a constant 2%.** Replace with historical SOFR /
  Fed Funds (`config.RF_CONST_ANNUAL` and `clean.build_rf_series`).
- Tiingo's free tier has no NASDAQ-100 index; `QQQ` is used as the NDX
  cross-check proxy (`config.TIINGO_SYMBOLS`).
- The committed repo ships **no data** — run `fetch` (real) or `demo` to populate.

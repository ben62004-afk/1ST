import pandas as pd

from qld_ewma.data import load_prices, INCEPTION_QLD


def test_synthetic_is_deterministic():
    a = load_prices(force_synthetic=True, seed=42, end="2012-01-01")
    b = load_prices(force_synthetic=True, seed=42, end="2012-01-01")
    pd.testing.assert_frame_equal(a.prices, b.prices)
    assert a.synthetic and a.source == "synthetic"


def test_synthetic_has_required_columns():
    pd_ = load_prices(force_synthetic=True, seed=1, end="2011-01-01")
    for col in ["NDX", "QQQ", "QLD", "SHY"]:
        assert col in pd_.prices.columns
    assert pd_.prices.index.is_monotonic_increasing


def test_signal_instrument_is_not_qld():
    pdz = load_prices(force_synthetic=True, seed=1, end="2011-01-01")
    # signal property returns NDX (or QQQ proxy), never QLD.
    assert pdz.signal.name in ("NDX", "QQQ")


def test_start_date_is_qld_inception():
    pdz = load_prices(force_synthetic=True, seed=1, end="2008-01-01")
    assert pdz.prices.index[0] >= pd.Timestamp(INCEPTION_QLD)


def test_leverage_decay_present():
    # Over a full sample, 2x daily QLD should not be exactly 2x NDX total return
    # (volatility decay). Confirm the engine's synthetic QLD exhibits this.
    pdz = load_prices(force_synthetic=True, seed=7)
    p = pdz.prices
    ndx_tr = p["NDX"].iloc[-1] / p["NDX"].iloc[0] - 1
    qld_tr = p["QLD"].iloc[-1] / p["QLD"].iloc[0] - 1
    # Not asserting direction (depends on path) but that they differ from naive 2x.
    assert abs(qld_tr - 2 * ndx_tr) > 1e-6

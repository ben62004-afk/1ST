"""QLD/SHY EWMA-200 regime-switching backtest package."""

from .signals import ewma, sma, generate_signal
from .backtest import run_backtest, BacktestResult
from .metrics import performance_metrics
from .data import load_prices, INCEPTION_QLD

__all__ = [
    "ewma",
    "sma",
    "generate_signal",
    "run_backtest",
    "BacktestResult",
    "performance_metrics",
    "load_prices",
    "INCEPTION_QLD",
]

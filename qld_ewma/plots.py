"""Plotting helpers: equity curve and drawdown chart (PNG output)."""

from __future__ import annotations

from typing import Dict

import matplotlib

matplotlib.use("Agg")  # headless / deterministic
import matplotlib.pyplot as plt  # noqa: E402

from .metrics import drawdown_series  # noqa: E402


def plot_equity_curves(curves: Dict[str, "pd.Series"], path: str, title: str) -> str:
    fig, ax = plt.subplots(figsize=(11, 6))
    for label, eq in curves.items():
        ax.plot(eq.index, eq.values, label=label, linewidth=1.3)
    ax.set_yscale("log")
    ax.set_title(title)
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_drawdowns(curves: Dict[str, "pd.Series"], path: str, title: str) -> str:
    fig, ax = plt.subplots(figsize=(11, 5))
    for label, eq in curves.items():
        dd = drawdown_series(eq) * 100.0
        ax.plot(dd.index, dd.values, label=label, linewidth=1.1)
    ax.set_title(title)
    ax.set_ylabel("Drawdown (%)")
    ax.set_xlabel("Date")
    ax.legend(loc="lower left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path

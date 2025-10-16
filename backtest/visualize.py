"""Visualization helpers for backtest results."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd

from .backtest_engine import BacktestSummary


def plot_equity_curve(summary: BacktestSummary, output_path: Path | None = None) -> Path:
    if not summary.trades:
        raise ValueError("No trades available to plot")

    df = pd.DataFrame(
        {
            "timestamp": [trade.timestamp for trade in summary.trades],
            "return_pct": [trade.return_pct for trade in summary.trades],
        }
    )
    df.sort_values("timestamp", inplace=True)
    df["equity"] = (1 + df["return_pct"]).cumprod()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["timestamp"], df["equity"], label="Equity Curve")
    ax.set_title("Strategy Equity Curve")
    ax.set_ylabel("Growth (x)")
    ax.set_xlabel("Time")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)

    output_path = output_path or Path("equity_curve.png")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path

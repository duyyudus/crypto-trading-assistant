"""Indicator helper functions built on top of pandas/pandas-ta."""
from __future__ import annotations

from typing import Optional

import pandas as pd

try:  # pragma: no cover - optional dependency guard
    import pandas_ta as ta
except Exception:  # pragma: no cover - fallback when pandas_ta is missing
    ta = None

from .utils import logger


def ema(series: pd.Series, length: int) -> pd.Series:
    if ta is not None:
        return ta.ema(series, length=length)  # type: ignore[arg-type]
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    if ta is not None:
        return ta.sma(series, length=length)  # type: ignore[arg-type]
    return series.rolling(window=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    if ta is not None:
        return ta.rsi(series, length=length)  # type: ignore[arg-type]
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger_bands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    mid = sma(series, length)
    std_dev = series.rolling(window=length).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def ema_trending_up(series: pd.Series, length: int = 20, lookback: int = 3) -> bool:
    ema_series = ema(series, length)
    recent = ema_series.dropna().tail(lookback + 1)
    if len(recent) <= lookback:
        return False
    is_up = all(x < y for x, y in zip(recent.iloc[:-1], recent.iloc[1:]))
    logger.debug("EMA trending up result: %s", is_up)
    return is_up


def swing_high(series: pd.Series, lookback: int = 5) -> Optional[float]:
    if len(series) < lookback:
        return None
    return series.iloc[-lookback:].max()

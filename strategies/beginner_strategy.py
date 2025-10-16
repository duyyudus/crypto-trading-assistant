"""Beginner multi-timeframe strategy implementation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from core.indicators import ema, ema_trending_up, rsi, swing_high
from .base_strategy import BaseStrategy, StrategyContext, StrategySignal


@dataclass(slots=True)
class ConditionResult:
    name: str
    passed: bool
    details: str


def _latest_closed(frame: pd.DataFrame) -> Optional[pd.Series]:
    if len(frame) < 2:
        return None
    return frame.iloc[-2]


class BeginnerStrategy(BaseStrategy):
    name = "beginner_strategy"

    def __init__(self) -> None:
        super().__init__()
        # Get a logger instance for strategy-level logging
        self.logger = logging.getLogger("crypto_trading_assistant.backtest.strategy")
        self.logger.debug("Beginner strategy initialized")

    def _daily_trend(self, frame: pd.DataFrame) -> ConditionResult:
        candle = _latest_closed(frame)
        if candle is None:
            return ConditionResult("daily_trend", False, "Insufficient candles for 1D timeframe")
        closes = frame["close"].astype(float)
        ema50 = ema(closes, 50)
        ema_value = float(ema50.iloc[-2]) if len(ema50) >= 2 else float("nan")
        close_price = float(candle["close"])
        passed = close_price > ema_value if pd.notna(ema_value) else False
        details = f"close={close_price:.2f}, ema50={ema_value:.2f}"
        return ConditionResult("daily_trend", passed, details)

    def _four_hour_momentum(self, frame: pd.DataFrame) -> ConditionResult:
        candle = _latest_closed(frame)
        if candle is None:
            return ConditionResult("4h_momentum", False, "Insufficient candles for 4H timeframe")
        closes = frame["close"].astype(float)
        rsi_series = rsi(closes, 14)
        rsi_value = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 else float("nan")
        ema_up = ema_trending_up(closes, length=20, lookback=3)
        passed = (rsi_value > 50) and ema_up if pd.notna(rsi_value) else False
        details = f"rsi14={rsi_value:.2f}, ema20_up={ema_up}, threshold=50"
        return ConditionResult("4h_momentum", passed, details)

    def _one_hour_entry(self, frame: pd.DataFrame) -> ConditionResult:
        candle = _latest_closed(frame)
        if candle is None:
            return ConditionResult("1h_entry", False, "Insufficient candles for 1H timeframe")
        highs = frame["high"].astype(float)
        historical_highs = highs.iloc[:-2]  # exclude the current candle and the most recent open candle
        if len(historical_highs) < 10:
            return ConditionResult("1h_entry", False, "Insufficient history for swing high")
        swing = swing_high(historical_highs, lookback=10)
        if swing is None:
            return ConditionResult("1h_entry", False, "Unable to determine swing high")
        close_price = float(candle["close"])
        low_price = float(candle["low"])
        passed = close_price > swing and low_price <= swing
        details = f"close={close_price:.2f}, swing_high={swing:.2f}, low={low_price:.2f}"
        return ConditionResult("1h_entry", passed, details)

    def check_signal(self, context: StrategyContext) -> StrategySignal:
        self.logger.debug("Checking signal for %s with %d timeframes", context.symbol, len(context.candles))

        required_tfs = {"1d", "4h", "1h"}
        missing = required_tfs - set(context.candles)

        if missing:
            self.logger.debug("Missing required timeframes for %s: %s", context.symbol, sorted(missing))
            return StrategySignal(False, f"Missing timeframes: {', '.join(sorted(missing))}")

        self.logger.debug("Evaluating conditions for %s", context.symbol)

        # Evaluate each condition
        daily = self._daily_trend(context.candles["1d"])
        self.logger.debug("Daily trend condition: %s - %s", daily.name, "PASS" if daily.passed else "FAIL")

        four_h = self._four_hour_momentum(context.candles["4h"])
        self.logger.debug("4H momentum condition: %s - %s", four_h.name, "PASS" if four_h.passed else "FAIL")

        one_h = self._one_hour_entry(context.candles["1h"])
        self.logger.debug("1H entry condition: %s - %s", one_h.name, "PASS" if one_h.passed else "FAIL")

        conditions = [daily, four_h, one_h]
        passed = all(cond.passed for cond in conditions)

        parts = [f"{cond.name}: {'✅' if cond.passed else '❌'} ({cond.details})" for cond in conditions]
        message = f"{context.symbol} | Beginner Strategy | " + " | ".join(parts)

        self.logger.debug("Signal evaluation for %s: %s - %s",
                    context.symbol,
                    "TRIGGERED" if passed else "NOT TRIGGERED",
                    " | ".join([f"{cond.name}={'✅' if cond.passed else '❌'}" for cond in conditions]))

        return StrategySignal(passed, message, metadata={cond.name: cond.details for cond in conditions})

"""Strategy base classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import pandas as pd


@dataclass(slots=True)
class StrategySignal:
    triggered: bool
    message: str
    metadata: Optional[Mapping[str, object]] = None


@dataclass(slots=True)
class StrategyContext:
    symbol: str
    candles: Dict[str, pd.DataFrame]


class BaseStrategy(ABC):
    name: str = "base_strategy"

    def __init__(self) -> None:
        self.last_signal: Optional[StrategySignal] = None

    @abstractmethod
    def check_signal(self, context: StrategyContext) -> StrategySignal:
        """Return the most recent trading signal for ``context``."""

    def __call__(self, context: StrategyContext) -> StrategySignal:
        signal = self.check_signal(context)
        self.last_signal = signal
        return signal

"""Market data fetching utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional

import pandas as pd

from .candles import CandleRepository, CandleSynchronizer
from .utils import ExchangeTimeframe, Settings, logger, timeframe_metadata


@dataclass(slots=True)
class FetchResult:
    symbol: str
    candles: Dict[str, pd.DataFrame]


class MarketDataFetcher:
    """Fetches and caches data from the configured exchange."""

    def __init__(
        self,
        settings: Settings,
        repository: CandleRepository,
        synchronizer: Optional[CandleSynchronizer] = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.synchronizer = synchronizer
        self.timeframes: Dict[str, ExchangeTimeframe] = timeframe_metadata(settings.timeframes)

    def _lookback_map(self) -> Dict[str, int]:
        return {tf: meta.lookback for tf, meta in self.timeframes.items()}

    def fetch_symbol(self, symbol: str) -> FetchResult:
        logger.info("Fetching data for %s", symbol)
        lookbacks = self._lookback_map()
        candles: Dict[str, pd.DataFrame] = {}
        for tf_key, metadata in self.timeframes.items():
            required = lookbacks[tf_key] + 2
            frame = self.repository.get_candles(symbol, tf_key, limit=required)
            if len(frame) < required and self.synchronizer is not None:
                logger.info(
                    "Not enough cached candles for %s/%s (have %d, need %d); synchronizing",
                    symbol,
                    tf_key,
                    len(frame),
                    required,
                )
                self.synchronizer.sync_symbol_timeframe(
                    symbol,
                    tf_key,
                    start_time=self.settings.candle_start_date,
                )
                frame = self.repository.get_candles(symbol, tf_key, limit=required)
            candles[tf_key] = frame
        return FetchResult(symbol=symbol, candles=candles)

    def fetch_all(self, symbols: Optional[Iterable[str]] = None) -> Dict[str, FetchResult]:
        symbols = list(symbols or self.settings.symbols)
        results: Dict[str, FetchResult] = {}
        for symbol in symbols:
            results[symbol] = self.fetch_symbol(symbol)
        return results

    def latest_closed(self, frame: pd.DataFrame) -> Optional[pd.Series]:
        if len(frame) < 2:
            return None
        return frame.iloc[-2]

    def latest_close_price(self, frame: pd.DataFrame) -> Optional[float]:
        candle = self.latest_closed(frame)
        if candle is None:
            return None
        return float(candle["close"])

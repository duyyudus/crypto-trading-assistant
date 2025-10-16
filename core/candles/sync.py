"""Utilities for synchronizing candles from exchanges into PostgreSQL."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Mapping, Optional

import pandas as pd

from ..exchanges.binance import BinanceSpotClient
from ..utils import ExchangeTimeframe, logger, utc_now
from .repository import CandleRepository


@dataclass(slots=True)
class SyncStats:
    symbol: str
    timeframe: str
    inserted: int


class CandleSynchronizer:
    """Synchronize exchange candles into the PostgreSQL-backed repository."""

    def __init__(
        self,
        repository: CandleRepository,
        client: BinanceSpotClient,
        timeframe_map: Mapping[str, ExchangeTimeframe],
    ) -> None:
        self.repository = repository
        self.client = client
        self.timeframe_map = dict(timeframe_map)

    def _timeframe_delta(self, timeframe_key: str) -> timedelta:
        metadata = self.timeframe_map[timeframe_key]
        minutes = max(metadata.refresh_minutes, 1)
        return timedelta(minutes=minutes)

    def _next_start(
        self, existing: Optional[datetime], requested_start: Optional[datetime], delta: timedelta
    ) -> Optional[datetime]:
        if existing:
            return existing + delta
        return requested_start

    def sync_symbol_timeframe(
        self,
        symbol: str,
        timeframe_key: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> SyncStats:
        """Synchronize candles for a specific symbol and timeframe."""

        if timeframe_key not in self.timeframe_map:
            raise KeyError(f"Unknown timeframe {timeframe_key}")

        delta = self._timeframe_delta(timeframe_key)
        latest = self.repository.latest_open_time(symbol, timeframe_key)
        fetch_start = self._next_start(latest, start_time, delta)
        if fetch_start is None:
            logger.info(
                "No start time provided and no existing data for %s/%s; skipping",
                symbol,
                timeframe_key,
            )
            return SyncStats(symbol=symbol, timeframe=timeframe_key, inserted=0)

        upper_bound = end_time or utc_now()
        inserted = 0
        while fetch_start <= upper_bound:
            logger.info(
                "Fetching candles for %s %s starting %s",
                symbol,
                timeframe_key,
                fetch_start,
            )
            frame = self.client.fetch_klines(
                symbol=symbol,
                timeframe=self.timeframe_map[timeframe_key],
                limit=1000,
                start_time=fetch_start,
                end_time=upper_bound,
            )
            if frame.empty:
                break

            # Filter out candles that were already present to avoid reprocessing.
            frame = frame[frame["open_time"] >= fetch_start]
            if frame.empty:
                break

            inserted += self.repository.upsert_frame(symbol, timeframe_key, frame)
            last_open_time = pd.Timestamp(frame["open_time"].max()).to_pydatetime()
            fetch_start = last_open_time + delta
            if fetch_start > upper_bound:
                break

        return SyncStats(symbol=symbol, timeframe=timeframe_key, inserted=inserted)

    def sync_symbols(
        self,
        symbols: Iterable[str],
        timeframes: Optional[Iterable[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[SyncStats]:
        """Synchronize multiple symbols/timeframes."""

        stats: List[SyncStats] = []
        requested_timeframes = list(timeframes or self.timeframe_map.keys())
        for symbol in symbols:
            for timeframe in requested_timeframes:
                stats.append(self.sync_symbol_timeframe(symbol, timeframe, start_time, end_time))
        return stats

    def schedule_periodic_updates(
        self,
        scheduler,
        symbols: Iterable[str],
        timeframes: Optional[Iterable[str]] = None,
    ) -> None:
        """Register periodic sync jobs on the provided ``schedule`` scheduler."""

        import schedule as schedule_module  # lazy import to keep dependency optional

        if scheduler is None:
            scheduler = schedule_module

        requested_timeframes = list(timeframes or self.timeframe_map.keys())
        for timeframe_key in requested_timeframes:
            delta = self._timeframe_delta(timeframe_key)
            minutes = max(int(delta.total_seconds() // 60), 1)

            def _job(symbols=symbols, timeframe=timeframe_key) -> None:
                self.sync_symbols(symbols=symbols, timeframes=[timeframe])

            job = scheduler.every(minutes).minutes if minutes != 1440 else scheduler.every().day
            job.do(_job)

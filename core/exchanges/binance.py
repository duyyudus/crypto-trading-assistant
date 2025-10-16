"""Binance Spot exchange client."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional

import pandas as pd
import requests

from ..utils import ExchangeTimeframe, logger

BINANCE_REST_ENDPOINT = "https://api.binance.com"


@dataclass(slots=True)
class BinanceCredentials:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None


class BinanceSpotClient:
    """Lightweight REST client for fetching Binance candle data."""

    def __init__(self, credentials: Optional[BinanceCredentials] = None, session: Optional[requests.Session] = None) -> None:
        self.credentials = credentials or BinanceCredentials()
        self.session = session or requests.Session()
        if self.credentials.api_key:
            self.session.headers.update({"X-MBX-APIKEY": self.credentials.api_key})

    def _request(self, method: str, path: str, params: Optional[Dict[str, str]] = None) -> requests.Response:
        url = f"{BINANCE_REST_ENDPOINT}{path}"
        response = self.session.request(method, url, params=params, timeout=10)
        response.raise_for_status()
        return response

    def fetch_klines(
        self,
        symbol: str,
        timeframe: ExchangeTimeframe,
        limit: int,
        end_time: Optional[datetime | int] = None,
        start_time: Optional[datetime | int] = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data and return as a pandas DataFrame."""

        params = {
            "symbol": symbol.upper(),
            "interval": timeframe.interval,
            "limit": min(limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = (
                int(start_time.timestamp() * 1000)
                if isinstance(start_time, datetime)
                else start_time
            )
        if end_time is not None:
            params["endTime"] = (
                int(end_time.timestamp() * 1000)
                if isinstance(end_time, datetime)
                else end_time
            )

        logger.debug("Requesting %s klines for %s", symbol, timeframe.interval)
        response = self._request("GET", "/api/v3/klines", params=params)
        payload = response.json()
        frame = pd.DataFrame(
            payload,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )
        numeric_cols = ["open", "high", "low", "close", "volume", "quote_asset_volume", "taker_buy_base", "taker_buy_quote"]
        for col in numeric_cols:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
        frame.drop(columns=["ignore"], inplace=True)
        return frame

    def fetch_historical_range(
        self,
        symbol: str,
        timeframe: ExchangeTimeframe,
        lookback: int,
    ) -> pd.DataFrame:
        """Fetch enough klines to satisfy ``lookback`` + 1 requirement."""

        limit = max(lookback + 2, 50)
        logger.info("Fetching %s candles for %s (%s)", limit, symbol, timeframe.interval)
        frame = self.fetch_klines(symbol, timeframe, limit)
        return frame

    def fetch_multiple(
        self,
        symbol: str,
        timeframe_map: Dict[str, ExchangeTimeframe],
        lookback_map: Dict[str, int],
    ) -> Dict[str, pd.DataFrame]:
        """Fetch candles for each timeframe specified in ``timeframe_map``."""

        results: Dict[str, pd.DataFrame] = {}
        for key, metadata in timeframe_map.items():
            lookback = lookback_map.get(key, metadata.lookback)
            frame = self.fetch_historical_range(symbol, metadata, lookback)
            results[key] = frame
            time.sleep(0.1)  # respect rate limits
        return results


def latest_closed_candle(frame: pd.DataFrame) -> Optional[pd.Series]:
    """Return the last fully closed candle."""

    if frame.empty:
        return None
    return frame.iloc[-2] if len(frame) > 1 else frame.iloc[-1]

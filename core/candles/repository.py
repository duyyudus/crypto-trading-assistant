"""Repository helpers for working with candle data."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy import Select, desc, func, select
from sqlalchemy.dialects.postgresql import insert

from ..database import Database
from ..models import Candle


class CandleRepository:
    """High-level data access helpers for OHLCV candles."""

    def __init__(self, database: Database, exchange: str) -> None:
        self._database = database
        self.exchange = exchange

    def _base_filter(self, symbol: str, timeframe: str) -> Select[tuple[Candle]]:
        stmt: Select[tuple[Candle]] = select(Candle).where(
            Candle.exchange == self.exchange,
            Candle.symbol == symbol.upper(),
            Candle.timeframe == timeframe.lower(),
        )
        return stmt

    def latest_open_time(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """Return the latest candle open time stored for ``symbol``/``timeframe``."""

        stmt = self._base_filter(symbol, timeframe).order_by(desc(Candle.open_time)).limit(1)
        with self._database.session() as session:
            result = session.execute(stmt).scalars().first()
            return result.open_time if result else None

    def upsert_frame(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> int:
        """Insert or update candles from ``frame``. Returns number of rows affected."""

        if frame.empty:
            return 0

        records: List[dict] = []
        for record in frame.to_dict(orient="records"):
            records.append(
                {
                    "exchange": self.exchange,
                    "symbol": symbol.upper(),
                    "timeframe": timeframe.lower(),
                    "open_time": pd.Timestamp(record["open_time"]).to_pydatetime(),
                    "close_time": pd.Timestamp(record["close_time"]).to_pydatetime(),
                    "open": float(record["open"]),
                    "high": float(record["high"]),
                    "low": float(record["low"]),
                    "close": float(record["close"]),
                    "volume": float(record["volume"]),
                    "quote_asset_volume": float(record["quote_asset_volume"])
                    if record.get("quote_asset_volume") is not None
                    else None,
                    "number_of_trades": int(record["number_of_trades"])
                    if record.get("number_of_trades") is not None
                    else None,
                    "taker_buy_base": float(record["taker_buy_base"])
                    if record.get("taker_buy_base") is not None
                    else None,
                    "taker_buy_quote": float(record["taker_buy_quote"])
                    if record.get("taker_buy_quote") is not None
                    else None,
                }
            )

        stmt = insert(Candle).values(records)
        update_columns = {
            column.name: getattr(stmt.excluded, column.name)
            for column in Candle.__table__.columns
            if not column.primary_key
        }
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=[
                Candle.exchange,
                Candle.symbol,
                Candle.timeframe,
                Candle.open_time,
            ],
            set_=update_columns,
        )

        with self._database.session() as session:
            result = session.execute(upsert_stmt)
            return result.rowcount or 0

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return candles for ``symbol``/``timeframe`` ordered by open time."""

        stmt = self._base_filter(symbol, timeframe).order_by(desc(Candle.open_time))
        if limit is not None:
            stmt = stmt.limit(limit)

        with self._database.session() as session:
            rows = session.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame(
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
                ]
            )

        data = [
            {
                "open_time": row.open_time,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "close_time": row.close_time,
                "quote_asset_volume": row.quote_asset_volume,
                "number_of_trades": row.number_of_trades,
                "taker_buy_base": row.taker_buy_base,
                "taker_buy_quote": row.taker_buy_quote,
            }
            for row in rows
        ]
        frame = pd.DataFrame(data)
        frame.sort_values("open_time", inplace=True)
        frame.reset_index(drop=True, inplace=True)
        return frame

    def count(self, symbol: str, timeframe: str) -> int:
        """Return the number of candles stored."""

        stmt = select(func.count()).select_from(
            Candle
        ).where(
            Candle.exchange == self.exchange,
            Candle.symbol == symbol.upper(),
            Candle.timeframe == timeframe.lower(),
        )
        with self._database.session() as session:
            return int(session.execute(stmt).scalar_one())

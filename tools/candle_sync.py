"""CLI tool for synchronizing historic candles into PostgreSQL."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import schedule
from dateutil import parser as date_parser

# Ensure project root is on PYTHONPATH so local packages import correctly when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.candles import CandleRepository, CandleSynchronizer
from core.database import Database, ensure_database
from core.exchanges.binance import BinanceCredentials, BinanceSpotClient
from core.utils import DEFAULT_TIMEFRAMES, Settings, logger, timeframe_metadata


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize OHLCV candles into PostgreSQL")
    parser.add_argument(
        "--symbols",
        help="Comma separated list of symbols (defaults to settings symbols)",
    )
    parser.add_argument(
        "--timeframes",
        help="Comma separated list of timeframes (defaults to settings timeframes)",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for historical sync (defaults to settings CANDLE_SYNC_START_DATE)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single synchronization pass and exit",
    )
    return parser.parse_args(argv)


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    settings = Settings.from_env()

    ensure_database(
        database_url=settings.database_url,
        superuser=settings.postgres_superuser,
        superuser_password=settings.postgres_superuser_password,
    )

    database = Database(settings.database_url)
    repository = CandleRepository(database=database, exchange=settings.exchange)
    credentials = BinanceCredentials(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
    )
    client = BinanceSpotClient(credentials=credentials)

    symbols = _split_csv(args.symbols) or settings.symbols
    timeframe_values = _split_csv(args.timeframes)
    if timeframe_values:
        timeframe_map = timeframe_metadata(timeframe_values)
    else:
        timeframe_map = timeframe_metadata(settings.timeframes or list(DEFAULT_TIMEFRAMES.keys()))

    start_date: datetime = settings.candle_start_date
    if args.start_date:
        parsed = date_parser.parse(args.start_date)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=start_date.tzinfo)
        start_date = parsed

    synchronizer = CandleSynchronizer(
        repository=repository,
        client=client,
        timeframe_map=timeframe_map,
    )

    logger.info(
        "Starting candle synchronization for symbols=%s timeframes=%s from %s",
        symbols,
        list(timeframe_map.keys()),
        start_date,
    )
    synchronizer.sync_symbols(symbols=symbols, timeframes=timeframe_map.keys(), start_time=start_date)

    if args.once:
        logger.info("Synchronization completed (single pass mode)")
        return

    synchronizer.schedule_periodic_updates(schedule, symbols=symbols, timeframes=timeframe_map.keys())
    logger.info("Entering continuous synchronization loop")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()

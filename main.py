"""Entry point for live monitoring."""
from __future__ import annotations

import argparse
import time
from typing import Optional

import schedule

from alert.telegram_bot import TelegramBot
from core.candles import CandleRepository, CandleSynchronizer
from core.database import Database, ensure_database
from core.data_fetcher import MarketDataFetcher
from core.exchanges.binance import BinanceCredentials, BinanceSpotClient
from core.utils import Settings, logger, timeframe_metadata
from strategies import load_strategy
from strategies.base_strategy import StrategyContext


def run_monitoring(settings: Settings, once: bool = False) -> None:
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
    timeframe_map = timeframe_metadata(settings.timeframes)
    synchronizer = CandleSynchronizer(
        repository=repository,
        client=client,
        timeframe_map=timeframe_map,
    )
    synchronizer.sync_symbols(settings.symbols, start_time=settings.candle_start_date)
    synchronizer.schedule_periodic_updates(schedule, settings.symbols)

    fetcher = MarketDataFetcher(
        settings=settings,
        repository=repository,
        synchronizer=synchronizer,
    )
    strategy = load_strategy(settings.strategy)
    telegram_bot: Optional[TelegramBot] = None
    if settings.alert_bot == "telegram":
        try:
            telegram_bot = TelegramBot.from_settings(settings)
        except ValueError as exc:
            logger.warning("Telegram disabled: %s", exc)

    def execute_cycle() -> None:
        logger.info("Running monitoring cycle")
        data_map = fetcher.fetch_all()
        for symbol, result in data_map.items():
            context = StrategyContext(symbol=symbol, candles=result.candles)
            signal = strategy(context)
            logger.info("Signal for %s: %s", symbol, signal.message)
            if signal.triggered and telegram_bot:
                telegram_bot.send_message(signal.message)

    if once:
        execute_cycle()
        return

    schedule.every(settings.check_interval_minutes).minutes.do(execute_cycle)
    execute_cycle()
    while True:
        schedule.run_pending()
        time.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live crypto trading assistant")
    parser.add_argument("--once", action="store_true", help="Run a single monitoring cycle and exit")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    settings = Settings.from_env()
    run_monitoring(settings, once=args.once)

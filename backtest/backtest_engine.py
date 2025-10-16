"""Simple backtesting engine for strategies."""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.candles import CandleRepository, CandleSynchronizer
from core.database import Database, ensure_database
from core.exchanges.binance import BinanceCredentials, BinanceSpotClient
from core.utils import Settings, get_backtest_logger, timeframe_metadata
from strategies import load_strategy
from strategies.base_strategy import StrategyContext


@dataclass(slots=True)
class TradeRecord:
    timestamp: pd.Timestamp
    message: str
    entry_price: float
    exit_price: float
    return_pct: float
    exit_timestamp: pd.Timestamp
    exit_reason: str


@dataclass(slots=True)
class BacktestSummary:
    trades: List[TradeRecord]
    win_rate: float
    average_return: float
    cumulative_return: float


class BacktestEngine:
    def __init__(
        self,
        settings: Settings,
        strategy_name: str,
        repository: CandleRepository,
        synchronizer: CandleSynchronizer,
    ) -> None:
        self.settings = settings
        self.strategy = load_strategy(strategy_name)
        self.repository = repository
        self.synchronizer = synchronizer
        self.timeframes = timeframe_metadata(settings.timeframes)
        self.logger = get_backtest_logger()
        self.base_timeframe = "1h"
        if self.base_timeframe not in self.timeframes:
            raise ValueError(f"Backtest requires {self.base_timeframe} timeframe in settings")
        self.warmup_bars = self._calculate_warmup_bars()
        self.logger.info("Backtest engine initialized with strategy: %s", strategy_name)
        self.logger.debug(
            "Configured timeframes: %s (base=%s, warmup_bars=%d)",
            list(self.timeframes.keys()),
            self.base_timeframe,
            self.warmup_bars,
        )

    def _timeframe_minutes(self, timeframe: str) -> int:
        metadata = self.timeframes[timeframe]
        return max(metadata.refresh_minutes, 1)

    def _calculate_timeframe_limits(self, base_limit: int) -> Dict[str, int]:
        if base_limit <= 0:
            raise ValueError("Backtest limit must be positive")

        if self.base_timeframe not in self.timeframes:
            raise ValueError(f"Backtest requires {self.base_timeframe} timeframe data")

        base_minutes = self._timeframe_minutes(self.base_timeframe)
        total_minutes = base_limit * base_minutes

        limits: Dict[str, int] = {}
        for key, metadata in self.timeframes.items():
            timeframe_minutes = self._timeframe_minutes(key)
            if key == self.base_timeframe:
                computed = base_limit
            else:
                computed = math.ceil(total_minutes / timeframe_minutes)
                if metadata.lookback > 0:
                    computed = max(metadata.lookback, computed)
                computed = max(2, computed)
            limits[key] = computed

        return limits

    def _calculate_warmup_bars(self) -> int:
        base_minutes = self._timeframe_minutes(self.base_timeframe)
        warmup = 0
        for key, metadata in self.timeframes.items():
            lookback = max(metadata.lookback, 0)
            if lookback == 0:
                continue
            timeframe_minutes = self._timeframe_minutes(key)
            required_minutes = lookback * timeframe_minutes
            warmup_bars = math.ceil(required_minutes / base_minutes)
            warmup = max(warmup, warmup_bars)

        # Ensure at least two base candles to allow prior candle comparisons
        return max(warmup, 2)

    def _fetch(self, symbol: str, limit: int) -> Dict[str, pd.DataFrame]:
        self.logger.debug("Starting data fetch for %s with limit %d", symbol, limit)
        frames: Dict[str, pd.DataFrame] = {}

        timeframe_limits = self._calculate_timeframe_limits(limit)
        self.logger.debug("Computed per-timeframe limits for %s: %s", symbol, timeframe_limits)

        for key in self.timeframes.keys():
            tf_limit = timeframe_limits[key]
            self.logger.debug("Fetching %s candles for %s/%s timeframe", tf_limit, symbol, key)
            frame = self.repository.get_candles(symbol, key, limit=tf_limit)

            if len(frame) < tf_limit:
                self.logger.info(
                    "Backtest needs %d candles for %s/%s; synchronizing missing data (have %d)",
                    tf_limit,
                    symbol,
                    key,
                    len(frame)
                )
                self.logger.debug("Starting synchronization for %s/%s from %s", symbol, key, self.settings.candle_start_date)
                self.synchronizer.sync_symbol_timeframe(
                    symbol,
                    key,
                    start_time=self.settings.candle_start_date,
                )
                self.logger.debug("Synchronization completed for %s/%s, refetching data", symbol, key)
                frame = self.repository.get_candles(symbol, key, limit=tf_limit)
                self.logger.debug("After sync: %s/%s now has %d candles", symbol, key, len(frame))

            if len(frame) < tf_limit:
                self.logger.error("Insufficient candles for %s %s; expected %d, got %d", symbol, key, tf_limit, len(frame))
                raise ValueError(f"Insufficient candles for {symbol} {key}; expected {tf_limit}")

            # Log data quality info
            self.logger.debug("Data quality for %s/%s: %d candles, date range %s to %s",
                        symbol, key, len(frame),
                        frame.iloc[0]['open_time'] if len(frame) > 0 else 'N/A',
                        frame.iloc[-1]['open_time'] if len(frame) > 0 else 'N/A')

            frames[key] = frame

        self.logger.debug("Data fetch completed for %s: %s timeframes loaded", symbol, list(frames.keys()))
        return frames

    def run(
        self,
        symbol: str,
        limit: int = 500,
        lookahead: int = 3,
        take_profit_pct: float = 0.02,
        trailing_stop_pct: float = 0.02,
    ) -> BacktestSummary:
        self.logger.info("Starting backtest for %s with strategy '%s'", symbol, self.strategy.name)
        self.logger.debug(
            "Backtest parameters: limit=%d, lookahead=%d, take_profit=%.4f, trailing_stop=%.4f, timeframes=%s",
            limit,
            lookahead,
            take_profit_pct,
            trailing_stop_pct,
            list(self.timeframes.keys()),
        )

        if lookahead <= 0:
            raise ValueError("Backtest lookahead must be positive")
        if take_profit_pct <= 0:
            raise ValueError("Take-profit percentage must be positive")
        if trailing_stop_pct <= 0:
            raise ValueError("Trailing-stop percentage must be positive")

        frames = self._fetch(symbol, limit)
        base_tf = self.base_timeframe
        if base_tf not in frames:
            self.logger.error("Required %s timeframe data not available for %s", base_tf, symbol)
            raise ValueError(f"Backtest requires {base_tf} timeframe data")

        self.logger.debug("Using %s as base timeframe with %d candles", base_tf, len(frames[base_tf]))

        trades: List[TradeRecord] = []
        base_frame = frames[base_tf]
        start_index = self.warmup_bars
        if len(base_frame) <= start_index + lookahead:
            required = start_index + lookahead + 1
            self.logger.error(
                "Insufficient %s candles for backtest window; need at least %d, have %d",
                base_tf,
                required,
                len(base_frame),
            )
            raise ValueError(
                f"Backtest requires at least {required} {base_tf} candles, but only {len(base_frame)} are available. "
                "Increase the --limit value or adjust timeframe lookbacks."
            )

        total_iterations = len(base_frame) - lookahead - start_index
        self.logger.info(
            "Processing %d iterations from index %d to %d",
            total_iterations,
            start_index,
            len(base_frame) - lookahead,
        )

        # Progress tracking
        progress_interval = max(1, total_iterations // 10)  # Log progress every 10%
        signals_checked = 0
        signals_triggered = 0

        for idx in range(start_index, len(base_frame) - lookahead):
            # Progress logging
            current_iteration = idx - start_index
            if current_iteration % progress_interval == 0 or idx == len(base_frame) - lookahead - 1:
                progress = current_iteration / total_iterations * 100
                self.logger.debug(
                    "Progress: %.1f%% (%d/%d iterations, %d trades so far)",
                    progress,
                    current_iteration,
                    total_iterations,
                    len(trades),
                )

            base_candle = base_frame.iloc[idx]
            current_time = base_candle["open_time"]

            self.logger.debug("Processing iteration %d at %s, price=%.4f",
                        idx, current_time, float(base_candle["close"]))

            # Build context frames for this timestamp
            context_frames: Dict[str, pd.DataFrame] = {}
            skip = False

            for key, frame in frames.items():
                subset = frame[frame["open_time"] <= current_time]
                metadata = self.timeframes[key]
                min_required = max(2, metadata.lookback)
                if len(subset) < min_required:
                    self.logger.debug(
                        "Skipping iteration %d: %s timeframe has %d/%d candles",
                        idx,
                        key,
                        len(subset),
                        min_required,
                    )
                    skip = True
                    break
                context_frames[key] = subset.copy()

            if skip:
                continue

            # Check strategy signal
            context = StrategyContext(symbol=symbol, candles=context_frames)
            self.logger.debug("Evaluating strategy signal at %s", current_time)
            signal = self.strategy.check_signal(context)
            signals_checked += 1

            if not signal.triggered:
                self.logger.debug("No signal triggered at %s", current_time)
                continue

            signals_triggered += 1
            self.logger.info("Signal triggered at %s: %s", current_time, signal.message)
            self.logger.debug("Signal metadata: %s", signal.metadata if signal.metadata else "None")

            # Calculate trade result with dynamic exit rules
            entry_price = float(base_candle["close"])
            target_price = entry_price * (1 + take_profit_pct)
            trailing_stop_price = entry_price * (1 - trailing_stop_pct)
            highest_price = entry_price
            exit_price = entry_price
            exit_reason = "lookahead_exit"
            exit_timestamp = base_frame.iloc[idx + lookahead]["open_time"]

            self.logger.debug(
                "Trade simulation start: entry=%.4f, target=%.4f, trailing_stop=%.4f (lookahead=%d periods)",
                entry_price,
                target_price,
                trailing_stop_price,
                lookahead,
            )

            for offset in range(1, lookahead + 1):
                candle = base_frame.iloc[idx + offset]
                candle_time = candle["open_time"]
                high = float(candle["high"])
                low = float(candle["low"])
                close = float(candle["close"])

                if high >= target_price:
                    exit_price = target_price
                    exit_reason = "take_profit"
                    exit_timestamp = candle_time
                    self.logger.debug(
                        "Take-profit hit at %s: high=%.4f >= target=%.4f",
                        candle_time,
                        high,
                        target_price,
                    )
                    break

                highest_price = max(highest_price, high)
                trailing_stop_price = max(trailing_stop_price, highest_price * (1 - trailing_stop_pct))

                if low <= trailing_stop_price:
                    exit_price = trailing_stop_price
                    exit_reason = "trailing_stop"
                    exit_timestamp = candle_time
                    self.logger.debug(
                        "Trailing stop hit at %s: low=%.4f <= stop=%.4f (highest=%.4f)",
                        candle_time,
                        low,
                        trailing_stop_price,
                        highest_price,
                    )
                    break

                if offset == lookahead:
                    exit_price = close
                    exit_reason = "lookahead_exit"
                    exit_timestamp = candle_time
                    self.logger.debug(
                        "Lookahead exit at %s: close=%.4f",
                        candle_time,
                        close,
                    )

            ret = (exit_price - entry_price) / entry_price

            self.logger.debug(
                "Trade completed: entry=%.4f, exit=%.4f (%s at %s), return=%.2f%%",
                entry_price,
                exit_price,
                exit_reason,
                exit_timestamp,
                ret * 100,
            )

            trades.append(
                TradeRecord(
                    timestamp=current_time,
                    message=signal.message,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    return_pct=ret,
                    exit_timestamp=exit_timestamp,
                    exit_reason=exit_reason,
                )
            )

        self.logger.info("Backtest iteration completed: %d signals checked, %d signals triggered, %d trades executed",
                   signals_checked, signals_triggered, len(trades))

        # Calculate performance metrics
        if trades:
            returns = [trade.return_pct for trade in trades]
            wins = sum(1 for r in returns if r > 0)
            win_rate = wins / len(returns)
            average_return = sum(returns) / len(returns)
            cumulative_return = 1.0
            for r in returns:
                cumulative_return *= 1 + r

            # Performance logging
            self.logger.info("Performance calculation completed:")
            self.logger.info("  Total trades: %d", len(trades))
            self.logger.info("  Winning trades: %d (%.1f%%)", wins, win_rate * 100)
            self.logger.info("  Average return: %.2f%%", average_return * 100)
            self.logger.info("  Cumulative return: %.2f%%", (cumulative_return - 1) * 100)
            self.logger.info("  Best trade: %.2f%%", max(returns) * 100)
            self.logger.info("  Worst trade: %.2f%%", min(returns) * 100)
            self.logger.debug("All returns: %s", [f"{r*100:.2f}%" for r in returns])
        else:
            win_rate = 0.0
            average_return = 0.0
            cumulative_return = 1.0
            self.logger.warning("No trades were executed during the backtest")

        self.logger.debug("Returning BacktestSummary with %d trades", len(trades))
        return BacktestSummary(trades=trades, win_rate=win_rate, average_return=average_return, cumulative_return=cumulative_return)


def parse_args(args: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--strategy", default="beginner_strategy")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--lookahead", type=int, default=3)
    parser.add_argument("--take-profit", type=float, default=0.02, dest="take_profit")
    parser.add_argument("--trailing-stop", type=float, default=0.02, dest="trailing_stop")
    return parser.parse_args(args=args)


def main(cli_args: Optional[Iterable[str]] = None) -> BacktestSummary:
    backtest_logger = get_backtest_logger()
    backtest_logger.info("=== Backtest Engine Starting ===")
    args = parse_args(cli_args)

    backtest_logger.info("Command line arguments:")
    backtest_logger.info("  Symbol: %s", args.symbol)
    backtest_logger.info("  Strategy: %s", args.strategy)
    backtest_logger.info("  Limit: %d", args.limit)
    backtest_logger.info("  Lookahead: %d", args.lookahead)
    backtest_logger.info("  Take profit: %.2f%%", args.take_profit * 100)
    backtest_logger.info("  Trailing stop: %.2f%%", args.trailing_stop * 100)

    backtest_logger.debug("Loading settings from environment")
    settings = Settings.from_env()

    # Ensure required timeframes are present
    required = {"1d", "4h", "1h"}
    missing_timeframes = required - set(settings.timeframes)
    if missing_timeframes:
        backtest_logger.info("Adding missing required timeframes: %s", sorted(missing_timeframes))
        for tf in missing_timeframes:
            settings.timeframes.append(tf)

    backtest_logger.debug("Ensuring database is initialized")
    ensure_database(
        database_url=settings.database_url,
        superuser=settings.postgres_superuser,
        superuser_password=settings.postgres_superuser_password,
    )
    backtest_logger.info("Database initialized successfully")

    backtest_logger.debug("Setting up database and repository")
    database = Database(settings.database_url)
    repository = CandleRepository(database=database, exchange=settings.exchange)

    backtest_logger.debug("Setting up exchange client")
    credentials = BinanceCredentials(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
    )
    client = BinanceSpotClient(credentials=credentials)

    timeframe_map = timeframe_metadata(settings.timeframes)
    backtest_logger.debug("Timeframe metadata: %s", {tf: tf_meta.interval for tf, tf_meta in timeframe_map.items()})

    synchronizer = CandleSynchronizer(
        repository=repository,
        client=client,
        timeframe_map=timeframe_map,
    )

    backtest_logger.info("Synchronizing candles for %s from %s", args.symbol, settings.candle_start_date)
    synchronizer.sync_symbols([args.symbol], start_time=settings.candle_start_date)
    backtest_logger.info("Candle synchronization completed")

    backtest_logger.info("Initializing backtest engine")
    engine = BacktestEngine(
        settings=settings,
        strategy_name=args.strategy,
        repository=repository,
        synchronizer=synchronizer,
    )

    backtest_logger.info("Running backtest for %s", args.symbol)
    summary = engine.run(
        symbol=args.symbol,
        limit=args.limit,
        lookahead=args.lookahead,
        take_profit_pct=args.take_profit,
        trailing_stop_pct=args.trailing_stop,
    )

    # Console output
    backtest_logger.info("=== Backtest Results ===")
    for trade in summary.trades:
        print(
            f"{trade.timestamp} -> {trade.exit_timestamp} | {trade.return_pct:.2%} "
            f"| {trade.exit_reason} | {trade.message}"
        )

    # Summary output
    print(
        "Summary: trades=%d, win_rate=%.2f, avg_return=%.2f%%, cumulative=%.2f%%"
        % (
            len(summary.trades),
            summary.win_rate,
            summary.average_return * 100,
            (summary.cumulative_return - 1) * 100,
        )
    )

    backtest_logger.info("=== Backtest Completed ===")
    backtest_logger.info("Final results: %d trades, %.1f%% win rate, %.2f%% average return, %.2f%% cumulative return",
               len(summary.trades), summary.win_rate * 100, summary.average_return * 100, (summary.cumulative_return - 1) * 100)

    return summary


if __name__ == "__main__":
    main()

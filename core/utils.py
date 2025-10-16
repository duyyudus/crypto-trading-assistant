"""Utility helpers for the trading assistant."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional

from dotenv import load_dotenv
from dateutil import parser as date_parser

# Configure logging early so that modules importing helpers inherit defaults.
load_dotenv(".env")

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(os.getenv("LOG_DIR", ".log"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "trading_assistant.log"

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
stream_handler = logging.StreamHandler()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[file_handler, stream_handler],
)
logger = logging.getLogger("crypto_trading_assistant")


def get_backtest_logger() -> logging.Logger:
    """Create and return a dedicated logger for backtest operations with timestamped log files."""
    backtest_logger = logging.getLogger("crypto_trading_assistant.backtest")

    # Clear any existing handlers to ensure fresh configuration
    backtest_logger.handlers.clear()

    # Create timestamped log file for this specific backtest run
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backtest_log_file = LOG_DIR / f"backtest_{timestamp}.log"

    # Create file handler for backtest-specific logs (overwrite mode for fresh start)
    file_handler = logging.FileHandler(backtest_log_file, encoding="utf-8", mode="w")
    file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Create console handler for backtest output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Set format to distinguish from main logs
    formatter = logging.Formatter("%(asctime)s | BACKTEST | %(levelname)s | %(name)s | %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    backtest_logger.addHandler(file_handler)
    backtest_logger.addHandler(console_handler)
    backtest_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Prevent propagation to root logger to avoid duplicate messages
    backtest_logger.propagate = False

    # Log the new log file location
    backtest_logger.info("Backtest log file created: %s", backtest_log_file)

    return backtest_logger


def cleanup_old_backtest_logs(keep_days: int = 7) -> int:
    """Remove old backtest log files older than the specified number of days.

    Args:
        keep_days: Number of days to keep log files (default: 7)

    Returns:
        Number of files deleted
    """
    from datetime import datetime, timedelta

    cutoff_date = datetime.now() - timedelta(days=keep_days)
    deleted_count = 0

    for log_file in LOG_DIR.glob("backtest_*.log"):
        try:
            # Extract timestamp from filename like "backtest_20251016_144549.log"
            timestamp_str = log_file.stem.replace("backtest_", "")
            file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

            if file_date < cutoff_date:
                log_file.unlink()
                deleted_count += 1
        except (ValueError, OSError):
            # Skip files that don't match the expected format or can't be deleted
            continue

    return deleted_count


@dataclass(slots=True)
class ExchangeTimeframe:
    """Container describing timeframe metadata used across the project."""

    name: str
    interval: str
    lookback: int
    refresh_minutes: int


DEFAULT_TIMEFRAMES: Mapping[str, ExchangeTimeframe] = {
    "5m": ExchangeTimeframe("5m", "5m", 100, 5),
    "15m": ExchangeTimeframe("15m", "15m", 100, 15),
    "30m": ExchangeTimeframe("30m", "30m", 100, 30),
    "1h": ExchangeTimeframe("1h", "1h", 100, 60),
    "4h": ExchangeTimeframe("4h", "4h", 60, 4 * 60),
    "1d": ExchangeTimeframe("1d", "1d", 50, 24 * 60),
}


@dataclass(slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    exchange: str = "binance_spot"
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    alert_bot: str = "telegram"
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframes: List[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    check_interval_minutes: int = 5
    strategy: str = "beginner_strategy"
    database_url: str = ""
    postgres_superuser: Optional[str] = None
    postgres_superuser_password: Optional[str] = None
    log_level: str = LOG_LEVEL
    log_dir: Path = LOG_DIR
    candle_start_date: datetime = datetime(2017, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_env(cls, env_file: Optional[str | os.PathLike[str]] = ".env") -> "Settings":
        """Load settings from environment variables, defaulting to ``.env``."""

        if env_file:
            load_dotenv(env_file)  # type: ignore[arg-type]

        def _split_list(value: Optional[str]) -> List[str]:
            if not value:
                return []
            return [item.strip() for item in value.split(",") if item.strip()]

        start_date_raw = os.getenv("CANDLE_SYNC_START_DATE", "2017-01-01")
        try:
            parsed_start = date_parser.parse(start_date_raw)
            if parsed_start.tzinfo is None:
                parsed_start = parsed_start.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid CANDLE_SYNC_START_DATE: {start_date_raw}") from exc

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL must be set in environment")

        return cls(
            exchange=os.getenv("EXCHANGE", "binance_spot"),
            binance_api_key=os.getenv("BINANCE_API_KEY"),
            binance_api_secret=os.getenv("BINANCE_API_SECRET"),
            alert_bot=os.getenv("ALERT_BOT", "telegram"),
            telegram_token=os.getenv("TELEGRAM_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            symbols=_split_list(os.getenv("SYMBOLS")) or ["BTCUSDT", "ETHUSDT"],
            timeframes=_split_list(os.getenv("TIMEFRAMES")) or ["1d", "4h", "1h"],
            check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "5")),
            strategy=os.getenv("STRATEGY", "beginner_strategy"),
            database_url=database_url,
            postgres_superuser=os.getenv("POSTGRES_SUPERUSER"),
            postgres_superuser_password=os.getenv("POSTGRES_SUPERUSER_PASSWORD"),
            log_level=LOG_LEVEL,
            log_dir=LOG_DIR,
            candle_start_date=parsed_start,
        )


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def load_json(path: Path) -> MutableMapping[str, object]:
    """Load a JSON file if it exists, returning an empty dict otherwise."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Mapping[str, object]) -> None:
    """Persist ``payload`` into ``path`` with pretty formatting."""

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def chunked(iterable: Iterable, size: int) -> Iterable[List]:
    """Yield chunks from ``iterable`` with a maximum size of ``size``."""

    chunk: List = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def timeframe_metadata(timeframes: Iterable[str]) -> Dict[str, ExchangeTimeframe]:
    """Return metadata for timeframes using defaults when available."""

    metadata: Dict[str, ExchangeTimeframe] = {}
    for tf in timeframes:
        tf_lower = tf.lower()
        metadata[tf_lower] = DEFAULT_TIMEFRAMES.get(
            tf_lower, ExchangeTimeframe(tf_lower, tf_lower, 200, 60)
        )
    return metadata

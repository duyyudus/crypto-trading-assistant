# Crypto Trading Assistant

A modular Python project that monitors crypto markets using configurable strategies and sends Telegram alerts when entry signals appear. The system focuses on data collection, signal detection, and human-readable notifications rather than automated trade execution.

## Features

- Binance Spot OHLCV data retrieval with configurable symbols and timeframes.
- PostgreSQL-backed candle warehouse managed through Alembic migrations.
- Extensible candle synchronization tool with historic backfill, incremental updates, and pagination awareness.
- Indicator utilities powered by `pandas`/`pandas-ta` for EMA, RSI, and trend checks.
- Strategy plug-in architecture with a sample multi-timeframe **Beginner Strategy**.
- Telegram alert module for human-readable signal delivery.
- Lightweight scheduling loop for continuous monitoring that keeps the candle warehouse fresh.
- Historical backtest runner that reads from the shared PostgreSQL dataset.

## Project Structure

```
core/
  exchanges/binance.py    # Binance Spot REST client
  data_fetcher.py         # Multi-timeframe data retrieval backed by PostgreSQL
  indicators.py           # Indicator helpers used by strategies
  utils.py                # Config, logging, and generic helpers
  database.py             # SQLAlchemy engine/session helpers
  models.py               # ORM models (Candles)
  candles/                # Candle repository + synchronizer
strategies/
  base_strategy.py        # Strategy base definitions
  beginner_strategy.py    # Default multi-timeframe example strategy
alert/
  telegram_bot.py         # Telegram alert sender
backtest/
  backtest_engine.py      # Historical backtesting CLI
  visualize.py            # Equity curve plotting helper
main.py                   # Live monitoring entry point
tools/
  candle_sync.py          # CLI to backfill & continuously sync candles
```

## Getting Started

### 1. Install dependencies

The project expects Python 3.10+. Use your preferred virtual environment manager (e.g., `uv`, `venv`, or `conda`) and install dependencies:

```bash
uv pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file at the repository root (see `.env.example`) with your Binance and Telegram credentials, database settings, and runtime configuration:

```
EXCHANGE=binance_spot
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
ALERT_BOT=telegram
TELEGRAM_TOKEN=telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SYMBOLS=BTCUSDT,ETHUSDT
TIMEFRAMES=1d,4h,1h
CHECK_INTERVAL_MINUTES=5
STRATEGY=beginner_strategy

# PostgreSQL configuration
DATABASE_URL=postgresql://trading_assistant:strong_password@localhost:5432/trading_assistant
POSTGRES_SUPERUSER=postgres
POSTGRES_SUPERUSER_PASSWORD=postgres_password
CANDLE_SYNC_START_DATE=2017-01-01

# Logging
LOG_LEVEL=INFO
LOG_DIR=.log
```

> **Security tip:** Always use read-only API keys when backtesting or monitoring markets.

### 3. Migrate the database

Run Alembic migrations to provision the candle schema. This will create the `candles` table used across backtests and live monitoring.

```bash
alembic upgrade head
```

### 4. Backfill & keep candles fresh

Use the candle synchronization tool to fetch historical data and keep it current. The command below pulls data starting from 1 January 2017 for the symbols and timeframes configured in `.env`, then continues polling based on each timeframe's duration.

```bash
python tools/candle_sync.py
```

To run a single backfill pass and exit (no continuous updates), append `--once`. Override symbols, timeframes, or start date via CLI flags, e.g. `--symbols BTCUSDT,ETHUSDT --timeframes 1h,15m --start-date 2020-01-01`.

### 5. Run live monitoring

```bash
python main.py
```

Run a single monitoring cycle without entering the persistent loop:

```bash
python main.py --once
```

### 6. Backtesting

Execute the backtesting engine for a symbol and strategy. The engine reads from the shared PostgreSQL candle database; ensure the required history has been synchronized beforehand.

```bash
python backtest/backtest_engine.py --symbol BTCUSDT --strategy beginner_strategy --limit 750 --lookahead 3
```

To visualize equity curves, run the backtest and pass the result into `backtest.visualize.plot_equity_curve` from a Python session.

## Beginner Strategy Overview

1. **Daily trend filter (1D)** – Close price must be above the 50-period EMA.
2. **Momentum confirmation (4H)** – RSI(14) above 55 and the 20-period EMA trending upward.
3. **Entry timing (1H)** – Latest candle closes above the most recent swing high (10-candle lookback) and performs a successful retest within the same candle.

All conditions must align to emit an "Entry-Ready" signal. Alerts include per-timeframe condition diagnostics to help traders validate the setup.

## Data & Rate Limit Notes

- The synchronizer paginates requests (1000 candles per page) and resumes from the latest stored candle to avoid duplicate work.
- Each timeframe schedules its own refresh cadence (e.g., hourly for `1h`, every four hours for `4h`).
- Respect Binance rate limits (≤1200 requests/min). The synchronizer reuses the lightweight REST client shared with live monitoring.

## Logging

Logs now stream to both stdout and `.log/trading_assistant.log`. Adjust `LOG_LEVEL` or `LOG_DIR` in `.env` to customize verbosity and destination.

## Future Enhancements

- Additional exchanges and alert destinations.
- Richer strategy examples, including exit logic and risk management.
- Streamlit dashboards or notebooks for signal exploration.
- Automated database provisioning for alternative cloud PostgreSQL providers.

## License

This project is provided as-is for educational and research use. Always validate strategies thoroughly before risking capital.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a crypto trading assistant that monitors markets using configurable strategies and sends Telegram alerts for entry signals. The system focuses on data collection, signal detection, and human-readable notifications rather than automated trade execution.

## Common Development Commands

Always source venv first before running python and related tools: `source .venv/bin/activate`

### Environment Setup
```bash
# Install dependencies (Python 3.10+ required)
uv pip install -r requirements.txt
# Or with regular pip:
pip install -r requirements.txt
```

### Running the System
```bash
# Run continuous monitoring loop
python main.py

# Run single monitoring cycle (useful for testing)
python main.py --once
```

### Backtesting
```bash
# Basic backtest with default settings
source .venv/bin/activate
python backtest/backtest_engine.py --symbol BTCUSDT --strategy beginner_strategy --limit 750 --lookahead 3

# Backtest with custom parameters
python backtest/backtest_engine.py --symbol ETHUSDT --strategy beginner_strategy --limit 1000 --lookahead 5

# Backtest with detailed DEBUG logging
LOG_LEVEL=DEBUG python backtest/backtest_engine.py --symbol BTCUSDT --strategy beginner_strategy --limit 200 --lookahead 3
```

### Backtest Logging
The backtest engine uses a dedicated logging system separate from the main application:

- **Log Files**: Each backtest run creates a fresh timestamped log file (e.g., `backtest_20251016_144549.log`)
- **Console Output**: All backtest logs appear in console with `BACKTEST` prefix
- **Log Levels**: Use `LOG_LEVEL=DEBUG` for maximum granularity
- **Clean Logs**: Each run starts with a completely new log file - no mixing with old logs

#### Log File Locations
- Main application logs: `.log/trading_assistant.log`
- Backtest-specific logs: `.log/backtest_YYYYMMDD_HHMMSS.log` (timestamped per run)
- Legacy backtest logs: `.log/backtest.log` (older format)

#### Log Cleanup
Clean up old backtest log files to save disk space:

```bash
# Clean up logs older than 7 days (default)
source .venv/bin/activate
python tools/cleanup_logs.py

# Clean up logs older than 30 days
python tools/cleanup_logs.py --days 30

# Clean up all backtest logs (use with caution)
python tools/cleanup_logs.py --days 0
```

### Visualization
```python
# In a Python REPL, after running a backtest:
from backtest.visualize import plot_equity_curve
import pandas as pd
# Load your backtest results and call:
# plot_equity_curve(your_dataframe)
```

## Architecture Overview

### Core Components
- **main.py**: Entry point for live monitoring, orchestrates the monitoring loop
- **core/**: Shared infrastructure including exchange clients, the PostgreSQL candle layer, indicators, and utilities
- **strategies/**: Plugin architecture for trading strategies with base classes and examples
- **backtest/**: Historical testing engine with visualization helpers
- **alert/**: Alert delivery systems (currently Telegram)

### Key Data Flow
1. **CandleSynchronizer** streams OHLCV data from Binance into PostgreSQL across multiple timeframes
2. **MarketDataFetcher** loads candles from the database for strategy evaluation
3. **Strategy** implementations analyze multi-timeframe data and generate signals
4. **TelegramBot** delivers human-readable alerts when signals trigger

### Strategy Architecture
- All strategies inherit from `BaseStrategy` (strategies/base_strategy.py)
- Strategies receive `StrategyContext` containing symbol and multi-timeframe candle data
- Must implement `check_signal()` method returning `StrategySignal`
- Strategies are loaded dynamically via `strategies.load_strategy()`

### Configuration System
- Runtime settings loaded from environment variables via `.env` file
- Core settings defined in `core/utils.py:Settings` dataclass
- Default timeframes and metadata in `DEFAULT_TIMEFRAMES` mapping
- Uses python-dotenv for environment variable management

### Data Management
- Candles persisted in PostgreSQL via SQLAlchemy models (`core/models.py`)
- Synchronizer paginates Binance requests (≤1000 candles per call) and resumes from the latest stored candle
- Each timeframe has configurable lookback periods for indicator stability
- Data includes OHLCV plus timestamp, volume, and trade count metrics

### Multi-Timeframe Strategy Pattern
The beginner strategy demonstrates the project's multi-timeframe approach:
1. **Daily trend filter** (1D): Price above 50-period EMA
2. **Momentum confirmation** (4H): RSI(14) > 55, EMA trending up
3. **Entry timing** (1H): Close above swing high with retest

### Database Setup
```bash
# Run Alembic migrations to create the candle schema
alembic upgrade head
```

### Candle Synchronization
```bash
# Sync candles for configured symbols/timeframes with continuous updates
python tools/candle_sync.py

# Run single sync pass and exit (no continuous updates)
python tools/candle_sync.py --once

# Override configuration via CLI flags
python tools/candle_sync.py --symbols BTCUSDT,ETHUSDT --timeframes 1h,15m --start-date 2020-01-01
```

## Development Notes

### Adding New Strategies
1. Create new strategy file in `strategies/` directory
2. Inherit from `BaseStrategy` and implement `check_signal()`
3. Export strategy class in the module
4. Update `STRATEGY` environment variable to use new strategy

### Exchange Integration
- Currently supports Binance Spot via REST API
- Exchange abstraction in `core/exchanges/` with credentials management
- Rate limiting handled automatically with small delays between requests
- Supports up to 1000 candles per API request (Binance limit)

### Testing Approach
- No automated test suite currently
- Use backtesting as regression testing for strategy changes
- Single-cycle execution (`--once`) for quick validation
- Include sample command lines in PRs for verification

### Security Considerations
- API keys should be read-only for monitoring/backtesting
- All secrets belong in `.env` file (never committed)
- PostgreSQL credentials should match least-privilege database roles; superuser credentials are used only for bootstrap
- Consider using different API keys for development vs production

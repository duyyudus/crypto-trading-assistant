# Repository Guidelines

## Project Structure & Module Organization
- `main.py` orchestrates the live monitoring loop; run `python main.py --once` for fast smoke checks.
- Shared plumbing (exchange clients, caching, indicators, logging utilities) lives in `core/`; keep cross-module imports minimal and well-documented.
- Strategies reside under `strategies/` (`base_strategy.py`, `beginner_strategy.py`); export new strategies via `strategies/__init__.py`.
- Offline tooling lives in `backtest/` (`backtest_engine.py`, `visualize.py`) and should mirror live execution.
- Alerts are implemented in `alert/` with `telegram_bot.py` as the current backend; add siblings and expose factories in `alert/__init__.py`.
- Place future unit tests in `tests/` to keep regression workflows predictable.

## Build, Test, and Development Commands
- `uv pip install -r requirements.txt` (or `pip install ...`) installs Python 3.10+ dependencies.
- `python main.py` runs continuous monitoring; append `--once` for a single iteration without scheduling.
- `python backtest/backtest_engine.py --symbol BTCUSDT --strategy beginner_strategy --limit 750 --lookahead 3` performs a deterministic backtest for regression checks.
- `python -m backtest.visualize` renders equity curves from a stored DataFrame when iterating on indicators.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and snake_case modules, functions, and variables.
- Provide type hints for new public APIs; prefer dataclasses for lightweight containers (`core/data_fetcher.py`).
- Reuse `logger` from `core.utils` over `print` statements and document non-trivial imports.

## Testing Guidelines
- No automated suite exists yet; rely on repeatable backtest runs as smoke and regression tests.
- Add deterministic unit tests under `tests/` using `pytest` for pure helpers or strategy signal builders.
- Keep fixture data cached (CSV/Parquet) and note sources in test docstrings to avoid live API calls.

## Commit & Pull Request Guidelines
- Write present-tense imperative commit messages (e.g., `Add RSI filter`) and group related changes.
- Pull requests should include a concise problem/solution summary, verification steps (e.g., backtest commands), configuration diffs, and screenshots for alert payload changes.
- Link tracked issues with `Fixes #<id>` where applicable and highlight any cache purges separately from logic edits.

## Security & Configuration Tips
- Store secrets in `.env` at the repo root; never commit API keys or Telegram tokens.
- Favor read-only Binance credentials, unique chat IDs, and limited write scopes when integrating new exchanges.
- Clear stale data with `rm -rf .data_cache/` only when debugging cache issues, and avoid bundling purges with behavioral changes.

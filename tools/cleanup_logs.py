#!/usr/bin/env python3
"""Utility script to clean up old backtest log files."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.utils import cleanup_old_backtest_logs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean up old backtest log files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--days", type=int, default=7, help="Number of days to keep logs (default: 7)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print(f"DRY RUN: Would delete backtest logs older than {args.days} days")
        # TODO: Implement dry run functionality if needed
        print("Dry run not implemented yet. Run without --dry-run to actually clean up logs.")
        return

    deleted_count = cleanup_old_backtest_logs(keep_days=args.days)

    if deleted_count > 0:
        print(f"✅ Cleaned up {deleted_count} old backtest log files (older than {args.days} days)")
    else:
        print(f"✨ No old backtest log files to clean up (all logs are newer than {args.days} days)")


if __name__ == "__main__":
    main()
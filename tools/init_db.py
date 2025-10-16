#!/usr/bin/env python3
"""Initialize database tables for the crypto trading assistant.

This script creates the database and user if they don't exist, then runs
Alembic migrations to create the necessary tables.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add the project root directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic.config import Config
from alembic import command
from core.database import ensure_database
from core.utils import Settings, logger


def init_database() -> None:
    """Initialize the database and create tables.

    This function:
    1. Loads settings from environment variables
    2. Ensures the database and user exist
    3. Runs Alembic migrations to create tables
    """
    try:
        # Load settings from environment
        logger.info("Loading settings from environment...")
        settings = Settings.from_env()

        # Ensure database and user exist
        logger.info("Ensuring database and user exist...")
        ensure_database(
            database_url=settings.database_url,
            superuser=settings.postgres_superuser,
            superuser_password=settings.postgres_superuser_password,
        )

        # Run Alembic migrations
        logger.info("Running database migrations...")
        alembic_cfg = Config("alembic.ini")

        # Check if migrations are already at head
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.database_url)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

        # Load head revision from alembic
        from alembic.script import ScriptDirectory
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script_dir.get_current_head()

        if current_rev == head_rev:
            logger.info("Migrations are already at head. Verifying tables exist...")
            # Verify that tables actually exist by checking the candles table
            try:
                with engine.connect() as connection:
                    result = connection.execute(
                        text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'candles'")
                    ).scalar()
                    if result == 0:
                        logger.warning("Migration marked as applied but candles table missing. Re-running migration...")
                        command.stamp(alembic_cfg, "base")
                        command.upgrade(alembic_cfg, "head")
                    else:
                        logger.info("Tables verified successfully")
            except Exception as e:
                logger.warning("Could not verify tables: %s. Re-running migration...", e)
                command.stamp(alembic_cfg, "base")
                command.upgrade(alembic_cfg, "head")
        else:
            command.upgrade(alembic_cfg, "head")

        logger.info("Database initialization completed successfully!")

    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise


def main() -> None:
    """Main entry point for the script."""
    logger.info("Starting database initialization...")
    init_database()
    logger.info("Database is ready for use!")


if __name__ == "__main__":
    main()
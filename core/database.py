"""Database utilities for the trading assistant."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .utils import logger


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def quote_ident(value: str) -> str:
    """Return ``value`` quoted for safe usage as a PostgreSQL identifier."""

    return f'"{value.replace("\"", "\"\"")}"'


class Database:
    """Lightweight wrapper around an SQLAlchemy engine and session factory."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.engine: Engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def ensure_database(
    database_url: str,
    superuser: Optional[str],
    superuser_password: Optional[str],
) -> None:
    """Ensure that the database and user referenced by ``database_url`` exist."""

    if not database_url:
        raise ValueError("DATABASE_URL must be provided")

    if not superuser or not superuser_password:
        logger.debug("Skipping database bootstrap; superuser credentials missing")
        return

    url = make_url(database_url)
    database_name = url.database
    app_user = url.username
    app_password = url.password or ""

    if not database_name:
        logger.debug("Skipping database bootstrap; database name missing from URL")
        return

    admin_url = URL.create(
        drivername=url.drivername,
        username=superuser,
        password=superuser_password,
        host=url.host,
        port=url.port,
        database="postgres",
    )

    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            if app_user:
                result = connection.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                    {"name": app_user},
                ).scalar()
                if result is None:
                    logger.info("Creating PostgreSQL role %s", app_user)
                    connection.execute(
                        text(f"CREATE USER {quote_ident(app_user)} WITH PASSWORD :password"),
                        {"password": app_password},
                    )
                else:
                    connection.execute(
                        text(f"ALTER USER {quote_ident(app_user)} WITH PASSWORD :password"),
                        {"password": app_password},
                    )

            result = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            ).scalar()
            if result is None:
                owner_clause = f" OWNER {quote_ident(app_user)}" if app_user else ""
                logger.info("Creating PostgreSQL database %s", database_name)
                connection.execute(
                    text(f"CREATE DATABASE {quote_ident(database_name)}{owner_clause}"),
                )
    except SQLAlchemyError as exc:
        logger.warning("Database bootstrap failed: %s", exc)
    finally:
        admin_engine.dispose()

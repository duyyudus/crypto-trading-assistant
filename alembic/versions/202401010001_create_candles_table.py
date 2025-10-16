"""Create candles table

Revision ID: 202401010001
Revises: 
Create Date: 2024-01-01 00:01:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202401010001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("exchange", sa.String(length=50), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), primary_key=True, nullable=False),
        sa.Column("timeframe", sa.String(length=10), primary_key=True, nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("quote_asset_volume", sa.Float(), nullable=True),
        sa.Column("number_of_trades", sa.Integer(), nullable=True),
        sa.Column("taker_buy_base", sa.Float(), nullable=True),
        sa.Column("taker_buy_quote", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_candles_symbol_timeframe_open_time",
        "candles",
        ["symbol", "timeframe", "open_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_candles_symbol_timeframe_open_time", table_name="candles")
    op.drop_table("candles")

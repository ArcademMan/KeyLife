"""per-application tracking + settings store

Revision ID: 0002_per_app_tracking
Revises: 0001_initial
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_per_app_tracking"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_app_counts",
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("exe_name", sa.String(length=260), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("date", "exe_name", name="pk_daily_app_counts"),
    )
    op.create_table(
        "hourly_app_totals",
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("exe_name", sa.String(length=260), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "date", "hour", "exe_name", name="pk_hourly_app_totals"
        ),
    )
    op.create_table(
        "app_icons",
        sa.Column("exe_name", sa.String(length=260), primary_key=True),
        sa.Column("png", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("app_icons")
    op.drop_table("hourly_app_totals")
    op.drop_table("daily_app_counts")

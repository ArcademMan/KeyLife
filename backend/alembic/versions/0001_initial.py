"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-27

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_key_counts",
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("vk", sa.Integer(), nullable=False),
        sa.Column("scancode", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("date", "vk", "scancode", name="pk_daily_key_counts"),
    )
    op.create_table(
        "hourly_totals",
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("date", "hour", name="pk_hourly_totals"),
    )


def downgrade() -> None:
    op.drop_table("hourly_totals")
    op.drop_table("daily_key_counts")

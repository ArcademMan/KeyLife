from __future__ import annotations

from sqlalchemy import Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyKeyCount(Base):
    """Per-key daily aggregate.

    Granularity is intentionally coarse (date + vk + scancode -> count).
    No timestamps, no order, no co-occurrence — a single keystroke is
    statistically indistinguishable inside a day's bucket.
    """

    __tablename__ = "daily_key_counts"

    date: Mapped[str] = mapped_column(String(10))  # ISO date YYYY-MM-DD
    vk: Mapped[int] = mapped_column(Integer)
    scancode: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("date", "vk", "scancode", name="pk_daily_key_counts"),
    )


class HourlyTotal(Base):
    """Per-hour total presses, no per-key breakdown.

    Used for temporal usage patterns; cannot leak which key was pressed.
    """

    __tablename__ = "hourly_totals"

    date: Mapped[str] = mapped_column(String(10))  # ISO date YYYY-MM-DD
    hour: Mapped[int] = mapped_column(Integer)     # 0..23
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("date", "hour", name="pk_hourly_totals"),
    )

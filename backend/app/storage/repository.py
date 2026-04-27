from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date as _date

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.storage.models import DailyKeyCount, HourlyTotal


def upsert_daily_key_counts(
    session: Session,
    rows: Iterable[tuple[str, int, int, int]],
) -> int:
    """UPSERT (date, vk, scancode, count). count is added to existing.

    Returns the number of rows submitted.
    """
    payload = [
        {"date": d, "vk": vk, "scancode": sc, "count": cnt}
        for d, vk, sc, cnt in rows
        if cnt > 0
    ]
    if not payload:
        return 0
    stmt = sqlite_insert(DailyKeyCount).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DailyKeyCount.date, DailyKeyCount.vk, DailyKeyCount.scancode],
        set_={"count": DailyKeyCount.count + stmt.excluded.count},
    )
    session.execute(stmt)
    return len(payload)


def upsert_hourly_totals(
    session: Session,
    rows: Iterable[tuple[str, int, int]],
) -> int:
    payload = [
        {"date": d, "hour": h, "total": t}
        for d, h, t in rows
        if t > 0
    ]
    if not payload:
        return 0
    stmt = sqlite_insert(HourlyTotal).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[HourlyTotal.date, HourlyTotal.hour],
        set_={"total": HourlyTotal.total + stmt.excluded.total},
    )
    session.execute(stmt)
    return len(payload)


def flush_snapshot(
    session: Session,
    per_key: Mapping[tuple[str, int, int], int],
    per_hour: Mapping[tuple[str, int], int],
) -> tuple[int, int]:
    n_keys = upsert_daily_key_counts(
        session, ((d, vk, sc, c) for (d, vk, sc), c in per_key.items())
    )
    n_hours = upsert_hourly_totals(
        session, ((d, h, t) for (d, h), t in per_hour.items())
    )
    session.commit()
    return n_keys, n_hours


def today_total(session: Session, today: str | None = None) -> int:
    iso = today or _date.today().isoformat()
    stmt = select(func.coalesce(func.sum(DailyKeyCount.count), 0)).where(
        DailyKeyCount.date == iso
    )
    return int(session.execute(stmt).scalar_one())


def all_time_total(session: Session) -> int:
    stmt = select(func.coalesce(func.sum(DailyKeyCount.count), 0))
    return int(session.execute(stmt).scalar_one())


def top_keys_today(
    session: Session, limit: int = 5, today: str | None = None,
) -> list[tuple[int, int, int]]:
    iso = today or _date.today().isoformat()
    stmt = (
        select(DailyKeyCount.vk, DailyKeyCount.scancode, DailyKeyCount.count)
        .where(DailyKeyCount.date == iso)
        .order_by(DailyKeyCount.count.desc())
        .limit(limit)
    )
    return [(int(vk), int(sc), int(c)) for vk, sc, c in session.execute(stmt).all()]


def top_keys_range(
    session: Session, start: str, end: str, limit: int = 20,
) -> list[tuple[int, int, int]]:
    sum_count = func.sum(DailyKeyCount.count).label("c")
    stmt = (
        select(DailyKeyCount.vk, DailyKeyCount.scancode, sum_count)
        .where(DailyKeyCount.date >= start, DailyKeyCount.date <= end)
        .group_by(DailyKeyCount.vk, DailyKeyCount.scancode)
        .order_by(sum_count.desc())
        .limit(limit)
    )
    return [(int(vk), int(sc), int(c)) for vk, sc, c in session.execute(stmt).all()]


def keys_in_range(
    session: Session, start: str, end: str,
) -> list[tuple[int, int, int]]:
    """All (vk, scancode, total_count) over the [start, end] inclusive window."""
    sum_count = func.sum(DailyKeyCount.count).label("c")
    stmt = (
        select(DailyKeyCount.vk, DailyKeyCount.scancode, sum_count)
        .where(DailyKeyCount.date >= start, DailyKeyCount.date <= end)
        .group_by(DailyKeyCount.vk, DailyKeyCount.scancode)
    )
    return [(int(vk), int(sc), int(c)) for vk, sc, c in session.execute(stmt).all()]


def daily_totals_range(
    session: Session, start: str, end: str,
) -> list[tuple[str, int]]:
    """Total presses per day across [start, end] inclusive. Sparse: missing days omitted."""
    sum_count = func.sum(DailyKeyCount.count).label("c")
    stmt = (
        select(DailyKeyCount.date, sum_count)
        .where(DailyKeyCount.date >= start, DailyKeyCount.date <= end)
        .group_by(DailyKeyCount.date)
        .order_by(DailyKeyCount.date)
    )
    return [(str(d), int(c)) for d, c in session.execute(stmt).all()]


def hourly_matrix_range(
    session: Session, start: str, end: str,
) -> list[tuple[str, int, int]]:
    """(date, hour, total) rows in [start, end] inclusive. Sparse."""
    stmt = (
        select(HourlyTotal.date, HourlyTotal.hour, HourlyTotal.total)
        .where(HourlyTotal.date >= start, HourlyTotal.date <= end)
        .order_by(HourlyTotal.date, HourlyTotal.hour)
    )
    return [(str(d), int(h), int(t)) for d, h, t in session.execute(stmt).all()]


def all_time_total_and_first_date(session: Session) -> tuple[int, str | None]:
    total_stmt = select(func.coalesce(func.sum(DailyKeyCount.count), 0))
    min_stmt = select(func.min(DailyKeyCount.date))
    total = int(session.execute(total_stmt).scalar_one())
    first = session.execute(min_stmt).scalar_one()
    return total, (str(first) if first else None)

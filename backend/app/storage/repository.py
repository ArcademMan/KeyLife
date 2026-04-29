from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date as _date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.storage.models import (
    AppIcon,
    AppSetting,
    DailyAppCount,
    DailyKeyCount,
    HourlyAppTotal,
    HourlyTotal,
)


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


def upsert_daily_app_counts(
    session: Session,
    rows: Iterable[tuple[str, str, int]],
) -> int:
    payload = [
        {"date": d, "exe_name": exe, "count": cnt}
        for d, exe, cnt in rows
        if cnt > 0 and exe
    ]
    if not payload:
        return 0
    stmt = sqlite_insert(DailyAppCount).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DailyAppCount.date, DailyAppCount.exe_name],
        set_={"count": DailyAppCount.count + stmt.excluded.count},
    )
    session.execute(stmt)
    return len(payload)


def upsert_hourly_app_totals(
    session: Session,
    rows: Iterable[tuple[str, int, str, int]],
) -> int:
    payload = [
        {"date": d, "hour": h, "exe_name": exe, "count": cnt}
        for d, h, exe, cnt in rows
        if cnt > 0 and exe
    ]
    if not payload:
        return 0
    stmt = sqlite_insert(HourlyAppTotal).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=[HourlyAppTotal.date, HourlyAppTotal.hour, HourlyAppTotal.exe_name],
        set_={"count": HourlyAppTotal.count + stmt.excluded.count},
    )
    session.execute(stmt)
    return len(payload)


def flush_snapshot(
    session: Session,
    per_key: Mapping[tuple[str, int, int], int],
    per_hour: Mapping[tuple[str, int], int],
    per_app_daily: Mapping[tuple[str, str], int] | None = None,
    per_app_hourly: Mapping[tuple[str, int, str], int] | None = None,
) -> tuple[int, int, int, int]:
    """Flush a single atomic snapshot to the DB.

    Returns (n_keys, n_hours, n_app_daily, n_app_hourly) — number of rows
    submitted to each table. Per-app args are optional: when the feature
    is OFF the aggregator passes None and we skip those tables entirely
    (zero overhead vs. the original two-table flush).
    """
    n_keys = upsert_daily_key_counts(
        session, ((d, vk, sc, c) for (d, vk, sc), c in per_key.items())
    )
    n_hours = upsert_hourly_totals(
        session, ((d, h, t) for (d, h), t in per_hour.items())
    )
    n_app_daily = 0
    n_app_hourly = 0
    if per_app_daily:
        n_app_daily = upsert_daily_app_counts(
            session, ((d, exe, c) for (d, exe), c in per_app_daily.items())
        )
    if per_app_hourly:
        n_app_hourly = upsert_hourly_app_totals(
            session, ((d, h, exe, c) for (d, h, exe), c in per_app_hourly.items())
        )
    session.commit()
    return n_keys, n_hours, n_app_daily, n_app_hourly


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


# ---- Per-application queries --------------------------------------------

def apps_summary_range(
    session: Session, start: str, end: str, limit: int = 50,
) -> list[tuple[str, int]]:
    """(exe_name, total_count) over [start, end] inclusive, top N first."""
    sum_count = func.sum(DailyAppCount.count).label("c")
    stmt = (
        select(DailyAppCount.exe_name, sum_count)
        .where(DailyAppCount.date >= start, DailyAppCount.date <= end)
        .group_by(DailyAppCount.exe_name)
        .order_by(sum_count.desc())
        .limit(limit)
    )
    return [(str(exe), int(c)) for exe, c in session.execute(stmt).all()]


def apps_hourly_range(
    session: Session, start: str, end: str, exe_name: str | None = None,
) -> list[tuple[str, int, str, int]]:
    """(date, hour, exe_name, count) over the window.

    If `exe_name` is given, restrict to that app: useful for a per-app
    hourly heatmap. Otherwise return everything (caller pivots).
    """
    stmt = (
        select(
            HourlyAppTotal.date,
            HourlyAppTotal.hour,
            HourlyAppTotal.exe_name,
            HourlyAppTotal.count,
        )
        .where(HourlyAppTotal.date >= start, HourlyAppTotal.date <= end)
        .order_by(HourlyAppTotal.date, HourlyAppTotal.hour)
    )
    if exe_name is not None:
        stmt = stmt.where(HourlyAppTotal.exe_name == exe_name)
    return [
        (str(d), int(h), str(exe), int(c))
        for d, h, exe, c in session.execute(stmt).all()
    ]


def known_exe_names(session: Session) -> list[str]:
    """Distinct exe names ever recorded. Useful for the Settings UI."""
    stmt = select(DailyAppCount.exe_name).distinct().order_by(DailyAppCount.exe_name)
    return [str(x) for (x,) in session.execute(stmt).all()]


def forget_app(session: Session, exe_name: str) -> int:
    """Cancella ogni traccia di `exe_name`: conteggi (daily + hourly) e icona.

    Le `app_settings.blocklist` non sono toccate (è una preferenza utente,
    non un dato). Restituisce il numero totale di righe rimosse.
    """
    n = 0
    n += session.execute(
        delete(DailyAppCount).where(DailyAppCount.exe_name == exe_name)
    ).rowcount or 0
    n += session.execute(
        delete(HourlyAppTotal).where(HourlyAppTotal.exe_name == exe_name)
    ).rowcount or 0
    n += session.execute(
        delete(AppIcon).where(AppIcon.exe_name == exe_name)
    ).rowcount or 0
    session.commit()
    return n


# ---- App icons ----------------------------------------------------------

def set_app_icon(session: Session, exe_name: str, png: bytes, fetched_at: str) -> None:
    stmt = sqlite_insert(AppIcon).values(
        exe_name=exe_name, png=png, fetched_at=fetched_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppIcon.exe_name],
        set_={"png": stmt.excluded.png, "fetched_at": stmt.excluded.fetched_at},
    )
    session.execute(stmt)
    session.commit()


def get_app_icon(
    session: Session, exe_name: str,
) -> tuple[bytes, str] | None:
    stmt = select(AppIcon.png, AppIcon.fetched_at).where(AppIcon.exe_name == exe_name)
    row = session.execute(stmt).first()
    if row is None:
        return None
    png, ts = row
    return bytes(png), str(ts)


def list_apps_with_icons(session: Session) -> list[str]:
    stmt = select(AppIcon.exe_name).order_by(AppIcon.exe_name)
    return [str(x) for (x,) in session.execute(stmt).all()]


# ---- App settings (per-app tracking opt-in + blocklist) ----------------

# Singolo source of truth per i nomi delle chiavi: evita typo silenziosi.
_KEY_TRACKING_ENABLED = "tracking_enabled"
_KEY_BLOCKLIST = "blocklist"


@dataclass(frozen=True)
class PerAppSettings:
    tracking_enabled: bool
    blocklist: tuple[str, ...]   # basename comparisons, case-insensitive


def _kv_get(session: Session, key: str) -> str | None:
    row = session.execute(
        select(AppSetting.value).where(AppSetting.key == key)
    ).first()
    return None if row is None else str(row[0])


def _kv_set(session: Session, key: str, value: str) -> None:
    stmt = sqlite_insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppSetting.key],
        set_={"value": stmt.excluded.value},
    )
    session.execute(stmt)


def get_per_app_settings(session: Session) -> PerAppSettings:
    enabled_raw = _kv_get(session, _KEY_TRACKING_ENABLED)
    blocklist_raw = _kv_get(session, _KEY_BLOCKLIST)

    enabled = enabled_raw == "1"  # default: False (opt-in)
    blocklist: tuple[str, ...] = ()
    if blocklist_raw:
        try:
            decoded = json.loads(blocklist_raw)
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, list):
            blocklist = tuple(
                s.strip().lower() for s in decoded
                if isinstance(s, str) and s.strip()
            )
    return PerAppSettings(tracking_enabled=enabled, blocklist=blocklist)


def set_per_app_settings(
    session: Session,
    tracking_enabled: bool | None = None,
    blocklist: Iterable[str] | None = None,
) -> PerAppSettings:
    if tracking_enabled is not None:
        _kv_set(session, _KEY_TRACKING_ENABLED, "1" if tracking_enabled else "0")
    if blocklist is not None:
        normalized = sorted({s.strip().lower() for s in blocklist if s.strip()})
        _kv_set(session, _KEY_BLOCKLIST, json.dumps(normalized))
    session.commit()
    return get_per_app_settings(session)

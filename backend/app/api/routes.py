from __future__ import annotations

import json
from datetime import date as _date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request

from app.aggregator.buffer import Aggregator
from app.core.config import get_settings
from app.core.paths import BACKEND_DIR
from app.hook.vk_codes import name as vk_name
from app.storage.repository import (
    all_time_total_and_first_date,
    daily_totals_range,
    hourly_matrix_range,
    keys_in_range,
    today_total,
    top_keys_range,
)
from app.storage.session import get_sessionmaker

from .schemas import (
    DailyTotal,
    HourlyCell,
    HourlyHeatmapResponse,
    KeyboardHeatmapResponse,
    KeyCount,
    SummaryResponse,
    TimelineResponse,
    TopKeysResponse,
)

router = APIRouter(prefix="/api")

_LAYOUT_PATH = BACKEND_DIR / "app" / "api" / "data" / "q6he_ansi_it.json"


def _aggregator(request: Request) -> Aggregator | None:
    return getattr(request.app.state, "aggregator", None)


def _today_iso() -> str:
    return _date.today().isoformat()


def _parse_range(start: str | None, end: str | None, default_days: int = 30) -> tuple[str, str]:
    try:
        end_d = _date.fromisoformat(end) if end else _date.today()
        start_d = _date.fromisoformat(start) if start else end_d - timedelta(days=default_days - 1)
    except ValueError:
        # Malformed input → 400, not 500. Without this, fromisoformat raises
        # and bubbles up to the generic exception handler.
        raise HTTPException(status_code=400, detail="invalid date (expected YYYY-MM-DD)")
    if start_d > end_d:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if (end_d - start_d).days > 366 * 5:
        raise HTTPException(status_code=400, detail="range too wide (max 5 years)")
    return start_d.isoformat(), end_d.isoformat()


def _to_keycounts(rows: list[tuple[int, int, int]]) -> list[KeyCount]:
    return [KeyCount(vk=vk, scancode=sc, name=vk_name(vk), count=c) for vk, sc, c in rows]


@router.get("/stats/summary", response_model=SummaryResponse)
def stats_summary(request: Request) -> SummaryResponse:
    settings = get_settings()
    today = _today_iso()
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        td = today_total(session, today=today)
        all_time, first_date = all_time_total_and_first_date(session)

    agg = _aggregator(request)
    session_total = agg.session_view()[0] if agg is not None else 0

    return SummaryResponse(
        today=today,
        today_total=td,
        session_total=session_total,
        all_time_total=all_time,
        first_recorded_date=first_date,
        flush_interval_seconds=settings.flush_interval_seconds,
    )


@router.get("/stats/top", response_model=TopKeysResponse)
def stats_top(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> TopKeysResponse:
    s, e = _parse_range(start, end, default_days=1)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = top_keys_range(session, s, e, limit=limit)
    return TopKeysResponse(start=s, end=e, keys=_to_keycounts(rows))


@router.get("/timeline/daily", response_model=TimelineResponse)
def timeline_daily(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> TimelineResponse:
    s, e = _parse_range(start, end, default_days=30)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = daily_totals_range(session, s, e)
    days = [DailyTotal(date=d, total=t) for d, t in rows]
    return TimelineResponse(start=s, end=e, days=days)


@router.get("/heatmap/hourly", response_model=HourlyHeatmapResponse)
def heatmap_hourly(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> HourlyHeatmapResponse:
    s, e = _parse_range(start, end, default_days=30)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = hourly_matrix_range(session, s, e)
    cells = [HourlyCell(date=d, hour=h, total=t) for d, h, t in rows]
    return HourlyHeatmapResponse(start=s, end=e, cells=cells)


@router.get("/heatmap/keyboard", response_model=KeyboardHeatmapResponse)
def heatmap_keyboard(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> KeyboardHeatmapResponse:
    s, e = _parse_range(start, end, default_days=30)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = keys_in_range(session, s, e)
    return KeyboardHeatmapResponse(start=s, end=e, keys=_to_keycounts(rows))


@router.get("/keyboard/layout")
def keyboard_layout() -> dict:
    if not _LAYOUT_PATH.is_file():
        raise HTTPException(status_code=500, detail="layout file missing")
    return json.loads(_LAYOUT_PATH.read_text(encoding="utf-8"))

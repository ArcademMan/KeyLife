from __future__ import annotations

import hashlib
import json
from datetime import date as _date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.aggregator.buffer import Aggregator
from app.core.config import get_settings
from app.core.paths import BACKEND_DIR
from app.hook.vk_codes import name as vk_name
from app.storage.repository import (
    all_time_total_and_first_date,
    apps_hourly_range,
    apps_summary_range,
    daily_totals_range,
    forget_app,
    get_app_icon,
    get_per_app_settings,
    hourly_matrix_range,
    keys_in_range,
    list_apps_with_icons,
    set_per_app_settings,
    today_total,
    top_keys_range,
    total_attributed_range,
    total_keystrokes_range,
    unattributed_hourly_range,
)

# Bucket sintetico per i press che non sono attribuiti a nessuna app
# (feature off, periodi pre-feature, blocklist). Il nome usa angle
# bracket perché Windows li rifiuta nei filename, garantendo che non
# possa mai collidere con un exe reale. Il frontend riconosce il prefisso
# "<" per renderlo con stile differente (italic + tooltip).
SYNTHETIC_NO_APP = "<no app>"
from app.storage.session import get_sessionmaker

from .schemas import (
    AppCount,
    AppHourlyCell,
    AppsHourlyResponse,
    AppsSummaryResponse,
    DailyTotal,
    ForgetAppRequest,
    ForgetAppResponse,
    HourlyCell,
    HourlyHeatmapResponse,
    KeyboardHeatmapResponse,
    KeyCount,
    PerAppSettingsModel,
    PerAppSettingsUpdate,
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


# ---- Per-app tracking endpoints ----------------------------------------

# Limite duro su quante voci accettiamo nella blocklist via API: l'utente
# non ne avrà mai più di una manciata, ma evita che un client buggato
# saturi la kv table con MB di JSON. 256 è una soglia comoda.
_MAX_BLOCKLIST_LEN = 256
_MAX_EXE_NAME_LEN = 260  # MAX_PATH


def _validate_exe_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="exe_name is required")
    if len(name) > _MAX_EXE_NAME_LEN:
        raise HTTPException(status_code=400, detail="exe_name too long")
    return name


@router.get("/settings/per-app", response_model=PerAppSettingsModel)
def per_app_settings_get() -> PerAppSettingsModel:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        s = get_per_app_settings(session)
    return PerAppSettingsModel(
        tracking_enabled=s.tracking_enabled,
        blocklist=list(s.blocklist),
    )


@router.put("/settings/per-app", response_model=PerAppSettingsModel)
def per_app_settings_put(
    body: PerAppSettingsUpdate, request: Request,
) -> PerAppSettingsModel:
    if body.blocklist is not None:
        if len(body.blocklist) > _MAX_BLOCKLIST_LEN:
            raise HTTPException(status_code=400, detail="blocklist too large")
        for item in body.blocklist:
            if not isinstance(item, str) or len(item) > _MAX_EXE_NAME_LEN:
                raise HTTPException(status_code=400, detail="invalid blocklist entry")

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        new_state = set_per_app_settings(
            session,
            tracking_enabled=body.tracking_enabled,
            blocklist=body.blocklist,
        )

    # Hot-reload nel daemon: senza questo il cambio resta solo nel DB e
    # diventa effettivo solo al prossimo riavvio.
    daemon = getattr(request.app.state, "daemon", None)
    if daemon is not None:
        try:
            daemon.refresh_per_app_state()
        except Exception:
            # Logghiamo ma non rompiamo la PUT: il setting è salvato e si
            # applica al prossimo restart anche se l'hot-reload fallisce.
            import logging as _logging
            _logging.getLogger(__name__).exception("daemon refresh failed")

    return PerAppSettingsModel(
        tracking_enabled=new_state.tracking_enabled,
        blocklist=list(new_state.blocklist),
    )


@router.get("/apps/summary", response_model=AppsSummaryResponse)
def apps_summary(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> AppsSummaryResponse:
    s, e = _parse_range(start, end, default_days=30)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        # +1 al limit così il bucket sintetico non spinge fuori una app
        # legittima quando si trova nel taglio.
        rows = apps_summary_range(session, s, e, limit=limit + 1)
        with_icons = set(list_apps_with_icons(session))
        global_total = total_keystrokes_range(session, s, e)
        attributed_total = total_attributed_range(session, s, e)

    delta = max(0, global_total - attributed_total)
    apps: list[AppCount] = [
        AppCount(exe_name=exe, count=cnt, has_icon=exe in with_icons)
        for exe, cnt in rows
    ]
    if delta > 0:
        # Inserisci il bucket sintetico nel posto giusto per count.
        synthetic = AppCount(exe_name=SYNTHETIC_NO_APP, count=delta, has_icon=False)
        idx = next((i for i, a in enumerate(apps) if a.count < delta), len(apps))
        apps.insert(idx, synthetic)
    apps = apps[:limit]
    return AppsSummaryResponse(start=s, end=e, apps=apps)


@router.get("/apps/hourly", response_model=AppsHourlyResponse)
def apps_hourly(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    exe_name: str | None = Query(default=None, max_length=_MAX_EXE_NAME_LEN),
) -> AppsHourlyResponse:
    s, e = _parse_range(start, end, default_days=30)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        if exe_name == SYNTHETIC_NO_APP:
            # Bucket sintetico: ogni cella è hourly_totals - sum(hourly_app_totals).
            delta_rows = unattributed_hourly_range(session, s, e)
            cells = [
                AppHourlyCell(date=d, hour=h, exe_name=SYNTHETIC_NO_APP, count=c)
                for d, h, c in delta_rows
            ]
        else:
            rows = apps_hourly_range(session, s, e, exe_name=exe_name)
            cells = [
                AppHourlyCell(date=d, hour=h, exe_name=exe, count=c)
                for d, h, exe, c in rows
            ]
    return AppsHourlyResponse(start=s, end=e, cells=cells)


@router.get("/app-icons/{exe_name}")
def app_icon(exe_name: str, request: Request) -> Response:
    name = _validate_exe_name(exe_name)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        icon = get_app_icon(session, name.lower())
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    png, fetched_at = icon
    # ETag dal contenuto: se l'icona viene re-estratta con bytes diversi
    # cambia. Niente collisioni con altri exe perché il PNG include il
    # nome implicitly via la differenza dei pixel.
    etag = '"' + hashlib.sha256(png).hexdigest()[:16] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "ETag": etag,
            # 5 minuti: bilanciamo cache hit con la possibilità che il
            # worker rigeneri l'icona (cambio di versione dell'app).
            "Cache-Control": "private, max-age=300",
            "X-Fetched-At": fetched_at,
        },
    )


@router.post("/apps/forget", response_model=ForgetAppResponse)
def apps_forget(body: ForgetAppRequest) -> ForgetAppResponse:
    name = _validate_exe_name(body.exe_name).lower()
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        n = forget_app(session, name)
    return ForgetAppResponse(exe_name=name, rows_deleted=n)

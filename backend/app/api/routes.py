from __future__ import annotations

import hashlib
import json
import os
from datetime import date as _date, timedelta

import tempfile
from fastapi import (
    APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile,
)

from app.aggregator.buffer import Aggregator
from app.core.config import get_settings
from app.core.paths import BACKEND_DIR
from app.hook.vk_codes import name as vk_name
from app.storage.backup import (
    BackupCorrupt,
    InvalidPassphrase,
    cancel_pending_restore,
    restore_pending_info,
    stage_restore,
    unwrap_db_key,
    wrap_db_key,
)
from app.storage.repository import (
    all_time_total_and_first_date,
    apps_hourly_range,
    apps_summary_range,
    daily_totals_range,
    forget_app,
    get_app_icon,
    get_backup_config,
    get_backup_envelope,
    get_per_app_settings,
    hourly_matrix_range,
    keys_in_range,
    list_apps_with_icons,
    set_backup_config,
    set_backup_envelope,
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
    BackupConfigModel,
    BackupConfigUpdate,
    BackupInfoModel,
    DailyTotal,
    ForgetAppRequest,
    ForgetAppResponse,
    HourlyCell,
    HourlyHeatmapResponse,
    KeyboardHeatmapResponse,
    KeyCount,
    PassphraseDeleteRequest,
    PassphraseSetRequest,
    PerAppSettingsModel,
    PerAppSettingsUpdate,
    RestoreStagedResponse,
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


# ---- Backup endpoints --------------------------------------------------

# Hard cap su quanto leggiamo da un upload .zip di restore: il DB non
# dovrebbe superare poche decine di MB in usi normali. 200 MB ci copre con
# margine 100x e fa da sentinel anti-DOS.
_MAX_RESTORE_UPLOAD_BYTES = 200 * 1024 * 1024


def _daemon(request: Request):
    return getattr(request.app.state, "daemon", None)


def _backup_config_response(request: Request) -> BackupConfigModel:
    settings = get_settings()
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        cfg = get_backup_config(session)
    resolved = cfg.dir or str(settings.data_dir / "backups")
    return BackupConfigModel(
        enabled=cfg.enabled,
        interval_hours=cfg.interval_hours,
        keep_n=cfg.keep_n,
        dir=cfg.dir,
        resolved_dir=resolved,
        has_passphrase=cfg.has_passphrase,
        last_backup_at=cfg.last_backup_at,
        restore_pending=restore_pending_info(settings.data_dir) is not None,
    )


@router.get("/settings/backup", response_model=BackupConfigModel)
def backup_config_get(request: Request) -> BackupConfigModel:
    return _backup_config_response(request)


@router.put("/settings/backup", response_model=BackupConfigModel)
def backup_config_put(body: BackupConfigUpdate, request: Request) -> BackupConfigModel:
    SessionLocal = get_sessionmaker()
    # `enabled=True` ha senso solo se c'è una passphrase: altrimenti il
    # loop gira ma salta ogni tick. Più chiaro al setter dire 400 subito.
    if body.enabled is True:
        with SessionLocal() as session:
            cfg = get_backup_config(session)
        if not cfg.has_passphrase:
            raise HTTPException(
                status_code=400,
                detail="set a backup passphrase before enabling auto-backup",
            )

    # `dir` ha 3 stati nel modello (campo opzionale Pydantic):
    # - non passato (model_fields_set non lo contiene) → invariato
    # - passato a "" o None → reset al default
    # - passato a stringa → set
    dir_arg: object
    if "dir" in body.model_fields_set:
        dir_arg = body.dir or ""   # "" sentinel handled by setter
    else:
        from app.storage.repository import _UNSET  # type: ignore[attr-defined]
        dir_arg = _UNSET

    try:
        with SessionLocal() as session:
            set_backup_config(
                session,
                enabled=body.enabled,
                interval_hours=body.interval_hours,
                keep_n=body.keep_n,
                dir=dir_arg,  # type: ignore[arg-type]
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Hot-reload nel daemon: backup loop riparte/cambia cadenza senza riavvio.
    daemon = _daemon(request)
    if daemon is not None:
        try:
            daemon.refresh_backup_state()
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).exception("daemon backup refresh failed")

    return _backup_config_response(request)


@router.put("/settings/backup/passphrase", response_model=BackupConfigModel)
def backup_set_passphrase(body: PassphraseSetRequest, request: Request) -> BackupConfigModel:
    """Set o change della passphrase.

    Se non esiste un envelope, `old_passphrase` viene ignorato e viene
    creato un nuovo envelope dalla chiave DB corrente. Se esiste, `old_`
    è obbligatorio e deve sbloccare l'envelope esistente — altrimenti 401.

    Nota: cambiare la passphrase NON re-wrappa i backup .zip già scritti
    (sono immutabili e usano la vecchia passphrase). Il frontend mostra
    un warning su questo punto.
    """
    settings = get_settings()
    SessionLocal = get_sessionmaker()

    with SessionLocal() as session:
        existing = get_backup_envelope(session)

    if existing is not None:
        if not body.old_passphrase:
            raise HTTPException(
                status_code=400,
                detail="old_passphrase is required to change an existing passphrase",
            )
        try:
            unwrap_db_key(body.old_passphrase, existing)
        except InvalidPassphrase:
            raise HTTPException(status_code=401, detail="old passphrase is incorrect")
        except BackupCorrupt as e:
            raise HTTPException(status_code=500, detail=f"existing envelope is corrupt: {e}")

    # Nuovo envelope dalla chiave DB corrente (mai cambia, viene solo
    # ri-wrappata con la nuova passphrase).
    db_key_hex = settings.db_key.get_secret_value()
    new_env = wrap_db_key(body.new_passphrase, db_key_hex)
    with SessionLocal() as session:
        set_backup_envelope(session, dict(new_env))

    daemon = _daemon(request)
    if daemon is not None:
        try:
            daemon.refresh_backup_state()
        except Exception:
            pass

    return _backup_config_response(request)


@router.delete("/settings/backup/passphrase", response_model=BackupConfigModel)
def backup_delete_passphrase(body: PassphraseDeleteRequest, request: Request) -> BackupConfigModel:
    """Rimuove l'envelope. Disabilita anche auto-backup se attivo.

    Richiede la passphrase corrente come conferma: cancellare per sbaglio
    significherebbe non poter più decifrare i backup esistenti (la
    passphrase è l'unico modo di unwrappare la chiave).
    """
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        existing = get_backup_envelope(session)
    if existing is None:
        raise HTTPException(status_code=400, detail="no passphrase to delete")
    try:
        unwrap_db_key(body.passphrase, existing)
    except InvalidPassphrase:
        raise HTTPException(status_code=401, detail="passphrase is incorrect")
    except BackupCorrupt as e:
        raise HTTPException(status_code=500, detail=f"envelope corrupt: {e}")

    with SessionLocal() as session:
        set_backup_envelope(session, None)
        # Spegni anche auto-backup, altrimenti il loop continua a girare
        # e a fallire (no envelope).
        set_backup_config(session, enabled=False)

    daemon = _daemon(request)
    if daemon is not None:
        try:
            daemon.refresh_backup_state()
        except Exception:
            pass

    return _backup_config_response(request)


@router.get("/backups", response_model=list[BackupInfoModel])
def backups_list(request: Request) -> list[BackupInfoModel]:
    daemon = _daemon(request)
    if daemon is None:
        return []
    return [
        BackupInfoModel(filename=b.filename, size=b.size, created_at=b.created_at)
        for b in daemon.list_existing_backups()
    ]


@router.post("/backups/now", response_model=BackupInfoModel)
def backups_now(request: Request) -> BackupInfoModel:
    """Triggera un backup immediato (sincrono). Richiede passphrase impostata."""
    daemon = _daemon(request)
    if daemon is None:
        raise HTTPException(status_code=503, detail="daemon not running")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        cfg = get_backup_config(session)
    if not cfg.has_passphrase:
        raise HTTPException(
            status_code=400,
            detail="set a backup passphrase before triggering a backup",
        )
    try:
        info = daemon.run_backup_now()
    except Exception as e:
        # Niente leak del path completo nel detail: i path includono lo
        # username Windows.
        raise HTTPException(status_code=500, detail=f"backup failed: {type(e).__name__}")
    return BackupInfoModel(
        filename=info.filename, size=info.size, created_at=info.created_at,
    )


@router.delete("/backups/{filename}", status_code=204)
def backups_delete(filename: str, request: Request) -> Response:
    daemon = _daemon(request)
    if daemon is None:
        raise HTTPException(status_code=503, detail="daemon not running")
    try:
        ok = daemon.delete_backup_file(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="backup not found")
    return Response(status_code=204)


@router.post("/backups/restore", response_model=RestoreStagedResponse)
async def backups_restore(
    file: UploadFile = File(...),
    passphrase: str = Form(...),
) -> RestoreStagedResponse:
    """Stagea un restore. Il restore EFFETTIVO avviene al prossimo riavvio.

    Step-by-step:
      1. Salva il .zip in un file temp (l'API non scrive nella backup dir
         dell'utente).
      2. `stage_restore()` valida zip + passphrase + estrae il DB nella
         staging dir + scrive il marker. Tutto o niente.
      3. Risponde 200 con `restart_required=true`.

    Errori comuni:
      - passphrase sbagliata → 401
      - zip non valido / manifest mancante → 400
      - upload troppo grande → 413
    """
    settings = get_settings()

    # Streaming read con cap. UploadFile.size può essere None su certi
    # client; non possiamo fidarci e dobbiamo contare i byte letti.
    with tempfile.NamedTemporaryFile(
        prefix="keylife-restore-", suffix=".zip", delete=False,
    ) as tmp:
        tmp_path = tmp.name
        total = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MiB
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_RESTORE_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload too large (>{_MAX_RESTORE_UPLOAD_BYTES // (1024*1024)} MB)",
                    )
                tmp.write(chunk)
        except HTTPException:
            tmp.close()
            try: os.unlink(tmp_path)
            except OSError: pass
            raise

    try:
        from pathlib import Path as _Path
        staged = stage_restore(_Path(tmp_path), passphrase, settings.data_dir)
    except InvalidPassphrase:
        raise HTTPException(status_code=401, detail="passphrase is incorrect")
    except BackupCorrupt as e:
        raise HTTPException(status_code=400, detail=f"invalid backup: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"restore staging failed: {type(e).__name__}")
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass

    return RestoreStagedResponse(
        staged_at=staged.staged_at,
        source_filename=file.filename or "backup.zip",
    )


@router.delete("/backups/restore", status_code=204)
def backups_restore_cancel(request: Request) -> Response:
    """Annulla un restore staged ma non ancora applicato."""
    settings = get_settings()
    ok = cancel_pending_restore(settings.data_dir)
    if not ok:
        raise HTTPException(status_code=404, detail="no restore pending")
    return Response(status_code=204)

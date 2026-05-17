from __future__ import annotations

from pydantic import BaseModel, Field


class KeyCount(BaseModel):
    vk: int
    scancode: int
    name: str
    count: int


class SummaryResponse(BaseModel):
    today: str
    today_total: int
    session_total: int
    all_time_total: int
    first_recorded_date: str | None
    flush_interval_seconds: float


class TopKeysResponse(BaseModel):
    start: str
    end: str
    keys: list[KeyCount]


class DailyTotal(BaseModel):
    date: str
    total: int


class TimelineResponse(BaseModel):
    start: str
    end: str
    days: list[DailyTotal]


class HourlyCell(BaseModel):
    date: str
    hour: int = Field(ge=0, le=23)
    total: int


class HourlyHeatmapResponse(BaseModel):
    start: str
    end: str
    cells: list[HourlyCell]


class KeyboardHeatmapResponse(BaseModel):
    start: str
    end: str
    keys: list[KeyCount]


# --- Per-app tracking ---------------------------------------------------

class PerAppSettingsModel(BaseModel):
    tracking_enabled: bool
    blocklist: list[str]


class PerAppSettingsUpdate(BaseModel):
    """PUT body. Tutti i campi sono opzionali: omettere = lascia invariato.

    `blocklist` è normalizzata server-side (lowercase + dedup) ed è la fonte
    di verità: il frontend deve fare PUT con la lista nuova completa, non
    un diff.
    """
    tracking_enabled: bool | None = None
    blocklist: list[str] | None = None


class AppCount(BaseModel):
    exe_name: str
    count: int
    has_icon: bool


class AppsSummaryResponse(BaseModel):
    start: str
    end: str
    apps: list[AppCount]


class AppHourlyCell(BaseModel):
    date: str
    hour: int = Field(ge=0, le=23)
    exe_name: str
    count: int


class AppsHourlyResponse(BaseModel):
    start: str
    end: str
    cells: list[AppHourlyCell]


class ForgetAppRequest(BaseModel):
    exe_name: str


class ForgetAppResponse(BaseModel):
    exe_name: str
    rows_deleted: int


# --- Backup ---------------------------------------------------------------

class BackupConfigModel(BaseModel):
    enabled: bool
    interval_hours: int = Field(ge=1, le=720)
    keep_n: int = Field(ge=1, le=365)
    dir: str | None
    resolved_dir: str           # path effettivo, per UI ("ho capito dove finiscono")
    has_passphrase: bool
    last_backup_at: str | None
    restore_pending: bool       # True se c'è un restore staged in attesa di riavvio


class BackupConfigUpdate(BaseModel):
    """Patch della config. Campi omessi → invariati. `dir=""` → torna al default."""
    enabled: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=720)
    keep_n: int | None = Field(default=None, ge=1, le=365)
    dir: str | None = None       # discriminato in routes: usiamo un sentinel "__unset__"


class PassphraseSetRequest(BaseModel):
    """Set/change passphrase. `old_passphrase` richiesto solo se ne esiste già una."""
    new_passphrase: str = Field(min_length=8, max_length=1024)
    old_passphrase: str | None = None


class PassphraseDeleteRequest(BaseModel):
    """Cancella envelope. Richiede la passphrase corrente come conferma anti-fat-finger."""
    passphrase: str


class BackupInfoModel(BaseModel):
    filename: str
    size: int
    created_at: str


class RestoreStagedResponse(BaseModel):
    staged_at: str
    source_filename: str
    restart_required: bool = True

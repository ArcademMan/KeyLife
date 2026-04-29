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

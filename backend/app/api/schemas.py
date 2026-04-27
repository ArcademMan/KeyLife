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

"""Tiny JSON-backed UI preferences.

Lives next to the SQLite DB in the user data dir. Holds preferences
that the UI mutates at runtime: start_minimized and the flush interval
override (None = fall back to pydantic-settings default).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.core.config import get_settings


@dataclass
class UiState:
    start_minimized: bool = False
    flush_interval_seconds: float | None = None


def _path():
    return get_settings().data_dir / "ui_state.json"


def _coerce_interval(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return f


def load() -> UiState:
    p = _path()
    if not p.is_file():
        return UiState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UiState()
    return UiState(
        start_minimized=bool(data.get("start_minimized", False)),
        flush_interval_seconds=_coerce_interval(data.get("flush_interval_seconds")),
    )


def save(state: UiState) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

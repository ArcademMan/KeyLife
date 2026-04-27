"""Tiny JSON-backed UI preferences (start_minimized).

Lives next to the SQLite DB in the user data dir. Settings that have
runtime side effects (data_dir, flush interval) stay in pydantic-settings;
this file only stores what the UI itself needs to remember.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.core.config import get_settings


@dataclass
class UiState:
    start_minimized: bool = False


def _path():
    return get_settings().data_dir / "ui_state.json"


def load() -> UiState:
    p = _path()
    if not p.is_file():
        return UiState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UiState()
    return UiState(start_minimized=bool(data.get("start_minimized", False)))


def save(state: UiState) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventKind(Enum):
    DOWN = "down"
    UP = "up"


@dataclass(frozen=True, slots=True)
class KeyEvent:
    kind: EventKind
    vk: int
    scancode: int
    extended: bool
    timestamp_ms: int
    is_repeat: bool

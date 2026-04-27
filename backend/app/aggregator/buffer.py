from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.hook.events import EventKind, KeyEvent


@dataclass
class Snapshot:
    per_key: dict[tuple[str, int, int], int] = field(default_factory=dict)
    per_hour: dict[tuple[str, int], int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.per_key and not self.per_hour

    @property
    def total_presses(self) -> int:
        return sum(self.per_key.values())


class Aggregator:
    """Thread-safe in-memory aggregator with auto-repeat filtering.

    A physical key press is counted exactly once: the first DOWN for a
    (vk, scancode) pair while it is not already in the down-set. The OS
    auto-repeat stream produces additional DOWNs at the same vk/scancode
    that we ignore until the matching UP arrives.
    """

    # If a key has been "held" longer than this without an UP, treat the next
    # DOWN as a fresh press. Real human key holds are well under this; values
    # above mean we missed an UP (focus change, sleep, hook re-install, etc.).
    _DOWN_STALE_MS = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Maps (vk, scancode) -> timestamp_ms of the DOWN that put it here.
        self._down: dict[tuple[int, int], int] = {}
        self._per_key: dict[tuple[str, int, int], int] = defaultdict(int)
        self._per_hour: dict[tuple[str, int], int] = defaultdict(int)
        # Session-only counters for the live UI
        self._session_per_key: dict[tuple[int, int], int] = defaultdict(int)
        self._session_total: int = 0

    def record(self, ev: KeyEvent) -> bool:
        """Record an event. Returns True iff it was counted as a press."""
        key = (ev.vk, ev.scancode)
        if ev.kind is EventKind.UP:
            with self._lock:
                self._down.pop(key, None)
            return False

        # DOWN
        with self._lock:
            prev_ts = self._down.get(key)
            if prev_ts is not None and ev.timestamp_ms - prev_ts < self._DOWN_STALE_MS:
                return False  # auto-repeat (still held)
            # Either first DOWN, or a stale entry from a missed UP — count it.
            self._down[key] = ev.timestamp_ms
            now = datetime.fromtimestamp(ev.timestamp_ms / 1000.0)
            date = now.strftime("%Y-%m-%d")
            hour = now.hour
            self._per_key[(date, ev.vk, ev.scancode)] += 1
            self._per_hour[(date, hour)] += 1
            self._session_per_key[key] += 1
            self._session_total += 1
        return True

    def take_snapshot(self) -> Snapshot:
        """Atomically extract pending counts and reset them."""
        with self._lock:
            snap = Snapshot(
                per_key=dict(self._per_key),
                per_hour=dict(self._per_hour),
            )
            self._per_key.clear()
            self._per_hour.clear()
            # GC stale DOWN entries: a key whose UP we never received (focus
            # change, sleep/resume, secure desktop, hook re-install, software
            # that sends DOWN-only via SendInput) would otherwise pin the
            # entry forever and cause the next press within _DOWN_STALE_MS to
            # be dropped as auto-repeat. Bounded sweep, runs under the lock.
            if self._down:
                cutoff = int(time.time() * 1000) - self._DOWN_STALE_MS
                self._down = {k: ts for k, ts in self._down.items() if ts >= cutoff}
            return snap

    def restore_snapshot(self, snap: Snapshot) -> None:
        """Re-merge a snapshot into the live counters.

        Used when a flush fails after take_snapshot has already cleared the
        counters: without this, the snapshot's presses would be lost forever.
        Concurrent record() calls are safe because the merge happens under
        the same lock.
        """
        if snap.is_empty:
            return
        with self._lock:
            for k, v in snap.per_key.items():
                self._per_key[k] += v
            for k, v in snap.per_hour.items():
                self._per_hour[k] += v

    def session_view(self) -> tuple[int, dict[tuple[int, int], int]]:
        with self._lock:
            return self._session_total, dict(self._session_per_key)

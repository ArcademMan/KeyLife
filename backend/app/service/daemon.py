"""Daemon: hook + aggregator + periodic flush.

Designed to be embeddable inside the Tk app and runnable headlessly.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from app.aggregator.buffer import Aggregator
from app.core.config import get_settings
from app.hook.events import KeyEvent
from app.hook.win_hook import WindowsKeyboardHook
from app.storage.repository import flush_snapshot
from app.storage.session import get_sessionmaker

log = logging.getLogger(__name__)


class KeyLifeDaemon:
    def __init__(
        self,
        ui_listener: Callable[[KeyEvent], None] | None = None,
    ) -> None:
        self._settings = get_settings()
        self._aggregator = Aggregator()
        self._hook = WindowsKeyboardHook(listener=self._on_event)
        self._ui_listener = ui_listener
        self._stop = threading.Event()
        # Wakes the flush loop early when the interval changes, without
        # ending it (which is what setting _stop would do).
        self._wake = threading.Event()
        self._flush_thread: threading.Thread | None = None
        self._flush_lock = threading.Lock()
        self._SessionLocal = get_sessionmaker()
        # Monotonic timestamp of the scheduled next flush. Used by the UI to
        # render a countdown. Reset right after each flush completes.
        self._next_flush_at: float = 0.0
        # Mutable so the Settings UI can change it at runtime; the flush
        # loop re-reads it each iteration.
        self._flush_interval = float(self._settings.flush_interval_seconds)
        # Honor a previously-saved UI override.
        try:
            from app.ui.qt import ui_state  # local import: keeps daemon importable headless

            saved = ui_state.load().flush_interval_seconds
            if saved is not None and saved > 0:
                self._flush_interval = float(saved)
        except Exception:
            log.exception("could not load flush interval from ui_state")

    @property
    def aggregator(self) -> Aggregator:
        return self._aggregator

    @property
    def flush_interval_seconds(self) -> float:
        return self._flush_interval

    def set_flush_interval(self, seconds: float) -> None:
        # Clamp to a sane range. The lower bound prevents a runaway flush
        # loop hammering SQLite; the upper bound is a generous 24h.
        if seconds < 1.0:
            seconds = 1.0
        elif seconds > 86_400.0:
            seconds = 86_400.0
        self._flush_interval = float(seconds)
        # Reschedule the countdown so the UI reflects the change immediately.
        self._next_flush_at = time.monotonic() + self._flush_interval
        # Wake the flush loop so it re-reads the new interval right away
        # instead of finishing its current wait on the old one.
        self._wake.set()

    def seconds_until_next_flush(self) -> float:
        if self._next_flush_at <= 0.0:
            return self._flush_interval
        return max(0.0, self._next_flush_at - time.monotonic())

    def start(self) -> None:
        # Log only the filename, not the full path: the full path includes the
        # OS username (LOCALAPPDATA\<user>\...) and would leak it via logs.
        log.info("Starting KeyLife daemon (db=%s)", self._settings.db_filename)
        self._hook.start()
        t = threading.Thread(target=self._flush_loop, name="keylife-flush", daemon=True)
        self._flush_thread = t
        t.start()

    def stop(self) -> None:
        log.info("Stopping KeyLife daemon")
        self._stop.set()
        self._wake.set()
        self._hook.stop()
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=5.0)
        # Final flush on shutdown so we don't lose the tail
        self._flush_once()

    def _on_event(self, ev: KeyEvent) -> None:
        self._aggregator.record(ev)
        if self._ui_listener is not None:
            try:
                self._ui_listener(ev)
            except Exception:
                log.exception("UI listener raised")

    def _flush_loop(self) -> None:
        self._next_flush_at = time.monotonic() + self._flush_interval
        while not self._stop.is_set():
            remaining = self._next_flush_at - time.monotonic()
            if remaining > 0:
                # _wake is pulsed by both stop() and set_flush_interval().
                # The interval-change branch reschedules the deadline, so we
                # just loop and recompute remaining instead of distinguishing.
                self._wake.wait(remaining)
                self._wake.clear()
                if self._stop.is_set():
                    break
                # Deadline may have moved if the interval was changed.
                if time.monotonic() < self._next_flush_at:
                    continue
            try:
                self._flush_once()
            except Exception:
                log.exception("flush failed")
            finally:
                self._next_flush_at = time.monotonic() + self._flush_interval

    def _flush_once(self) -> None:
        # Serialize manual ("Flush now" from the UI thread) and periodic flushes.
        with self._flush_lock:
            snap = self._aggregator.take_snapshot()
            if snap.is_empty:
                return
            try:
                with self._SessionLocal() as session:
                    n_keys, n_hours = flush_snapshot(
                        session, snap.per_key, snap.per_hour
                    )
            except Exception:
                # Don't lose the counts: put them back so the next flush retries.
                self._aggregator.restore_snapshot(snap)
                raise
            log.debug("flushed: %d key rows, %d hour rows, %d presses",
                      n_keys, n_hours, snap.total_presses)


class UiEventBridge:
    """Drains hook events into a bounded queue for the UI thread.

    The Tk thread calls drain() on a timer; the hook thread calls
    push() from the listener. Old events are dropped if the queue
    fills, which protects the daemon from a stalled UI.
    """

    def __init__(self, maxsize: int) -> None:
        self._q: queue.Queue[KeyEvent] = queue.Queue(maxsize=maxsize)

    def push(self, ev: KeyEvent) -> None:
        try:
            self._q.put_nowait(ev)
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait(ev)
            except queue.Empty:
                pass

    def drain(self, limit: int = 64) -> list[KeyEvent]:
        out: list[KeyEvent] = []
        for _ in range(limit):
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

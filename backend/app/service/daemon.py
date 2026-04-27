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
        self._flush_thread: threading.Thread | None = None
        self._flush_lock = threading.Lock()
        self._SessionLocal = get_sessionmaker()
        # Monotonic timestamp of the scheduled next flush. Used by the UI to
        # render a countdown. Reset right after each flush completes.
        self._next_flush_at: float = 0.0

    @property
    def aggregator(self) -> Aggregator:
        return self._aggregator

    @property
    def flush_interval_seconds(self) -> float:
        return self._settings.flush_interval_seconds

    def seconds_until_next_flush(self) -> float:
        if self._next_flush_at <= 0.0:
            return self._settings.flush_interval_seconds
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
        interval = self._settings.flush_interval_seconds
        self._next_flush_at = time.monotonic() + interval
        while not self._stop.wait(interval):
            try:
                self._flush_once()
            except Exception:
                log.exception("flush failed")
            finally:
                self._next_flush_at = time.monotonic() + interval

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

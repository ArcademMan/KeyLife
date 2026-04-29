"""Daemon: hook + aggregator + periodic flush.

Designed to be embeddable inside the Tk app and runnable headlessly.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

from app.aggregator.buffer import Aggregator
from app.core.config import get_settings
from app.hook.events import KeyEvent
from app.hook.foreground import ForegroundHook
from app.hook.icons import extract_icon_png
from app.hook.win_hook import WindowsKeyboardHook
from app.storage.repository import (
    PerAppSettings,
    flush_snapshot,
    get_per_app_settings,
    list_apps_with_icons,
    set_app_icon,
)
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

        # --- Per-app tracking (opt-in) -----------------------------------
        # Tutto questo stato è valido solo se `_app_settings.tracking_enabled`
        # è True. `_refresh_per_app_state()` legge il DB e startera/fermerà
        # foreground hook + icon worker di conseguenza.
        self._app_settings: PerAppSettings = PerAppSettings(False, ())
        self._fg_hook: ForegroundHook | None = None
        self._icon_queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=64)
        self._icon_thread: threading.Thread | None = None
        self._icons_known: set[str] = set()

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
        # Per-app: legge dal DB se è attivo e attacca foreground hook +
        # worker. Se l'utente non l'ha mai attivato è un no-op.
        try:
            self.refresh_per_app_state()
        except Exception:
            log.exception("could not init per-app tracking; feature stays off")

    def stop(self) -> None:
        log.info("Stopping KeyLife daemon")
        self._stop.set()
        self._wake.set()
        self._hook.stop()
        self._stop_foreground_if_running()
        self._stop_icon_worker_if_running()
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
                    n_keys, n_hours, n_app_d, n_app_h = flush_snapshot(
                        session,
                        snap.per_key,
                        snap.per_hour,
                        snap.per_app_daily or None,
                        snap.per_app_hourly or None,
                    )
            except Exception:
                # Don't lose the counts: put them back so the next flush retries.
                self._aggregator.restore_snapshot(snap)
                raise
            log.debug(
                "flushed: %d key rows, %d hour rows, %d app-day rows, %d app-hour rows, %d presses",
                n_keys, n_hours, n_app_d, n_app_h, snap.total_presses,
            )

    # --- Per-app tracking lifecycle -------------------------------------

    @property
    def per_app_settings(self) -> PerAppSettings:
        return self._app_settings

    def refresh_per_app_state(self) -> None:
        """Rilegge tracking_enabled + blocklist dal DB e (dis)attiva i sotto-componenti.

        Chiamata dal daemon all'avvio e dall'API quando l'utente cambia
        Settings. Idempotente: se lo stato è già corretto, non fa nulla.
        """
        with self._SessionLocal() as session:
            new_settings = get_per_app_settings(session)

        was_enabled = self._app_settings.tracking_enabled
        self._app_settings = new_settings

        if new_settings.tracking_enabled:
            self._start_foreground_if_needed()
            self._start_icon_worker_if_needed()
            self._aggregator.set_exe_provider(self._make_exe_provider())
            if not was_enabled:
                log.info("per-app tracking ENABLED (blocklist size=%d)",
                         len(new_settings.blocklist))
        else:
            self._aggregator.set_exe_provider(None)
            self._stop_foreground_if_running()
            self._stop_icon_worker_if_running()
            if was_enabled:
                log.info("per-app tracking DISABLED")

    def _make_exe_provider(self) -> Callable[[], str | None]:
        """Costruisce il callable consultato dall'aggregator per ogni press.

        Snapshot della blocklist al momento della costruzione: cambi futuri
        richiedono `refresh_per_app_state()` che ricostruisce il provider.
        Una `frozenset` evita allocazioni nel hot path.
        """
        blocklist = frozenset(self._app_settings.blocklist)
        fg = self._fg_hook
        if fg is None:
            return lambda: None

        def provider() -> str | None:
            exe, _path = fg.current()
            if not exe or exe in blocklist:
                return None
            return exe

        return provider

    def _start_foreground_if_needed(self) -> None:
        if self._fg_hook is not None:
            return
        hook = ForegroundHook(on_change=self._on_foreground_change)
        hook.start()
        self._fg_hook = hook

    def _stop_foreground_if_running(self) -> None:
        if self._fg_hook is None:
            return
        try:
            self._fg_hook.stop()
        except Exception:
            log.exception("foreground hook stop raised")
        self._fg_hook = None

    def _start_icon_worker_if_needed(self) -> None:
        if self._icon_thread is not None and self._icon_thread.is_alive():
            return
        # Pre-popola il set delle exe già con icona così evitiamo round-trip
        # al DB nel hot path della on_change.
        try:
            with self._SessionLocal() as session:
                self._icons_known = set(list_apps_with_icons(session))
        except Exception:
            log.exception("could not preload icon set; will retry per-job")
            self._icons_known = set()
        t = threading.Thread(
            target=self._icon_worker_loop, name="keylife-icons", daemon=True,
        )
        self._icon_thread = t
        t.start()

    def _stop_icon_worker_if_running(self) -> None:
        if self._icon_thread is None:
            return
        # Il worker fa get(timeout=...) e controlla `_stop` ad ogni giro;
        # quando il daemon si ferma esce. Niente sentinel speciale.
        # Non joinamo qui se chiamato a runtime (toggle off): il thread
        # resta in idle finché il daemon non viene fermato. Per il caso
        # toggle off → on → off ripetuto questo è fine: non leakiamo
        # thread perché il worker stesso esce sul `_stop`.
        self._icon_thread = None

    def _on_foreground_change(self, exe_name: str, exe_path: str | None) -> None:
        """Callback dal ForegroundHook: enqueue per icon extraction se serve."""
        if not exe_name or exe_name in self._icons_known:
            return
        if exe_path is None:
            # Bucket "unknown"/"system": nessun path → niente icona.
            return
        try:
            self._icon_queue.put_nowait((exe_name, exe_path))
        except queue.Full:
            # Coda piena: l'utente sta alt-tabbing follemente o il worker
            # è bloccato. Lasciamo perdere questo job: la prossima volta
            # che l'utente focusa lo stesso exe ne otteniamo un altro.
            pass

    def _icon_worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                exe_name, exe_path = self._icon_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if exe_name in self._icons_known:
                continue
            try:
                png = extract_icon_png(exe_path, size=32)
            except Exception:
                log.exception("icon extract crashed for %s", exe_name)
                continue
            if png is None:
                # Memo del fallimento per non riaccodare in loop. Manteniamo
                # in `_icons_known` quel nome: il worst case è che non
                # avremo mai un'icona per questo exe, accettabile.
                self._icons_known.add(exe_name)
                continue
            try:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                with self._SessionLocal() as session:
                    set_app_icon(session, exe_name, png, ts)
                self._icons_known.add(exe_name)
                log.debug("stored icon for %s (%d bytes)", exe_name, len(png))
            except Exception:
                log.exception("could not persist icon for %s", exe_name)


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

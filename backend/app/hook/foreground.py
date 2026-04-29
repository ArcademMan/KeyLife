"""Foreground-window tracking via SetWinEventHook.

Esponiamo `ForegroundHook`: un thread message-only che ascolta
`EVENT_SYSTEM_FOREGROUND` (out-of-context, niente DLL injection) e
mantiene una cache `(exe_name, exe_path)` consultabile dal listener
keyboard al volo, senza syscall per keystroke.

Modello threading
-----------------
- Il thread del hook è quello che chiama `SetWinEventHook` E che pompa i
  messaggi: `WINEVENT_OUTOFCONTEXT` accoda gli eventi come messaggi che
  *arrivano sullo stesso thread* del registrante; senza un message loop
  qui dentro, nessun callback verrebbe invocato.
- La cache è protetta da un lock. Letture (hot path della keystroke) e
  scritture (cambio focus, decine al secondo nel peggiore dei casi) sono
  veloci abbastanza da non meritare uno schema lock-free.

Limitazioni note
----------------
- App UWP (Calculator, Photos, Edge, ...) hostate da
  `ApplicationFrameHost.exe`: vedremo quel nome invece dell'app reale.
  Risolverlo richiede walk dei child window cercando un PID diverso —
  TODO follow-up.
- Processi protetti (anti-cheat, lsass, alcuni servizi): `OpenProcess`
  con `PROCESS_QUERY_LIMITED_INFORMATION` può fallire con `ERROR_ACCESS_DENIED`.
  In quel caso il bucket finale è `"unknown"` (mai `None` per il caller).
- Lockscreen / secure desktop: HWND==0 oppure di owner sistema → bucket
  `"system"`.
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
from collections.abc import Callable
from ctypes import wintypes

log = logging.getLogger(__name__)

# ---------- Win32 constants ----------
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

WM_QUIT = 0x0012

# Ampia: Win32 path lunghi possono superare MAX_PATH=260 nel \\?\ form;
# 1024 wide chars (=2KB stack) è abbondante e non costa nulla per chiamata.
_PATH_BUF_LEN = 1024

# Bucket "fallback" per casi non risolubili — mai stringa vuota perché
# l'aggregator usa l'exe_name come parte di una primary key.
BUCKET_UNKNOWN = "unknown"
BUCKET_SYSTEM = "system"


# ---------- callback signature ----------
# void CALLBACK WinEventProc(HWINEVENTHOOK, DWORD, HWND, LONG, LONG, DWORD, DWORD)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,   # hWinEventHook
    wintypes.DWORD,    # event
    wintypes.HWND,     # hwnd
    wintypes.LONG,     # idObject
    wintypes.LONG,     # idChild
    wintypes.DWORD,    # dwEventThread
    wintypes.DWORD,    # dwmsEventTime
)


def _load_dlls() -> tuple[ctypes.WinDLL, ctypes.WinDLL, ctypes.WinDLL]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = kernel32  # QueryFullProcessImageNameW vive in kernel32 (Vista+)

    user32.SetWinEventHook.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
        WINEVENTPROC, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    ]
    user32.SetWinEventHook.restype = wintypes.HANDLE

    user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    user32.UnhookWinEvent.restype = wintypes.BOOL

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
    ]
    user32.GetMessageW.restype = wintypes.BOOL

    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL

    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM

    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    return user32, kernel32, psapi


# Caricato a livello modulo: una singola WinDLL per l'intero processo.
_user32, _kernel32, _psapi = _load_dlls()


def _exe_for_pid(pid: int) -> str | None:
    """Ritorna il path completo dell'exe per `pid`, o None se inaccessibile."""
    if pid <= 0:
        return None
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(_PATH_BUF_LEN)
        size = wintypes.DWORD(_PATH_BUF_LEN)
        ok = _kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size),
        )
        if not ok:
            return None
        return buf.value or None
    finally:
        _kernel32.CloseHandle(handle)


def resolve_foreground() -> tuple[str, str | None]:
    """Snapshot sincrono del foreground attuale.

    Usato per popolare la cache all'avvio del hook prima del primo evento.
    Stesse semantiche di bucketing del callback async.
    """
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return (BUCKET_SYSTEM, None)
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return (BUCKET_SYSTEM, None)
    path = _exe_for_pid(pid.value)
    if not path:
        return (BUCKET_UNKNOWN, None)
    return (os.path.basename(path).lower(), path)


# ---------- public class ----------

OnChangeCallback = Callable[[str, str | None], None]


class ForegroundHook:
    """Owns a thread that pumps EVENT_SYSTEM_FOREGROUND notifications.

    Usage:
        hook = ForegroundHook(on_change=lambda exe, path: ...)
        hook.start()
        ...
        exe, path = hook.current()       # consultata dal keystroke handler
        ...
        hook.stop()
    """

    def __init__(self, on_change: OnChangeCallback | None = None) -> None:
        self._on_change = on_change
        self._lock = threading.Lock()
        self._exe: str = BUCKET_UNKNOWN
        self._path: str | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_handle: int = 0
        self._proc_ref: WINEVENTPROC | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    # ----- public API -----

    def start(self) -> None:
        if self._thread is not None:
            return
        t = threading.Thread(target=self._run, name="keylife-foreground", daemon=True)
        self._thread = t
        t.start()
        if not self._ready.wait(timeout=5.0):
            raise TimeoutError("foreground hook did not become ready within 5s")
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None

    def current(self) -> tuple[str, str | None]:
        """Snapshot della cache (exe_name, exe_path)."""
        with self._lock:
            return (self._exe, self._path)

    # ----- thread body -----

    def _run(self) -> None:
        try:
            self._thread_id = _kernel32.GetCurrentThreadId()

            # Popola la cache subito, prima di registrare l'hook: una
            # keystroke arrivata nei primi millisecondi non finirà a
            # `unknown` per via di una race contro il primo evento.
            exe, path = resolve_foreground()
            self._update(exe, path)

            @WINEVENTPROC
            def proc(_h, _ev, hwnd, _id_obj, _id_child, _ev_thread, _ts):
                # Eccezioni qui non devono attraversare il confine Win32.
                try:
                    self._handle_foreground_change(hwnd)
                except Exception:
                    log.exception("foreground hook callback raised")

            self._proc_ref = proc

            handle = _user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                None,  # hmodWinEventProc: out-of-context, no DLL
                proc,
                0,     # idProcess: any
                0,     # idThread: any
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            )
            if not handle:
                err = ctypes.get_last_error()
                raise OSError(err, f"SetWinEventHook failed (error {err})")
            self._hook_handle = handle
            self._ready.set()

            msg = wintypes.MSG()
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        except BaseException as e:  # noqa: BLE001
            self._error = e
            self._ready.set()
        finally:
            if self._hook_handle:
                _user32.UnhookWinEvent(self._hook_handle)
                self._hook_handle = 0
            self._proc_ref = None

    def _handle_foreground_change(self, hwnd: int) -> None:
        if not hwnd:
            self._update(BUCKET_SYSTEM, None)
            return
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            self._update(BUCKET_SYSTEM, None)
            return
        path = _exe_for_pid(pid.value)
        if not path:
            self._update(BUCKET_UNKNOWN, None)
            return
        self._update(os.path.basename(path).lower(), path)

    def _update(self, exe: str, path: str | None) -> None:
        with self._lock:
            if exe == self._exe and path == self._path:
                return
            self._exe = exe
            self._path = path
        if self._on_change is not None:
            try:
                self._on_change(exe, path)
            except Exception:
                log.exception("foreground on_change handler raised")

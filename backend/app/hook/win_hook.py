"""Low-level Windows keyboard hook (WH_KEYBOARD_LL) via ctypes.

The hook runs on its own thread, which owns a Windows message pump
(GetMessageW). The OS calls our procedure on that thread for every
keyboard event system-wide. We never block: we update a thread-safe
aggregator and push a small dataclass to a queue for the UI, then
return CallNextHookEx as fast as possible.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from app.hook.events import EventKind, KeyEvent

log = logging.getLogger(__name__)

# ---------- Win32 constants ----------
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
LLKHF_LOWER_IL_INJECTED = 0x02
LLKHF_ALTDOWN = 0x20
LLKHF_UP = 0x80


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


# WINFUNCTYPE -> stdcall on Windows
LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


def _load_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, LowLevelKeyboardProc, wintypes.HMODULE, wintypes.DWORD,
    ]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK

    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    user32.CallNextHookEx.argtypes = [
        wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.CallNextHookEx.restype = wintypes.LPARAM

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
    return user32


def _load_kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    return kernel32


EventListener = Callable[[KeyEvent], None]


class WindowsKeyboardHook:
    """Owns a dedicated thread running the message pump and the LL hook."""

    def __init__(self, listener: EventListener) -> None:
        self._listener = listener
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_handle: int = 0
        self._proc_ref: LowLevelKeyboardProc | None = None  # keep alive
        self._user32 = _load_user32()
        self._kernel32 = _load_kernel32()
        self._ready = threading.Event()
        self._error: BaseException | None = None

    # ----- public API -----
    def start(self) -> None:
        if self._thread is not None:
            return
        t = threading.Thread(target=self._run, name="keylife-hook", daemon=True)
        self._thread = t
        t.start()
        if not self._ready.wait(timeout=5.0):
            # Setup hung. The thread is daemon=True so it won't block exit,
            # but we surface the failure instead of silently returning with
            # no hook installed.
            raise TimeoutError(
                "Windows keyboard hook did not become ready within 5s"
            )
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            # Wake the message loop so GetMessageW returns 0.
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None

    # ----- thread body -----
    def _run(self) -> None:
        try:
            self._thread_id = self._kernel32.GetCurrentThreadId()
            hmod = self._kernel32.GetModuleHandleW(None)

            @LowLevelKeyboardProc
            def proc(nCode: int, wParam: int, lParam: int) -> int:
                if nCode >= 0:
                    try:
                        self._dispatch(wParam, lParam)
                    except Exception:
                        # Must never let exceptions cross into Win32, but a
                        # silent swallow hides broken listeners. Log and drop.
                        log.exception("hook dispatch raised; event dropped")
                return self._user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

            self._proc_ref = proc
            self._hook_handle = self._user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, proc, hmod, 0
            )
            if not self._hook_handle:
                err = ctypes.get_last_error()
                raise OSError(err, f"SetWindowsHookExW failed (error {err})")

            self._ready.set()

            msg = wintypes.MSG()
            while True:
                ret = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                self._user32.TranslateMessage(ctypes.byref(msg))
                self._user32.DispatchMessageW(ctypes.byref(msg))
        except BaseException as e:  # noqa: BLE001
            self._error = e
            self._ready.set()
        finally:
            if self._hook_handle:
                self._user32.UnhookWindowsHookEx(self._hook_handle)
                self._hook_handle = 0
            self._proc_ref = None

    def _dispatch(self, wParam: int, lParam: int) -> None:
        info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT))[0]
        if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kind = EventKind.DOWN
        elif wParam in (WM_KEYUP, WM_SYSKEYUP):
            kind = EventKind.UP
        else:
            return
        ev = KeyEvent(
            kind=kind,
            vk=int(info.vkCode),
            scancode=int(info.scanCode),
            extended=bool(info.flags & LLKHF_EXTENDED),
            injected=bool(info.flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED)),
            # info.time is the OS tick count (GetTickCount), not an epoch
            # timestamp. We capture wall time here so downstream code can
            # bucket by date/hour without ambiguity.
            timestamp_ms=int(time.time() * 1000),
            is_repeat=False,  # auto-repeat detection happens in the aggregator
        )
        self._listener(ev)

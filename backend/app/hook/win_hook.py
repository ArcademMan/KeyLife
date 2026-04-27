"""Windows keyboard listener via the Raw Input API.

We register a message-only window for HID usage page 0x01 / usage 0x06
(generic keyboard) with RIDEV_INPUTSINK, so we receive WM_INPUT for
every keyboard event system-wide while running as a passive sink — we
are never in the input dispatch chain that the foreground app reads.

Compared to a global WH_KEYBOARD_LL hook this:
  - is not a system-wide hook → far less likely to trip game anti-cheats
    that look for the LL-hook DLL-injection / global-hook pattern;
  - does not stall the input flow waiting for our callback to return;
  - still works without administrator privileges.

The hook runs on its own thread which owns the message-only HWND and
its message pump. The OS posts WM_INPUT to that thread; we copy the
RAWINPUT payload, build a small KeyEvent and hand it to the listener.
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
WM_INPUT = 0x00FF
WM_DESTROY = 0x0002
WM_QUIT = 0x0012

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001

RIM_TYPEKEYBOARD = 1

# RAWKEYBOARD.Flags
RI_KEY_MAKE = 0x00
RI_KEY_BREAK = 0x01
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04

# CreateWindowEx — HWND_MESSAGE parent
HWND_MESSAGE = wintypes.HWND(-3)

# Generic Desktop / Keyboard
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_KEYBOARD = 0x06

# VK code that means "ignore, escaped sequence" — typically appears as
# the first half of an E1 Pause/Break and must be filtered.
VK_IGNORE = 0xFF


# ---------- structs ----------
class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


# We only ever register for keyboard input, so we only need RAWKEYBOARD
# in the union — but to safely interpret the buffer we still allocate
# enough room for any RAWINPUT payload Windows might write. The mouse
# payload is the largest at 24 bytes on x64 (vs 16 for keyboard); 32 is
# a comfortable upper bound that survives any future field padding.
_RAWINPUT_PAYLOAD_BYTES = 32


class _RAWINPUT_UNION(ctypes.Union):
    _fields_ = [
        ("keyboard", RAWKEYBOARD),
        ("_pad", ctypes.c_byte * _RAWINPUT_PAYLOAD_BYTES),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data", _RAWINPUT_UNION),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


def _load_user32() -> ctypes.WinDLL:
    u = ctypes.WinDLL("user32", use_last_error=True)

    u.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u.RegisterClassExW.restype = wintypes.ATOM

    u.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    u.UnregisterClassW.restype = wintypes.BOOL

    u.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    u.CreateWindowExW.restype = wintypes.HWND

    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.DestroyWindow.restype = wintypes.BOOL

    u.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    u.DefWindowProcW.restype = wintypes.LPARAM

    u.RegisterRawInputDevices.argtypes = [
        ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT,
    ]
    u.RegisterRawInputDevices.restype = wintypes.BOOL

    u.GetRawInputData.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
        ctypes.POINTER(wintypes.UINT), wintypes.UINT,
    ]
    u.GetRawInputData.restype = wintypes.UINT

    u.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
    ]
    u.GetMessageW.restype = wintypes.BOOL

    u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.TranslateMessage.restype = wintypes.BOOL

    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.restype = wintypes.LPARAM

    u.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    u.PostMessageW.restype = wintypes.BOOL

    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.PostQuitMessage.restype = None

    return u


def _load_kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentThreadId.restype = wintypes.DWORD
    k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k.GetModuleHandleW.restype = wintypes.HMODULE
    return k


EventListener = Callable[[KeyEvent], None]


class WindowsKeyboardHook:
    """Owns a dedicated thread with a message-only HWND receiving WM_INPUT.

    Public API kept identical to the previous WH_KEYBOARD_LL implementation:
    construct with a listener, call start()/stop().
    """

    _CLASS_NAME = "KeyLifeRawInputSink"

    def __init__(self, listener: EventListener) -> None:
        self._listener = listener
        self._user32 = _load_user32()
        self._kernel32 = _load_kernel32()
        self._thread: threading.Thread | None = None
        self._hwnd: int = 0
        self._class_atom: int = 0
        self._proc_ref: WNDPROC | None = None  # keep alive
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._buf_size = ctypes.sizeof(RAWINPUT)
        self._buf = (ctypes.c_byte * self._buf_size)()

    # ----- public API -----
    def start(self) -> None:
        if self._thread is not None:
            return
        t = threading.Thread(target=self._run, name="keylife-hook", daemon=True)
        self._thread = t
        t.start()
        if not self._ready.wait(timeout=5.0):
            raise TimeoutError(
                "Windows raw input hook did not become ready within 5s"
            )
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._hwnd:
            # Wake the message loop so GetMessageW returns 0. We post WM_QUIT
            # to the window itself; GetMessageW(hWnd=...) treats WM_QUIT
            # the same as a thread-level WM_QUIT.
            self._user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None

    # ----- thread body -----
    def _run(self) -> None:
        try:
            hmod = self._kernel32.GetModuleHandleW(None)

            @WNDPROC
            def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
                if msg == WM_INPUT:
                    try:
                        self._handle_wm_input(lparam)
                    except Exception:
                        # Must never let exceptions cross back into Win32.
                        # A silent swallow would hide broken listeners, so log.
                        log.exception("raw input dispatch raised; event dropped")
                    # Per docs: still chain to DefWindowProc so the system can
                    # perform cleanup of the input data.
                    return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)
                if msg == WM_DESTROY:
                    self._user32.PostQuitMessage(0)
                    return 0
                return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            self._proc_ref = wnd_proc

            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = wnd_proc
            wc.hInstance = hmod
            wc.lpszClassName = self._CLASS_NAME
            atom = self._user32.RegisterClassExW(ctypes.byref(wc))
            if not atom:
                err = ctypes.get_last_error()
                raise OSError(err, f"RegisterClassExW failed (error {err})")
            self._class_atom = atom

            hwnd = self._user32.CreateWindowExW(
                0, self._CLASS_NAME, "KeyLifeRawInput", 0,
                0, 0, 0, 0,
                HWND_MESSAGE, None, hmod, None,
            )
            if not hwnd:
                err = ctypes.get_last_error()
                raise OSError(err, f"CreateWindowExW failed (error {err})")
            self._hwnd = hwnd

            rid = RAWINPUTDEVICE(
                usUsagePage=HID_USAGE_PAGE_GENERIC,
                usUsage=HID_USAGE_GENERIC_KEYBOARD,
                dwFlags=RIDEV_INPUTSINK,
                hwndTarget=hwnd,
            )
            ok = self._user32.RegisterRawInputDevices(
                ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)
            )
            if not ok:
                err = ctypes.get_last_error()
                raise OSError(err, f"RegisterRawInputDevices failed (error {err})")

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
            if self._hwnd:
                # Unregister the device first; passing RIDEV_REMOVE requires
                # hwndTarget to be NULL.
                rid_off = RAWINPUTDEVICE(
                    usUsagePage=HID_USAGE_PAGE_GENERIC,
                    usUsage=HID_USAGE_GENERIC_KEYBOARD,
                    dwFlags=RIDEV_REMOVE,
                    hwndTarget=None,
                )
                self._user32.RegisterRawInputDevices(
                    ctypes.byref(rid_off), 1, ctypes.sizeof(RAWINPUTDEVICE)
                )
                self._user32.DestroyWindow(self._hwnd)
                self._hwnd = 0
            if self._class_atom:
                self._user32.UnregisterClassW(self._CLASS_NAME, self._kernel32.GetModuleHandleW(None))
                self._class_atom = 0
            self._proc_ref = None

    # ----- WM_INPUT handler -----
    def _handle_wm_input(self, lparam: int) -> None:
        size = wintypes.UINT(self._buf_size)
        n = self._user32.GetRawInputData(
            lparam, RID_INPUT, ctypes.byref(self._buf),
            ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER),
        )
        if n == 0xFFFFFFFF or n == 0:
            return
        ri = ctypes.cast(self._buf, ctypes.POINTER(RAWINPUT))[0]
        if ri.header.dwType != RIM_TYPEKEYBOARD:
            return

        kb = ri.data.keyboard
        vk = int(kb.VKey)
        # Pause/Break and similar arrive as an E1 escape sequence whose
        # first half has VKey == 0xFF — the second half carries the real
        # VK. Drop the placeholder so we don't spuriously count it.
        if vk == VK_IGNORE:
            return

        message = int(kb.Message)
        if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kind = EventKind.DOWN
        elif message in (WM_KEYUP, WM_SYSKEYUP):
            kind = EventKind.UP
        else:
            return

        ev = KeyEvent(
            kind=kind,
            vk=vk,
            scancode=int(kb.MakeCode),
            extended=bool(kb.Flags & RI_KEY_E0),
            timestamp_ms=int(time.time() * 1000),
            is_repeat=False,  # auto-repeat detection happens in the aggregator
        )
        self._listener(ev)

"""Windows-only window chrome tweaks.

Enables the immersive dark title bar on Windows 10 1809+ / Windows 11
via DwmSetWindowAttribute. No-op on unsupported builds.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19  # Windows 10 builds 18985..19041


def apply_dark_titlebar(hwnd: int) -> bool:
    """Tell DWM to render this window's title bar in dark mode.

    Returns True on success. Silently no-ops off-Windows.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        return False

    set_attr = dwmapi.DwmSetWindowAttribute
    set_attr.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    set_attr.restype = ctypes.c_long  # HRESULT

    value = ctypes.c_int(1)
    for attr in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY):
        hr = set_attr(wintypes.HWND(hwnd), attr, ctypes.byref(value), ctypes.sizeof(value))
        if hr == 0:
            return True
    return False

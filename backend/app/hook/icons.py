"""Estrazione icona da exe Win32 → PNG bytes via GDI + Pillow.

`extract_icon_png(exe_path, size=32)` ritorna un PNG (bytes) della prima
icona dell'exe, o None se l'extraction fallisce. Può fallire in modo
silenzioso (per design) per:
  - exe senza risorse icona (rare ma esistono);
  - app UWP virtualizzate (hbmColor a 0);
  - file non accessibili (path con caratteri speciali, exe rimosso).

Le chiamate GDI vengono fatte con cleanup robusto in `finally`: se non
liberi `HICON`/`HBITMAP` accumuli handle leak (User Object Quota = 10000
default per processo).
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from io import BytesIO

log = logging.getLogger(__name__)


# ---------- structs ----------
class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),  # padding per varianti BI_BITFIELDS
    ]


# ---------- DLL setup ----------
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
    wintypes.UINT,
]
_shell32.ExtractIconExW.restype = wintypes.UINT

_user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
_user32.GetIconInfo.restype = wintypes.BOOL

_user32.DestroyIcon.argtypes = [wintypes.HICON]
_user32.DestroyIcon.restype = wintypes.BOOL

_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC

_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int

_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
_gdi32.GetObjectW.restype = ctypes.c_int

_gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    wintypes.LPVOID, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
]
_gdi32.GetDIBits.restype = ctypes.c_int

_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
_gdi32.DeleteObject.restype = wintypes.BOOL

DIB_RGB_COLORS = 0
BI_RGB = 0


def _hicon_to_pil_image(hicon: int):
    """HICON → PIL.Image RGBA. None se l'estrazione GDI fallisce."""
    from PIL import Image  # import lazy: Pillow è dep nuova

    info = ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None

    color_bm = info.hbmColor
    mask_bm = info.hbmMask
    try:
        if not color_bm:
            # Icona monocromatica (rara): hbmColor è 0, l'immagine è in
            # hbmMask come due metà verticalmente impilate (AND mask + XOR).
            # Non vale la pena gestirla — bucket fallback.
            return None

        bm = BITMAP()
        if not _gdi32.GetObjectW(color_bm, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
            return None

        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None

        hdc = _user32.GetDC(None)
        if not hdc:
            return None
        try:
            bi = BITMAPINFO()
            bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bi.bmiHeader.biWidth = w
            # biHeight negativo = top-down DIB: senza questo dovremmo flip
            # verticalmente ogni icona dopo il decode.
            bi.bmiHeader.biHeight = -h
            bi.bmiHeader.biPlanes = 1
            bi.bmiHeader.biBitCount = 32
            bi.bmiHeader.biCompression = BI_RGB

            buf_size = w * h * 4
            buf = (ctypes.c_ubyte * buf_size)()
            scanlines = _gdi32.GetDIBits(
                hdc, color_bm, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS,
            )
            if scanlines == 0:
                return None

            # Windows 32bpp = BGRA. Pillow accepts that as raw mode.
            return Image.frombytes("RGBA", (w, h), bytes(buf), "raw", "BGRA")
        finally:
            _user32.ReleaseDC(None, hdc)
    finally:
        if color_bm:
            _gdi32.DeleteObject(color_bm)
        if mask_bm:
            _gdi32.DeleteObject(mask_bm)


def extract_icon_png(exe_path: str, size: int = 32) -> bytes | None:
    """Estrae la prima icona di `exe_path` come PNG bytes RGBA `size`x`size`.

    Ritorna None se l'extraction fallisce. Il caller decide se lasciare
    quel record senza icona (frontend mostra placeholder) o riprovare.
    """
    if not exe_path:
        return None

    large = wintypes.HICON(0)
    small = wintypes.HICON(0)
    # Index 0 = prima icona. Richiediamo sia large che small così copriamo
    # i casi in cui solo una delle due è presente.
    n = _shell32.ExtractIconExW(
        exe_path, 0,
        ctypes.byref(large), ctypes.byref(small), 1,
    )
    if n == 0xFFFFFFFF or n == 0:
        return None

    hicon = large.value or small.value
    if not hicon:
        if large.value:
            _user32.DestroyIcon(large)
        if small.value:
            _user32.DestroyIcon(small)
        return None

    try:
        img = _hicon_to_pil_image(hicon)
        if img is None:
            return None

        if img.size != (size, size):
            from PIL import Image
            img = img.resize((size, size), Image.LANCZOS)

        out = BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        log.exception("icon extraction failed for %s", exe_path)
        return None
    finally:
        # DestroyIcon su entrambi i pointer alzati da ExtractIconEx, anche
        # quello che non abbiamo usato.
        if large.value:
            _user32.DestroyIcon(large)
        if small.value and small.value != large.value:
            _user32.DestroyIcon(small)

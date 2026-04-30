"""Generate KeyLife brand assets: logo.png + multi-resolution .ico.

Renders the same shape painted at runtime by `app.ui.qt.main_window._brand_icon`:
a rounded square in the accent color with a white bold "K". Output:

    assets/logo.png       1024x1024 PNG
    assets/keylife.ico    multi-resolution Windows icon (16, 24, 32, 48, 64, 128, 256)

Run from the repo root:

    python tools/make_icons.py
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication

ACCENT = "#7c5cff"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
LOGO_SIZE = 1024

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.22
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI", int(size * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRect(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), "K")
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, images: list[QImage]) -> None:
    """Write a Windows .ico that embeds each image as a PNG payload.

    Vista and later accept PNG-encoded entries inside ICO. Sizes >= 256 use
    the special width/height byte = 0 sentinel.
    """
    pngs = [png_bytes(im) for im in images]
    n = len(images)

    out = io.BytesIO()
    # ICONDIR: reserved=0, type=1 (ICO), count
    out.write(struct.pack("<HHH", 0, 1, n))

    header_size = 6 + 16 * n
    offsets = []
    cursor = header_size
    for png in pngs:
        offsets.append(cursor)
        cursor += len(png)

    for img, png, offset in zip(images, pngs, offsets):
        w = img.width()
        h = img.height()
        # 256 is encoded as 0 in the byte fields.
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        # ICONDIRENTRY: width(B) height(B) colors(B) reserved(B)
        # planes(H) bpp(H) bytesInRes(I) imageOffset(I)
        out.write(struct.pack(
            "<BBBBHHII",
            bw, bh, 0, 0, 1, 32, len(png), offset,
        ))
    for png in pngs:
        out.write(png)

    path.write_bytes(out.getvalue())


def main() -> int:
    # Need a Qt application for font rendering even though we never show a window.
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app  # keep alive

    ASSETS.mkdir(parents=True, exist_ok=True)

    # PNG logo (large, high quality).
    logo = render(LOGO_SIZE)
    logo_path = ASSETS / "logo.png"
    logo.save(str(logo_path), "PNG")

    # Multi-resolution .ico.
    ico_imgs = [render(s) for s in ICO_SIZES]
    ico_path = ASSETS / "keylife.ico"
    write_ico(ico_path, ico_imgs)

    print(f"wrote {logo_path}  ({logo_path.stat().st_size} bytes)")
    print(f"wrote {ico_path}   ({ico_path.stat().st_size} bytes, {len(ICO_SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

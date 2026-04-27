"""Last-key display: a single keycap that pulses on each new keypress.

Privacy: only the most recent key is shown, replaced on every press. No
history, no timestamps, no persistence — consistent with the monitor's
"only aggregate counts, never reconstructable sequences" model.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.hook.events import EventKind, KeyEvent
from app.hook.vk_codes import pretty_name


class HookBridge(QObject):
    """Marshals hook events from the hook thread to the Qt main thread.

    The daemon's listener fires on the hook thread; emitting a Qt signal
    with AutoConnection delivers it to slots in the main thread via the
    Qt event loop.
    """

    keyDown = Signal(int)  # vk

    def on_event(self, ev: KeyEvent) -> None:
        # Skip auto-repeat: a single physical press should pulse once.
        if ev.kind is EventKind.DOWN and not ev.is_repeat:
            self.keyDown.emit(ev.vk)


class KeyDisplay(QWidget):
    """A keycap that flashes the accent color on each new keypress."""

    PULSE_MS = 320
    _CARD_BG = QColor("#1a1d24")
    _CARD_BORDER = QColor("#232732")
    _CAP_BASE = QColor("#232732")
    _CAP_BORDER = QColor("#2c313d")
    _CAP_BORDER_HOT = QColor("#3a3450")
    _ACCENT = QColor("#7c5cff")
    _LABEL_COLOR = QColor("#8a93a6")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        # Default to expanding; StatsPage drives a square setFixedSize() that
        # tracks the "Today" card's height.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._text: str = "—"
        self._pulse: float = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.PULSE_MS)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_pulse)

    def show_key(self, vk: int) -> None:
        self._text = pretty_name(vk)
        self._anim.stop()
        self._anim.start()

    def _on_pulse(self, v) -> None:
        self._pulse = float(v)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Card background
        p.setBrush(self._CARD_BG)
        p.setPen(QPen(self._CARD_BORDER, 1))
        p.drawRoundedRect(rect, 12, 12)

        # Keycap geometry: square, centered, fills most of the card.
        # Slightly shrinks during the press pulse.
        side_base = min(rect.width(), rect.height()) - 20
        scale = 1.0 - 0.07 * self._pulse
        side = side_base * scale
        cap = QRectF(0, 0, side, side)
        cap.moveCenter(rect.center())

        # Cap fill: lerp base → accent with pulse
        t = self._pulse * 0.85
        fill = QColor(
            int(self._CAP_BASE.red() + (self._ACCENT.red() - self._CAP_BASE.red()) * t),
            int(self._CAP_BASE.green() + (self._ACCENT.green() - self._CAP_BASE.green()) * t),
            int(self._CAP_BASE.blue() + (self._ACCENT.blue() - self._CAP_BASE.blue()) * t),
        )
        border = self._CAP_BORDER_HOT if self._pulse > 0.05 else self._CAP_BORDER
        p.setBrush(fill)
        p.setPen(QPen(border, 1.5))
        radius = max(8.0, side * 0.14)
        p.drawRoundedRect(cap, radius, radius)

        # Key label — font size adapts to label length
        text = self._text
        n = len(text)
        if n <= 2:
            size = max(20, int(side * 0.42))
        elif n <= 5:
            size = max(14, int(side * 0.24))
        else:
            size = max(11, int(side * 0.16))
        cap_font = QFont("Segoe UI Variable Display", size)
        cap_font.setBold(True)
        p.setFont(cap_font)
        p.setPen(QColor("#ffffff") if self._pulse > 0.15 else QColor("#e6e8ee"))
        p.drawText(cap, int(Qt.AlignmentFlag.AlignCenter), text)
        p.end()

"""Stats tab: Today / Session / All-time KPIs + Top 5 keys today."""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.hook.vk_codes import pretty_name as vk_pretty
from app.service.daemon import KeyLifeDaemon
from app.storage.repository import all_time_total, today_total, top_keys_today
from app.storage.session import get_sessionmaker
from app.ui.qt.key_display import HookBridge, KeyDisplay

log = logging.getLogger(__name__)

# Aggregator session_view() is cheap (lock + dict copy). DB SUMs on
# DailyKeyCount are sub-millisecond. One timer drives both.
TICK_MS = 500


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _kpi_card(
    label_text: str, value_object_name: str = "kpiValue", hero: bool = False
) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("cardHero" if hero else "card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 18)
    lay.setSpacing(6)
    lbl = QLabel(label_text.upper())
    lbl.setObjectName("kpiLabel")
    val = QLabel("0")
    val.setObjectName(value_object_name)
    if hero:
        glow = QGraphicsDropShadowEffect(val)
        glow.setBlurRadius(18)
        glow.setOffset(0, 0)
        glow.setColor(QColor(124, 92, 255, 90))
        val.setGraphicsEffect(glow)
    lay.addWidget(lbl)
    lay.addWidget(val)
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return card, val


class _CounterAnim:
    """Smoothly animate a QLabel from its current integer value to a new one."""

    def __init__(self, label: QLabel, duration_ms: int = 320) -> None:
        self._label = label
        self._current = 0
        self._anim = QVariantAnimation(label)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)

    def _on_value(self, v) -> None:
        self._label.setText(_fmt(int(v)))

    def set(self, target: int) -> None:
        if target == self._current:
            return
        self._anim.stop()
        self._anim.setStartValue(int(self._current))
        self._anim.setEndValue(int(target))
        self._current = target
        self._anim.start()


class StatsPage(QWidget):
    def __init__(
        self,
        daemon: KeyLifeDaemon,
        bridge: HookBridge,
        api_url: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._daemon = daemon
        # Read-only Sessions for the UI. Safe alongside the daemon's writer
        # thread because SQLite WAL allows concurrent readers; each Session
        # opens its own short-lived Connection.
        self._SessionLocal = get_sessionmaker()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # Top grid:
        #   col 0..1 — KPI cards (Today hero spans both columns; Session/All-time below)
        #   col 2    — KeyDisplay (square, height tracks the Today card) + Open Dashboard button
        top_grid = QGridLayout()
        top_grid.setSpacing(12)
        c1, self.lbl_today = _kpi_card("Today", "kpiAccent", hero=True)
        c2, self.lbl_session = _kpi_card("Session")
        c3, self.lbl_alltime = _kpi_card("All-time")
        top_grid.addWidget(c1, 0, 0, 1, 2)
        top_grid.addWidget(c2, 1, 0)
        top_grid.addWidget(c3, 1, 1)
        top_grid.setColumnStretch(0, 1)
        top_grid.setColumnStretch(1, 1)
        top_grid.setColumnStretch(2, 0)

        self.key_display = KeyDisplay()
        bridge.keyDown.connect(self.key_display.show_key)
        top_grid.addWidget(self.key_display, 0, 2)

        self.web_btn = QPushButton("WEB\n↗")
        self.web_btn.setObjectName("primary")
        self.web_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.web_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        web_font = QFont("Segoe UI Variable Display")
        web_font.setPointSize(18)
        web_font.setBold(True)
        web_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self.web_btn.setFont(web_font)
        if api_url:
            self._api_url = api_url
            self.web_btn.setToolTip(api_url)
            self.web_btn.clicked.connect(self._open_web)
        else:
            self._api_url = None
            self.web_btn.setEnabled(False)
            self.web_btn.setToolTip("Run with --api to enable the web dashboard")
        top_grid.addWidget(self.web_btn, 1, 2)
        root.addLayout(top_grid)

        # Track the Today hero card's height to keep KeyDisplay square at the
        # same height. The card auto-sizes from its font metrics, so a static
        # constant would drift if Qt scaling changes.
        self._today_card = c1
        c1.installEventFilter(self)

        self._anim_today = _CounterAnim(self.lbl_today)
        self._anim_session = _CounterAnim(self.lbl_session)
        self._anim_alltime = _CounterAnim(self.lbl_alltime)

        # Top keys table
        top_card = QFrame()
        top_card.setObjectName("card")
        tl = QVBoxLayout(top_card)
        tl.setContentsMargins(18, 16, 18, 16)
        tl.setSpacing(8)
        tl.addWidget(QLabel("TOP 5 KEYS TODAY", objectName="kpiLabel"))

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["KEY", "PRESSES"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tbl.setShowGrid(False)
        h = self.tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tl.addWidget(self.tbl)
        root.addWidget(top_card)

        # Status row + flush countdown
        bottom = QHBoxLayout()
        self.status = QLabel("● HOOK ACTIVE")
        self.status.setObjectName("statusOk")
        bottom.addWidget(self.status)
        bottom.addStretch(1)

        self.lbl_flush = QLabel("NEXT FLUSH")
        self.lbl_flush.setObjectName("kpiLabel")
        bottom.addWidget(self.lbl_flush)

        self.flush_bar = QProgressBar()
        self.flush_bar.setObjectName("flushBar")
        self.flush_bar.setRange(0, 1000)
        self.flush_bar.setValue(1000)
        self.flush_bar.setTextVisible(False)
        self.flush_bar.setFixedWidth(160)
        self.flush_bar.setFixedHeight(6)
        bottom.addWidget(self.flush_bar)

        self.lbl_flush_eta = QLabel("--s")
        self.lbl_flush_eta.setObjectName("kpiLabel")
        self.lbl_flush_eta.setFixedWidth(36)
        self.lbl_flush_eta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.lbl_flush_eta)

        root.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def eventFilter(self, obj, event):  # noqa: N802 — Qt override
        if obj is self._today_card and event.type() == QEvent.Type.Resize:
            h = self._today_card.height()
            if h > 0:
                self.key_display.setFixedSize(h, h)
                # Match the button to the keycap: same square size, stacked below.
                self.web_btn.setFixedSize(h, h)
        return super().eventFilter(obj, event)

    def _open_web(self) -> None:
        if self._api_url:
            QDesktopServices.openUrl(QUrl(self._api_url))

    def _tick(self) -> None:
        # Live session view: lock-protected, in-memory.
        sess_total, _ = self._daemon.aggregator.session_view()
        self._anim_session.set(sess_total)

        # DB reads. SQLite WAL allows concurrent readers alongside the
        # daemon's writer thread; we open a fresh Session per tick.
        try:
            with self._SessionLocal() as s:
                today = today_total(s)
                alltime = all_time_total(s)
                top = top_keys_today(s, limit=5)
        except Exception:
            log.exception("stats query failed")
            return

        self._anim_today.set(today)
        self._anim_alltime.set(alltime)
        self._fill_top(top)

        # Flush countdown bar: empties as we approach the next flush.
        interval = self._daemon.flush_interval_seconds
        remaining = self._daemon.seconds_until_next_flush()
        if interval > 0:
            self.flush_bar.setValue(int(remaining / interval * 1000))
        self.lbl_flush_eta.setText(f"{int(remaining)}s")

    def _fill_top(self, rows: list[tuple[int, int, int]]) -> None:
        self.tbl.setRowCount(len(rows))
        for i, (vk, _sc, cnt) in enumerate(rows):
            name = QTableWidgetItem(vk_pretty(vk))
            count = QTableWidgetItem(_fmt(cnt))
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl.setItem(i, 0, name)
            self.tbl.setItem(i, 1, count)
        if not rows:
            self.tbl.setRowCount(1)
            placeholder = QTableWidgetItem("(no key presses recorded today)")
            placeholder.setForeground(Qt.GlobalColor.gray)
            self.tbl.setItem(0, 0, placeholder)
            self.tbl.setSpan(0, 0, 1, 2)

    def set_status(self, ok: bool, text: str) -> None:
        self.status.setObjectName("statusOk" if ok else "statusBad")
        self.status.setText(text)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

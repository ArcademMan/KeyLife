"""Settings tab: DB folder, autostart, start minimized, flush interval."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import get_settings
from app.service.daemon import KeyLifeDaemon
from app.ui.qt import autostart, ui_state

log = logging.getLogger(__name__)


def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    lbl = QLabel(title.upper())
    lbl.setObjectName("kpiLabel")
    lay.addWidget(lbl)
    return card, lay


class SettingsPage(QWidget):
    def __init__(
        self,
        daemon: KeyLifeDaemon | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = get_settings()
        self._daemon = daemon
        self._state = ui_state.load()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        root.addWidget(self._db_section())
        root.addWidget(self._flush_section())
        root.addWidget(self._startup_section())
        root.addStretch(1)
        root.addWidget(self._about_row())

    def _db_section(self) -> QFrame:
        card, lay = _section("Database")
        path_lbl = QLabel(str(self._settings.db_path))
        path_lbl.setObjectName("mono")
        path_lbl.setWordWrap(True)
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(path_lbl)

        btn_row = QHBoxLayout()
        btn = QPushButton("Open folder")
        btn.clicked.connect(self._open_db_folder)
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        return card

    def _flush_section(self) -> QFrame:
        card, lay = _section("Flush interval")

        # Effective interval: live daemon value if available, else saved
        # override, else the pydantic-settings default.
        if self._daemon is not None:
            current = int(round(self._daemon.flush_interval_seconds))
        elif self._state.flush_interval_seconds is not None:
            current = int(round(self._state.flush_interval_seconds))
        else:
            current = int(round(self._settings.flush_interval_seconds))

        row = QHBoxLayout()
        self.spin_flush = QSpinBox()
        self.spin_flush.setRange(1, 3600)
        self.spin_flush.setSuffix(" s")
        self.spin_flush.setValue(max(1, min(3600, current)))
        self.spin_flush.setFixedWidth(110)
        self.spin_flush.editingFinished.connect(self._on_flush_committed)
        row.addWidget(self.spin_flush)
        row.addStretch(1)
        lay.addLayout(row)

        hint = QLabel(
            "How often the in-memory counters are written to the database. "
            "Shorter values write more often; longer values batch more counts."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return card

    def _startup_section(self) -> QFrame:
        card, lay = _section("Startup")

        self.cb_autostart = QCheckBox("Start KeyLife at Windows sign-in")
        self.cb_autostart.setChecked(autostart.is_enabled())
        self.cb_autostart.toggled.connect(self._on_autostart_toggled)
        lay.addWidget(self.cb_autostart)

        self.cb_minimized = QCheckBox("Start minimized to system tray")
        self.cb_minimized.setChecked(self._state.start_minimized)
        self.cb_minimized.toggled.connect(self._on_minimized_toggled)
        lay.addWidget(self.cb_minimized)

        hint = QLabel(
            "The tray icon lets you reopen the window or quit."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return card

    def _about_row(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 0, 4, 0)
        h.addWidget(QLabel("KeyLife · v0.1.0", objectName="muted"))
        h.addStretch(1)
        h.addWidget(QLabel(f"DB: {self._settings.db_filename}", objectName="muted"))
        return w

    # --- handlers ---

    def _open_db_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._settings.data_dir)))

    def _on_autostart_toggled(self, checked: bool) -> None:
        try:
            if checked:
                autostart.enable()
            else:
                autostart.disable()
        except OSError:
            log.exception("autostart toggle failed")
            # Roll back the checkbox to the truth from registry.
            self.cb_autostart.blockSignals(True)
            self.cb_autostart.setChecked(autostart.is_enabled())
            self.cb_autostart.blockSignals(False)

    def _on_minimized_toggled(self, checked: bool) -> None:
        self._state.start_minimized = checked
        try:
            ui_state.save(self._state)
        except OSError:
            log.exception("ui_state save failed")

    def _on_flush_committed(self) -> None:
        seconds = float(self.spin_flush.value())
        if self._daemon is not None:
            self._daemon.set_flush_interval(seconds)
        self._state.flush_interval_seconds = seconds
        try:
            ui_state.save(self._state)
        except OSError:
            log.exception("ui_state save failed")

"""Single QSS string applied app-wide. Dark theme, one accent color."""

from __future__ import annotations

ACCENT = "#7c5cff"

QSS = """
* {
    color: #e6e8ee;
    font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #14171f, stop:0.55 #0f1115, stop:1 #0c0e13
    );
}
QWidget#root { background: transparent; }

/* tabs */
QTabWidget::pane {
    border: none;
    background: transparent;
    top: -1px;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: #8a93a6;
    padding: 10px 22px;
    border: none;
    margin-right: 2px;
}
QTabBar::tab:hover { color: #c2c8d6; }
QTabBar::tab:selected {
    color: #e6e8ee;
    border-bottom: 2px solid #7c5cff;
}

/* cards */
QFrame#card {
    background: #1a1d24;
    border-radius: 12px;
    border: 1px solid #232732;
}
QFrame#card:hover {
    border: 1px solid #3a3450;
    background: #1c1f27;
}
QFrame#cardHero {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #1f1a35, stop:1 #1a1d24
    );
    border-radius: 12px;
    border: 1px solid #2e2748;
}
QFrame#cardHero:hover {
    border: 1px solid #4a3d7a;
}

/* KPI typography */
QLabel#kpiLabel {
    color: #8a93a6;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
}
QLabel#kpiValue {
    color: #e6e8ee;
    font-size: 34px;
    font-weight: 700;
}
QLabel#kpiAccent {
    color: #b6a3ff;
    font-size: 38px;
    font-weight: 700;
}

/* misc text */
QLabel#sectionTitle {
    color: #8a93a6;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    margin-top: 6px;
}
QLabel#muted { color: #8a93a6; font-size: 11px; }
QLabel#mono {
    font-family: "Consolas", "JetBrains Mono", monospace;
    color: #c2c8d6;
}

/* buttons */
QPushButton {
    background: #232732;
    border: 1px solid #2c313d;
    border-radius: 6px;
    padding: 6px 14px;
    color: #e6e8ee;
}
QPushButton:hover { background: #2c313d; }
QPushButton:pressed { background: #1a1d24; }
QPushButton#primary {
    background: #7c5cff;
    border-color: #7c5cff;
    color: #ffffff;
}
QPushButton#primary:hover { background: #8e72ff; }

/* checkbox */
QCheckBox { spacing: 10px; color: #e6e8ee; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #2c313d;
    background: #1a1d24;
}
QCheckBox::indicator:hover { border-color: #3a4050; }
QCheckBox::indicator:checked {
    background: #7c5cff;
    border-color: #7c5cff;
    image: none;
}

/* table */
QTableWidget {
    background: transparent;
    border: none;
    gridline-color: transparent;
    color: #e6e8ee;
    selection-background-color: #2c313d;
    selection-color: #e6e8ee;
    outline: 0;
}
QTableWidget QTableCornerButton::section {
    background: transparent;
    border: none;
}
QTableWidget::item {
    padding: 8px 6px;
    border: none;
    border-bottom: 1px solid #232732;
}
QTableWidget::item:selected { background: #232732; }

QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: transparent;
    color: #6c7488;
    border: none;
    border-bottom: 1px solid #2c313d;
    padding: 6px 6px 8px 6px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
}
QHeaderView::section:first { padding-left: 2px; }
QHeaderView::section:last { padding-right: 2px; }
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2c313d;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #3a4050; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* menus (tray context menu, etc.) */
QMenu {
    background: #1a1d24;
    border: 1px solid #2c313d;
    border-radius: 8px;
    padding: 6px;
    color: #e6e8ee;
}
QMenu::item {
    background: transparent;
    padding: 6px 18px;
    border-radius: 4px;
    margin: 1px 2px;
}
QMenu::item:selected {
    background: #2c313d;
    color: #ffffff;
}
QMenu::item:disabled { color: #6c7488; }
QMenu::separator {
    height: 1px;
    background: #2c313d;
    margin: 4px 6px;
}

/* status pill */
QLabel#statusOk {
    color: #46c66f;
    font-size: 11px;
    letter-spacing: 1px;
}
QLabel#statusBad {
    color: #e06c6c;
    font-size: 11px;
    letter-spacing: 1px;
}

/* spin box */
QSpinBox, QDoubleSpinBox {
    background: #1a1d24;
    color: #e6e8ee;
    border: 1px solid #2c313d;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #7c5cff;
    selection-color: #ffffff;
    min-height: 22px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #3a3f4d;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #7c5cff;
    background: #1d2029;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: transparent;
    border: none;
    width: 18px;
    subcontrol-origin: border;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    margin-right: 2px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    margin-right: 2px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #232732;
    border-radius: 3px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #8a93a6;
    width: 0; height: 0;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8a93a6;
    width: 0; height: 0;
}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {
    border-bottom-color: #e6e8ee;
}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {
    border-top-color: #e6e8ee;
}
QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #5a6173;
    background: #14171f;
    border-color: #1f232c;
}

/* flush countdown bar */
QProgressBar#flushBar {
    background: #232732;
    border: none;
    border-radius: 3px;
}
QProgressBar#flushBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c5cff, stop:1 #5b8cff
    );
    border-radius: 3px;
}
"""

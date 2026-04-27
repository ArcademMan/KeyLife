"""Qt main window + system tray + entry point.

This is the default user-facing UI. The legacy Tk monitor stays available
behind --monitor for hook debugging.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QSystemTrayIcon,
    QMenu,
    QTabWidget,
)

from app.service.daemon import KeyLifeDaemon
from app.ui.qt import ui_state
from app.ui.qt.key_display import HookBridge
from app.ui.qt.settings_page import SettingsPage
from app.ui.qt.stats_page import StatsPage
from app.ui.qt.style import ACCENT, QSS
from app.ui.qt.win_chrome import apply_dark_titlebar

log = logging.getLogger(__name__)


def _brand_icon(size: int = 64) -> QIcon:
    """A small painted icon: rounded square in accent color with a 'K'.

    Avoids shipping any asset file.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.22
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI", int(size * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "K")
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(
        self,
        daemon: KeyLifeDaemon,
        bridge: HookBridge,
        api_url: str | None = None,
    ) -> None:
        super().__init__()
        self._daemon = daemon
        self._allow_close = False  # set True only when user really quits

        self.setWindowTitle("KeyLife")
        self.setWindowIcon(_brand_icon())
        self.resize(720, 560)
        self.setMinimumSize(QSize(620, 480))

        tabs = QTabWidget()
        tabs.setObjectName("root")
        tabs.setDocumentMode(True)
        self.stats = StatsPage(daemon, bridge, api_url=api_url)
        self.settings_page = SettingsPage(daemon=daemon)
        tabs.addTab(self.stats, "Stats")
        tabs.addTab(self.settings_page, "Settings")
        self.setCentralWidget(tabs)

    def showEvent(self, event):  # noqa: N802 — Qt override
        super().showEvent(event)
        # Re-apply on every show: Windows resets the title-bar theme when a
        # window is hidden to the tray and shown again.
        apply_dark_titlebar(int(self.winId()))

    def closeEvent(self, event):  # noqa: N802 — Qt override
        # Hide to tray on the user's window-close, unless we're actually quitting.
        if self._allow_close or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        event.ignore()
        self.hide()

    def request_quit(self) -> None:
        self._allow_close = True
        self.close()


class TrayController:
    def __init__(self, app: QApplication, window: MainWindow, daemon: KeyLifeDaemon) -> None:
        self.app = app
        self.window = window
        self.daemon = daemon
        self.tray = QSystemTrayIcon(_brand_icon(), parent=app)
        self.tray.setToolTip("KeyLife")

        menu = QMenu()
        act_open = QAction("Open", menu)
        act_open.triggered.connect(self._show)
        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _show(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self._show()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show()

    def _quit(self) -> None:
        try:
            self.daemon.stop()
        except Exception:
            log.exception("daemon stop failed during quit")
        self.tray.hide()
        self.window.request_quit()
        self.app.quit()


def _start_api_thread(daemon: KeyLifeDaemon):
    """Run uvicorn in a background thread, sharing the Qt daemon.

    Returns (server, thread). Caller must `server.should_exit = True` and
    join the thread to shut it down cleanly.
    """
    import uvicorn

    from app.api.server import build_app
    from app.core.config import get_settings

    settings = get_settings()
    app = build_app(daemon=daemon)
    config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        access_log=True,
        lifespan="on",
        # uvicorn's default LOGGING_CONFIG installs a ColourizedFormatter that
        # calls sys.stdout.isatty(); in the packaged build (console=False)
        # sys.stdout is None and the constructor crashes. Reuse the root
        # logger configured in app.__main__._setup_logging instead.
        log_config=None,
    )
    server = uvicorn.Server(config)

    def _serve() -> None:
        # uvicorn.Server.run() installs signal handlers, which only works on
        # the main thread. Drive the asyncio loop manually instead.
        try:
            asyncio.run(server.serve())
        except Exception:
            log.exception("uvicorn server crashed")

    t = threading.Thread(target=_serve, name="keylife-api", daemon=True)
    t.start()
    return server, t


def run(start_minimized: bool = False, with_api: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("KeyLife")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS)
    app.setWindowIcon(_brand_icon())

    bridge = HookBridge()
    daemon = KeyLifeDaemon(ui_listener=bridge.on_event)
    try:
        daemon.start()
    except TimeoutError as e:
        QMessageBox.critical(None, "KeyLife", f"Hook failed to start: {e}")
        return 1

    api_server = None
    api_thread = None
    api_url: str | None = None
    if with_api:
        try:
            api_server, api_thread = _start_api_thread(daemon)
            from app.core.config import get_settings
            s = get_settings()
            host = "127.0.0.1" if s.api_host in ("0.0.0.0", "::", "") else s.api_host
            api_url = f"http://{host}:{s.api_port}/"
        except Exception:
            log.exception("failed to start API server; continuing with UI only")

    window = MainWindow(daemon, bridge, api_url=api_url)

    state = ui_state.load()
    minimize = start_minimized or state.start_minimized
    if minimize and QSystemTrayIcon.isSystemTrayAvailable():
        window.hide()
    else:
        window.show()

    tray = TrayController(app, window, daemon)  # noqa: F841 — kept alive by ref

    rc = app.exec()
    if api_server is not None:
        api_server.should_exit = True
        if api_thread is not None:
            api_thread.join(timeout=5)
    # Final safety: if Qt exited without us routing through TrayController._quit
    # (e.g. logoff), make sure the daemon is stopped.
    try:
        daemon.stop()
    except Exception:
        log.exception("daemon stop on shutdown raised")
    return rc


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    sys.exit(run())


if __name__ == "__main__":
    main()

"""KeyLife entry point.

Usage:
  python -m app                  # launches Qt UI (default)
  python -m app --minimized      # Qt UI, starts hidden in the tray
  python -m app --headless       # daemon without UI
  python -m app --serve          # daemon + HTTP API + web UI on 127.0.0.1
  python -m app --monitor        # legacy Tk hook monitor (debug)
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from app.service.daemon import KeyLifeDaemon


def _run_headless() -> int:
    logging.info("KeyLife headless mode")
    daemon = KeyLifeDaemon()
    daemon.start()

    stop_evt = threading.Event()

    def _handle_sig(_signum, _frame):  # noqa: ANN001
        # Idempotent: a second Ctrl+C during shutdown must not perturb state.
        if not stop_evt.is_set():
            stop_evt.set()

    signal.signal(signal.SIGINT, _handle_sig)
    try:
        signal.signal(signal.SIGBREAK, _handle_sig)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    try:
        stop_evt.wait()
    finally:
        daemon.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keylife")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="run daemon without UI")
    mode.add_argument("--serve", action="store_true",
                      help="run daemon + HTTP API + web UI on loopback")
    mode.add_argument("--monitor", action="store_true", help="legacy Tk hook monitor")
    parser.add_argument(
        "--minimized", action="store_true",
        help="start the Qt UI hidden in the system tray",
    )
    parser.add_argument(
        "--api", action="store_true",
        help="also serve the HTTP API on loopback alongside the Qt UI",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )

    if args.headless:
        return _run_headless()

    if args.serve:
        from app.api.server import run as run_api
        run_api()
        return 0

    if args.monitor:
        from app.ui.monitor import MonitorApp
        MonitorApp().run()
        return 0

    from app.ui.qt.main_window import run as run_qt
    return run_qt(start_minimized=args.minimized, with_api=args.api)


if __name__ == "__main__":
    sys.exit(main())

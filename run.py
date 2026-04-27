"""Project launcher.

Boots the KeyLife daemon from the repo root:
  1. ensures `backend/` is on sys.path so `app` is importable;
  2. applies any pending Alembic migrations (no-op if already at head);
  3. launches `app.__main__:main`, forwarding CLI args.

Usage:
    python run.py                 # Qt UI + HTTP API (default)
    python run.py --serve         # headless: daemon + HTTP API + web UI on loopback
    python run.py --headless      # daemon without UI
    python run.py --log-level=DEBUG
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller bundle: data files live under sys._MEIPASS, code is already on sys.path.
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent

BACKEND = ROOT / "backend"

if not getattr(sys, "frozen", False) and str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    # Run with cwd=backend so any relative paths inside env.py resolve correctly.
    prev_cwd = os.getcwd()
    os.chdir(BACKEND)
    try:
        command.upgrade(cfg, "head")
    finally:
        os.chdir(prev_cwd)


def main() -> int:
    _run_migrations()
    from app.__main__ import main as app_main
    # No CLI args from the IDE? Default to Qt UI + API server.
    args = sys.argv[1:] or ["--api"]
    return app_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

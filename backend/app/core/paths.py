from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    # PyInstaller onedir: bundled data files live under sys._MEIPASS, mirroring
    # the source layout (PROJECT_ROOT/{backend,frontend,assets}).
    PROJECT_ROOT: Path = Path(sys._MEIPASS)
    BACKEND_DIR: Path = PROJECT_ROOT / "backend"
else:
    BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
    PROJECT_ROOT: Path = BACKEND_DIR.parent


def user_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "AmMstools" / "KeyLife"

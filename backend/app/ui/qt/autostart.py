"""Windows HKCU autostart helper.

Writes a single value under
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run that launches
KeyLife minimized at user logon. HKCU only — no admin needed.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from app.core.paths import PROJECT_ROOT

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "KeyLife"


def _runner_command() -> str:
    # Prefer pythonw.exe (no console window) if it sits next to the active
    # interpreter; otherwise fall back to whatever started us.
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    runner = pyw if pyw.is_file() else exe
    run_py = (PROJECT_ROOT / "run.py").resolve()
    return f'"{runner}" "{run_py}" --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            value, _ = winreg.QueryValueEx(k, _VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    cmd = _runner_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
        winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, cmd)


def disable() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE,
        ) as k:
            winreg.DeleteValue(k, _VALUE_NAME)
    except FileNotFoundError:
        pass

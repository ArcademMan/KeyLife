"""KeyLife package.

Single source of truth for the version is `pyproject.toml`. We expose it
here via `importlib.metadata` so the rest of the app (and the UI) can
read it without duplicating the literal.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("keylife")
except PackageNotFoundError:
    # Source checkout without an installed dist (e.g. running from the
    # repo without `pip install -e .`). Fall back to reading pyproject.toml.
    from pathlib import Path

    try:
        import tomllib  # 3.11+
    except ModuleNotFoundError:  # pragma: no cover — 3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]

    _pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        __version__ = tomllib.loads(_pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError):
        __version__ = "0.0.0+unknown"

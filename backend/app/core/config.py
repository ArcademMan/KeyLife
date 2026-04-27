from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import BACKEND_DIR, user_data_dir

# Sentinel value used as default. If this value is ever observed at runtime
# it means no real key was provisioned — we refuse to use it.
_PLACEHOLDER_SECRET = "dev-insecure-change-me"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="KEYLIFE_",
        extra="ignore",
    )

    # Storage
    data_dir: Path = Field(default_factory=user_data_dir)
    db_filename: str = "keylife.sqlite"

    # Daemon timing
    flush_interval_seconds: float = 60.0

    # UI
    ui_queue_max: int = 256

    # HTTP API (read-only, bound to loopback only — see api/server.py).
    api_host: str = "127.0.0.1"
    api_port: int = 48123

    # Secrets. Resolution happens in get_settings(): backend/.secret_key file
    # → KEYLIFE_SECRET_KEY env var → freshly generated file. The placeholder
    # below is a sentinel — get_settings() refuses to return it.
    secret_key: SecretStr = SecretStr(_PLACEHOLDER_SECRET)

    @property
    def db_path(self) -> Path:
        # Force a bare filename: KEYLIFE_DB_FILENAME is read from env, so an
        # attacker with env-var control could otherwise redirect the DB
        # outside data_dir via "../..". Strip any path component.
        name = os.path.basename(self.db_filename) or "keylife.sqlite"
        return self.data_dir / name

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


def _secret_key_path() -> Path:
    return BACKEND_DIR / ".secret_key"


def _load_secret_key_file() -> str | None:
    p = _secret_key_path()
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def _generate_secret_key_file() -> str:
    """Create backend/.secret_key with a fresh 32-byte token, mode 0o600.

    Returns the token. Safe against losing a race with another process: if
    the file already exists when we try to create it, we read the winner's
    value instead.
    """
    p = _secret_key_path()
    token = secrets.token_urlsafe(32)
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, token.encode("utf-8"))
        finally:
            os.close(fd)
        return token
    except FileExistsError:
        existing = _load_secret_key_file()
        if existing and existing != _PLACEHOLDER_SECRET:
            return existing
        raise RuntimeError(
            "backend/.secret_key exists but is empty or unreadable; "
            "delete it and retry"
        ) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Precedence: backend/.secret_key file → KEYLIFE_SECRET_KEY env var
    # (handled natively by pydantic-settings) → freshly generated file.
    overrides: dict[str, object] = {}
    sk = _load_secret_key_file()
    if sk and sk != _PLACEHOLDER_SECRET:
        overrides["secret_key"] = SecretStr(sk)

    s = Settings(**overrides)
    s.data_dir.mkdir(parents=True, exist_ok=True)

    if s.secret_key.get_secret_value() == _PLACEHOLDER_SECRET:
        # No file, no env var — generate one and reload.
        token = _generate_secret_key_file()
        s = Settings(secret_key=SecretStr(token))
        s.data_dir.mkdir(parents=True, exist_ok=True)

    return s

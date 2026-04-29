from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import BACKEND_DIR, user_data_dir

# Sentinel value used as default. If this value is ever observed at runtime
# it means no real key was provisioned — we refuse to use it.
_PLACEHOLDER_SECRET = "dev-insecure-change-me"  # noqa: S105

# Sentinel per la chiave del DB. get_settings() la sovrascrive sempre con il
# valore caricato dal Credential Manager (o appena generato): se questa
# costante arriva fino a SQLCipher significa che get_settings() è stato
# bypassato e ci rifiutiamo di aprire il DB.
_PLACEHOLDER_DB_KEY = "0" * 64  # noqa: S105

# Slot del Credential Manager dove vive la chiave del DB.
# username fisso, service-name diverso fra dev e build frozen così che
# checkout sorgente e exe installato non si rigenerino la chiave a vicenda
# rendendo illeggibile il DB dell'altro.
_KEYRING_USERNAME = "db"
_KEYRING_SERVICE_FROZEN = "KeyLife"
_KEYRING_SERVICE_DEV = "KeyLife-dev"


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

    # Chiave a 256 bit per SQLCipher, hex-encoded (64 char). Risolta in
    # get_settings() leggendo il Windows Credential Manager (o generandola
    # al primo avvio). Mai letta da env o da file: vive solo nel keychain.
    db_key: SecretStr = SecretStr(_PLACEHOLDER_DB_KEY)

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
    # In dev il file vive accanto al codice (in .gitignore). In modalità
    # frozen (PyInstaller) BACKEND_DIR è dentro la cartella di installazione
    # — read-only se installato in Program Files, e comunque sovrascritto a
    # ogni reinstall — quindi il segreto va con gli altri dati utente.
    if getattr(sys, "frozen", False):
        return user_data_dir() / ".secret_key"
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


def _keyring_service() -> str:
    return _KEYRING_SERVICE_FROZEN if getattr(sys, "frozen", False) else _KEYRING_SERVICE_DEV


def _load_db_key() -> str | None:
    """Read the DB key from Windows Credential Manager.

    Returns None if the entry doesn't exist OR if any keyring backend error
    happens — the caller decides whether that's "first run, generate one"
    or "configured DB exists but key is gone, abort".
    """
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return None
    try:
        v = keyring.get_password(_keyring_service(), _KEYRING_USERNAME)
    except KeyringError:
        return None
    return v or None


def _generate_db_key() -> str:
    """Generate 256 bit di entropia, salvali nel Credential Manager, restituisci hex.

    Hex form (64 char) viene consumato da SQLCipher come raw key:
    `PRAGMA key = "x'...'"` salta il PBKDF2 di derivazione (non ne abbiamo
    bisogno con una chiave random ad alta entropia) ed evita problemi di
    quoting/encoding sul valore della PRAGMA.
    """
    import keyring
    token = secrets.token_hex(32)
    keyring.set_password(_keyring_service(), _KEYRING_USERNAME, token)
    return token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # DB key first: se il Credential Manager è rotto/inaccessibile è meglio
    # saperlo prima di toccare data_dir o di scrivere il .secret_key.
    db_key_raw = _load_db_key()
    if db_key_raw is None:
        db_key_raw = _generate_db_key()
    if not db_key_raw or db_key_raw == _PLACEHOLDER_DB_KEY:
        raise RuntimeError("failed to provision a DB encryption key")

    # Precedence per secret_key: backend/.secret_key file → KEYLIFE_SECRET_KEY
    # env var (handled natively by pydantic-settings) → freshly generated file.
    overrides: dict[str, object] = {"db_key": SecretStr(db_key_raw)}
    sk = _load_secret_key_file()
    if sk and sk != _PLACEHOLDER_SECRET:
        overrides["secret_key"] = SecretStr(sk)

    s = Settings(**overrides)
    s.data_dir.mkdir(parents=True, exist_ok=True)

    if s.secret_key.get_secret_value() == _PLACEHOLDER_SECRET:
        # No file, no env var — generate one and reload.
        token = _generate_secret_key_file()
        s = Settings(secret_key=SecretStr(token), db_key=SecretStr(db_key_raw))
        s.data_dir.mkdir(parents=True, exist_ok=True)

    return s

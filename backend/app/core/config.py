from __future__ import annotations

import logging
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import BACKEND_DIR, user_data_dir

log = logging.getLogger(__name__)

# Sentinel per la chiave del DB. get_settings() la sovrascrive sempre con il
# valore caricato dal Credential Manager (o appena generato): se questa
# costante arriva fino a SQLCipher significa che get_settings() è stato
# bypassato e ci rifiutiamo di aprire il DB.
_PLACEHOLDER_DB_KEY = "0" * 64  # noqa: S105

# Slot del Credential Manager dove vive la chiave del DB.
# Unico slot per dev e build frozen: condividono lo stesso `data_dir` (e
# quindi lo stesso file DB), avere chiavi separate causerebbe HMAC fail
# alla prima volta che si passa da una modalità all'altra.
_KEYRING_SERVICE = "KeyLife"
_KEYRING_SERVICE_LEGACY_DEV = "KeyLife-dev"  # 0.3.0 only — fallback one-shot
_KEYRING_USERNAME = "db"


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


def _load_db_key() -> str | None:
    """Read the DB key from Windows Credential Manager.

    Tenta prima lo slot canonico `KeyLife/db`. Se vuoto, prova quello
    legacy `KeyLife-dev/db` introdotto in 0.3.0 e mai più scritto: se
    trovato, lo migra (copy + delete del legacy) così le invocazioni
    successive non rifaranno il fallback.
    Returns None quando la chiave non esiste in nessun posto.
    """
    try:
        import keyring
        from keyring.errors import KeyringError, PasswordDeleteError
    except ImportError:
        return None
    try:
        v = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except KeyringError:
        return None
    if v:
        return v

    # Fallback legacy 0.3.0: dev checkout aveva uno slot suo. Migra.
    try:
        legacy = keyring.get_password(_KEYRING_SERVICE_LEGACY_DEV, _KEYRING_USERNAME)
    except KeyringError:
        legacy = None
    if not legacy:
        return None
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, legacy)
        log.info("DB key migrated from legacy slot %s to %s",
                 _KEYRING_SERVICE_LEGACY_DEV, _KEYRING_SERVICE)
    except KeyringError:
        log.exception("could not migrate legacy DB key; continuing with legacy slot")
        return legacy
    try:
        keyring.delete_password(_KEYRING_SERVICE_LEGACY_DEV, _KEYRING_USERNAME)
    except (KeyringError, PasswordDeleteError):
        # Non fatale: la chiave nuova è già scritta e funziona.
        log.warning("legacy slot %s not deleted; harmless leftover",
                    _KEYRING_SERVICE_LEGACY_DEV)
    return legacy


def _generate_db_key() -> str:
    """Generate 256 bit di entropia, salvali nel Credential Manager, restituisci hex.

    Hex form (64 char) viene consumato da SQLCipher come raw key:
    `PRAGMA key = "x'...'"` salta il PBKDF2 di derivazione (non ne abbiamo
    bisogno con una chiave random ad alta entropia) ed evita problemi di
    quoting/encoding sul valore della PRAGMA.
    """
    import keyring
    token = secrets.token_hex(32)
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, token)
    return token


def _retire_legacy_secret_key_file() -> None:
    """Cancella il vecchio `.secret_key` se esiste.

    Era stato introdotto nell'audit di aprile come segreto generico
    "in caso servisse" (sign cookie / HMAC export / ...) ma nessuna
    feature lo ha mai usato. Da 0.3.1 viene rimosso: il file su disco è
    rumore privacy/confusione. Cancellazione idempotente, log INFO una volta.
    """
    candidates = (
        user_data_dir() / ".secret_key",
        BACKEND_DIR / ".secret_key",
    )
    for p in candidates:
        try:
            if p.is_file():
                p.unlink()
                log.info("retired unused .secret_key file at %s", p)
        except OSError:
            log.exception("could not remove %s; ignored", p)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    db_key_raw = _load_db_key()
    if db_key_raw is None:
        db_key_raw = _generate_db_key()
    if not db_key_raw or db_key_raw == _PLACEHOLDER_DB_KEY:
        raise RuntimeError("failed to provision a DB encryption key")

    s = Settings(db_key=SecretStr(db_key_raw))
    s.data_dir.mkdir(parents=True, exist_ok=True)

    # Cleanup del .secret_key dismesso (vedi docstring). One-shot ad ogni
    # avvio finché non è sparito; cheap (un is_file() check).
    _retire_legacy_secret_key_file()

    return s

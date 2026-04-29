"""Cifratura at-rest del DB SQLite via SQLCipher.

Tre operazioni:
  - `detect_db_state(path, key)`: classifica un file come missing/plaintext/
    encrypted_ok/unreadable, leggendo i magic byte e provando un'apertura
    con la chiave attuale.
  - `migrate_plaintext_to_encrypted(path, key)`: porta un DB plaintext
    esistente a SQLCipher, lasciando un backup `.pre-encrypt.bak`.
  - `open_sqlcipher(path)`: factory per `sqlcipher3.dbapi2.connect` usata
    dal `creator` di SQLAlchemy in `session.py`.

Threat model: questo modulo non protegge da malware in-process (la chiave
è leggibile dal processo). Protegge dalla copia del solo `data_dir`,
perché la chiave vive nel Windows Credential Manager (vedi config.py).
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

logger = logging.getLogger(__name__)

DbState = Literal["missing", "plaintext", "encrypted_ok", "unreadable"]

# Header SQLite plaintext, costante. Un DB cifrato con SQLCipher ha header
# random (la prima pagina è cifrata), quindi la presenza di questo magic
# è sufficiente per discriminare.
_SQLITE_MAGIC = b"SQLite format 3\x00"


def open_sqlcipher(path: Path | str):
    """Apri una connessione DB-API a SQLCipher senza applicare la chiave.

    Il caller (engine listener in session.py / env.py, oppure questo modulo
    durante la migrazione) è responsabile di emettere `PRAGMA key=...` come
    primo statement quando serve.
    """
    import sqlcipher3.dbapi2 as sqlcipher_dbapi

    return sqlcipher_dbapi.connect(
        str(path),
        check_same_thread=False,
        timeout=30,
        isolation_level=None,
    )


def detect_db_state(path: Path, key: SecretStr) -> DbState:
    """Classifica il DB sul disco senza modificarlo."""
    if not path.exists():
        return "missing"
    try:
        with path.open("rb") as f:
            header = f.read(16)
    except OSError:
        return "unreadable"
    if header == _SQLITE_MAGIC:
        return "plaintext"
    if _can_open_encrypted(path, key):
        return "encrypted_ok"
    return "unreadable"


def _can_open_encrypted(path: Path, key: SecretStr) -> bool:
    """True se `path` apre senza errori con la chiave fornita.

    SQLCipher non valida la chiave a `PRAGMA key`: lo fa al primo accesso
    a una pagina del DB. Forziamo quindi una lettura di `sqlite_master`.
    """
    try:
        conn = open_sqlcipher(path)
    except Exception:
        return False
    try:
        cur = conn.cursor()
        _apply_key(cur, key)
        cur.execute("SELECT count(*) FROM sqlite_master")
        cur.fetchone()
        return True
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _apply_key(cursor, key: SecretStr) -> None:
    """Emetti `PRAGMA key` in formato hex-blob.

    Hex blob (`x'...'`) salta il PBKDF2 e tratta i 32 byte come chiave
    raw — corretto perché la generiamo già con `secrets.token_hex(32)`.
    """
    hex_key = key.get_secret_value()
    cursor.execute(f"PRAGMA key = \"x'{hex_key}'\"")


def migrate_plaintext_to_encrypted(path: Path, key: SecretStr) -> None:
    """Cifra in-place il DB SQLite plaintext a `path`.

    Lascia un backup `<path>.pre-encrypt.bak` (cancellazione manuale a
    discrezione dell'utente). Atomico via `os.replace` su NTFS.

    Postcondizione: `path` apre solo con `key`. I sidecar `-wal`/`-shm`
    plaintext sono rimossi (sono incompatibili con il file cifrato).
    """
    if not path.is_file():
        raise FileNotFoundError(path)

    backup_path = path.with_suffix(path.suffix + ".pre-encrypt.bak")
    tmp_path = path.with_suffix(path.suffix + ".encrypted.tmp")

    if tmp_path.exists():
        # Residuo di un tentativo precedente fallito a metà — rimuoverlo
        # non distrugge dati: il DB plaintext originale è ancora a `path`.
        tmp_path.unlink()

    # 1. Checkpoint del WAL nel main file: il backup cattura tutto e
    # l'export legge da uno stato consistente.
    conn = open_sqlcipher(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()

    # 2. Backup pre-migrazione. Se le righe 3-5 falliscono il file
    # originale è ancora intatto (il backup è ridondante ma cheap).
    shutil.copy2(path, backup_path)

    # 3. Export plaintext → tmp (cifrato con la chiave).
    src = open_sqlcipher(path)
    try:
        cur = src.cursor()
        # ATTACH richiede un literal nel SQL. Su Windows i path hanno `\`
        # che andrebbero escapati: forward-slash form funziona ovunque.
        attach_path = tmp_path.as_posix().replace("'", "''")
        hex_key = key.get_secret_value()
        cur.execute(
            f"ATTACH DATABASE '{attach_path}' AS encrypted KEY \"x'{hex_key}'\""
        )
        cur.execute("SELECT sqlcipher_export('encrypted')")
        cur.fetchall()
        cur.execute("DETACH DATABASE encrypted")
    finally:
        src.close()

    # 4. Sanity-check: il tmp deve riaprirsi con la stessa chiave.
    # Se questa fallisce abortiamo prima di sostituire il file originale.
    if not _can_open_encrypted(tmp_path, key):
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"encrypted export at {tmp_path} cannot be reopened with the "
            f"new key; original DB and backup at {backup_path} are intact"
        )

    # 5. Swap atomico. Dopo questo punto il file su disco è cifrato.
    os.replace(tmp_path, path)

    # 6. I sidecar -wal/-shm appartenevano al file plaintext: lasciarli
    # confonderebbe SQLite alla prossima apertura. Abbiamo appena
    # checkpoint-ato, quindi non contengono dati non flushed.
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError as e:
                logger.warning("could not remove stale sidecar %s: %s", sidecar, e)

    logger.info("DB migrato a SQLCipher; backup plaintext lasciato a %s", backup_path)

"""Backup encrypted del DB con key-wrapping a passphrase.

Tre operazioni principali:

  - `wrap_db_key(passphrase, db_key_hex) -> envelope`: deriva una chiave
    AES-256 da `passphrase` via scrypt e la usa per cifrare in AES-GCM la
    chiave DB. L'envelope risultante (salt + nonce + ciphertext + KDF
    params) è JSON-serializzabile.

  - `unwrap_db_key(passphrase, envelope) -> db_key_hex`: inverso. Raise
    `InvalidPassphrase` se l'autenticazione GCM fallisce (passphrase
    sbagliata o envelope manomesso).

  - `create_backup(db_path, db_key, envelope, dest_dir) -> Path`:
    snapshotta il DB cifrato via `VACUUM INTO` (single-file consistent
    output, mantiene la cifratura) e impacchetta in un .zip con manifest.

Threat model: l'envelope leakato è inutile senza la passphrase, ammesso
che la passphrase sia forte. scrypt protegge contro brute-force con CPU/
memoria parametrizzabili. Il valore di default (n=2**15) è ~16 MB di RAM
e ~100ms per derivazione — abbastanza lento da rendere il brute-force
costoso senza essere fastidioso per l'utente.

I backup risultanti sono portable: la chiave DB viaggia *dentro* il zip
wrappata dalla passphrase, quindi il restore funziona anche su una
macchina diversa (a differenza del DB cifrato isolato, che dipende dal
Credential Manager dell'account Windows originale).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from pydantic import SecretStr

from app.storage.encryption import open_sqlcipher

log = logging.getLogger(__name__)


# Formato del .zip. Bump quando cambia il layout dei file interni o lo
# schema del manifest in modo incompatibile.
BACKUP_FORMAT_VERSION = 1

# Parametri scrypt: 16 MB di RAM, ~100ms su CPU desktop moderna. Alti
# abbastanza da costare a un attacker, bassi abbastanza da non essere
# percepiti dall'utente al wrap/unwrap.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32   # AES-256
_SALT_LEN = 16
_NONCE_LEN = 12  # GCM default


class InvalidPassphrase(Exception):
    """Sollevata quando l'unwrap fallisce (passphrase errata o envelope corrotto)."""


class BackupCorrupt(Exception):
    """Il .zip non è un backup KeyLife valido (manifest mancante/illeggibile)."""


class Envelope(TypedDict):
    """Wrapped key envelope. Tutti i bytes sono base64-encoded per JSON."""
    v: int          # envelope format version
    kdf: str        # "scrypt"
    salt: str       # b64
    n: int
    r: int
    p: int
    nonce: str      # b64 (AES-GCM nonce)
    ct: str         # b64 (AES-GCM ciphertext + tag concatenati)


@dataclass(frozen=True)
class BackupInfo:
    filename: str
    path: Path
    size: int
    created_at: str  # ISO 8601 UTC


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def wrap_db_key(passphrase: str, db_key_hex: str) -> Envelope:
    """Wrappa `db_key_hex` (hex string a 64 char) con `passphrase`.

    Salt e nonce random freschi per ogni wrap: lo stesso input dà output
    diverso ogni volta, e leakare una singola passphrase su più envelopes
    non aiuta a romperli.
    """
    if len(db_key_hex) != 64:
        raise ValueError(f"db_key_hex must be 64 hex chars, got {len(db_key_hex)}")
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    wrap_key = kdf.derive(passphrase.encode("utf-8"))
    aead = AESGCM(wrap_key)
    ct = aead.encrypt(nonce, db_key_hex.encode("ascii"), associated_data=b"keylife/db-key/v1")
    return Envelope(
        v=1,
        kdf="scrypt",
        salt=_b64e(salt),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        nonce=_b64e(nonce),
        ct=_b64e(ct),
    )


def unwrap_db_key(passphrase: str, envelope: Envelope) -> str:
    """Sblocca l'envelope e restituisce la chiave DB hex.

    Raise `InvalidPassphrase` su qualunque errore di decifratura: non
    distinguiamo "passphrase errata" da "envelope manomesso" per non
    dare information leak a un eventuale brute-forcer offline.
    """
    if envelope.get("v") != 1:
        raise BackupCorrupt(f"unsupported envelope version: {envelope.get('v')}")
    if envelope.get("kdf") != "scrypt":
        raise BackupCorrupt(f"unsupported KDF: {envelope.get('kdf')}")
    try:
        salt = _b64d(envelope["salt"])
        nonce = _b64d(envelope["nonce"])
        ct = _b64d(envelope["ct"])
        n = int(envelope["n"]); r = int(envelope["r"]); p = int(envelope["p"])
    except (KeyError, ValueError) as e:
        raise BackupCorrupt(f"envelope fields malformed: {e}") from e

    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=n, r=r, p=p)
    wrap_key = kdf.derive(passphrase.encode("utf-8"))
    aead = AESGCM(wrap_key)
    try:
        pt = aead.decrypt(nonce, ct, associated_data=b"keylife/db-key/v1")
    except Exception as e:
        raise InvalidPassphrase("passphrase non valida o envelope corrotto") from e
    db_key_hex = pt.decode("ascii")
    if len(db_key_hex) != 64:
        raise BackupCorrupt(f"unwrapped key is not 64 hex chars (got {len(db_key_hex)})")
    return db_key_hex


# --- Backup creation -----------------------------------------------------

_BACKUP_FILENAME_RE = re.compile(
    r"^keylife-backup-(\d{4}-\d{2}-\d{2}T\d{6}Z)\.zip$"
)


def _utc_stamp() -> str:
    """Compact UTC stamp safe-for-filename: 20260518T143022Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _make_backup_filename(stamp: str | None = None) -> str:
    return f"keylife-backup-{stamp or _utc_stamp()}.zip"


def _snapshot_encrypted_db(src_path: Path, db_key: SecretStr, dest_path: Path) -> None:
    """Crea uno snapshot consistente del DB cifrato a `dest_path`.

    Uso `VACUUM INTO`: SQLite produce un single-file output e SQLCipher
    cifra la destinazione con la chiave attached. Output: file cifrato
    con la stessa chiave del source, niente sidecar `-wal/-shm`.

    Niente bisogno di tenere il flush_lock per la durata: VACUUM INTO usa
    le transazioni SQLite normali e legge uno snapshot consistente. Però
    il caller (daemon) lo tiene comunque per evitare di fare snapshot in
    mezzo a un upsert grande — più una belt-and-suspenders che necessità.
    """
    if dest_path.exists():
        dest_path.unlink()
    conn = open_sqlcipher(src_path)
    try:
        cur = conn.cursor()
        hex_key = db_key.get_secret_value()
        cur.execute(f"PRAGMA key = \"x'{hex_key}'\"")
        # Sanity: forza lettura per validare la chiave PRIMA di consumare
        # CPU sul vacuum.
        cur.execute("SELECT count(*) FROM sqlite_master")
        cur.fetchone()
        # ATTACH per VACUUM INTO non serve: SQLite scrive il file output
        # con la stessa chiave della connessione main. Path con forward
        # slash per evitare escape su Windows.
        dest_sql = dest_path.as_posix().replace("'", "''")
        cur.execute(f"VACUUM INTO '{dest_sql}'")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_backup(
    db_path: Path,
    db_key: SecretStr,
    envelope: Envelope,
    dest_dir: Path,
    *,
    app_version: str | None = None,
) -> BackupInfo:
    """Crea un backup .zip a `dest_dir`.

    Il contenuto è:
      - `db.sqlite`: snapshot consistente cifrato (VACUUM INTO output).
      - `key.envelope.json`: chiave DB wrappata con la passphrase utente.
      - `manifest.json`: metadati (versione formato, timestamp, schema).

    Atomico: scrive in `.zip.partial` e poi `os.replace` al nome finale.
    Se qualcosa fallisce, niente file parziale resta in giro.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    final_path = dest_dir / _make_backup_filename(stamp)
    partial_path = final_path.with_suffix(".zip.partial")

    if partial_path.exists():
        partial_path.unlink()

    with tempfile.TemporaryDirectory(prefix="keylife-backup-") as tmpdir:
        tmp = Path(tmpdir)
        snap_path = tmp / "db.sqlite"
        _snapshot_encrypted_db(db_path, db_key, snap_path)
        snap_size = snap_path.stat().st_size

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app_version": app_version,
            "db_filename": db_path.name,
            "db_size_bytes": snap_size,
        }

        try:
            with zipfile.ZipFile(partial_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(snap_path, arcname="db.sqlite")
                zf.writestr("key.envelope.json", json.dumps(envelope, indent=2))
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        except Exception:
            if partial_path.exists():
                try: partial_path.unlink()
                except OSError: pass
            raise

    os.replace(partial_path, final_path)

    st = final_path.stat()
    return BackupInfo(
        filename=final_path.name,
        path=final_path,
        size=st.st_size,
        created_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def list_backups(dest_dir: Path) -> list[BackupInfo]:
    """Elenca i .zip di backup in `dest_dir`, più recenti prima.

    Filtra rigorosamente sul pattern del nostro naming: ignoriamo zip o
    altri file che l'utente potrebbe aver messo nella stessa cartella
    (es. il dump manuale `2026-05-09/`).
    """
    if not dest_dir.is_dir():
        return []
    items: list[BackupInfo] = []
    for p in dest_dir.iterdir():
        if not p.is_file():
            continue
        if not _BACKUP_FILENAME_RE.match(p.name):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        items.append(BackupInfo(
            filename=p.name,
            path=p,
            size=st.st_size,
            created_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
    items.sort(key=lambda b: b.created_at, reverse=True)
    return items


def prune_backups(dest_dir: Path, keep_n: int) -> list[BackupInfo]:
    """Tiene i `keep_n` più recenti, cancella il resto. Restituisce i rimossi.

    `keep_n <= 0` è no-op (mai cancelliamo tutto in automatico, per
    paranoia). Solo i file che combaciano col nostro pattern sono
    eleggibili — i dump manuali dell'utente non vengono toccati.
    """
    if keep_n <= 0:
        return []
    all_backups = list_backups(dest_dir)
    if len(all_backups) <= keep_n:
        return []
    to_remove = all_backups[keep_n:]
    removed: list[BackupInfo] = []
    for b in to_remove:
        try:
            b.path.unlink()
            removed.append(b)
        except OSError as e:
            log.warning("could not prune backup %s: %s", b.path, e)
    return removed


# --- Restore -------------------------------------------------------------

def validate_backup_zip(zip_path: Path) -> dict:
    """Legge il manifest senza estrarre nulla. Raise BackupCorrupt se invalido.

    Restituisce il manifest decoded. Da chiamare prima di chiedere la
    passphrase all'utente: ha senso fallire subito se il file non è
    nemmeno un backup nostro.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise BackupCorrupt("manifest.json missing")
            if "db.sqlite" not in names:
                raise BackupCorrupt("db.sqlite missing")
            if "key.envelope.json" not in names:
                raise BackupCorrupt("key.envelope.json missing")
            with zf.open("manifest.json") as f:
                manifest = json.loads(f.read().decode("utf-8"))
    except (zipfile.BadZipFile, json.JSONDecodeError) as e:
        raise BackupCorrupt(f"not a valid zip backup: {e}") from e
    fv = manifest.get("format_version")
    if fv != BACKUP_FORMAT_VERSION:
        raise BackupCorrupt(f"unsupported backup format_version: {fv}")
    return manifest


def read_envelope_from_zip(zip_path: Path) -> Envelope:
    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("key.envelope.json") as f:
            data = json.loads(f.read().decode("utf-8"))
    return data  # type: ignore[return-value]


def extract_db_from_zip(zip_path: Path, dest_path: Path) -> None:
    """Estrae db.sqlite dal backup a `dest_path` (sovrascrive se esiste)."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("db.sqlite") as src, open(dest_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


# --- Restore staging -----------------------------------------------------
#
# Il restore non avviene live (engine swap a runtime è una mina anti-uomo
# di race condition: readers in volo, lock SQLite, settings cache, ...).
# Invece: l'API stagea il DB e la chiave, scrive un marker, dice all'utente
# "riavvia l'app". Al prossimo avvio `apply_pending_restore()` fa la swap
# atomica prima che chiunque apra una connessione.
#
# La nuova chiave del DB NON viene mai scritta in plaintext su disco. Vive
# in uno slot dedicato del Windows Credential Manager (`KeyLife/db-restore-
# pending`) finché non viene migrata allo slot canonico al boot successivo.

_STAGING_DIRNAME = "restore-staging"
_STAGING_DB_NAME = "db.sqlite"
_MARKER_FILENAME = ".restore-pending.json"
_KEYRING_SERVICE = "KeyLife"
_KEYRING_PENDING_USER = "db-restore-pending"
_KEYRING_CANONICAL_USER = "db"


@dataclass(frozen=True)
class StagedRestore:
    staged_at: str   # ISO 8601 UTC
    staging_dir: Path
    marker_path: Path


def stage_restore(zip_path: Path, passphrase: str, data_dir: Path) -> StagedRestore:
    """Valida il zip + la passphrase e stagea i file per la swap al prossimo avvio.

    Steps:
      1. Validate zip layout + manifest version.
      2. Read envelope, unwrap key with `passphrase` (raise InvalidPassphrase
         se sbagliata — NIENTE viene scritto).
      3. Extract db.sqlite to `<data_dir>/restore-staging/db.sqlite`.
      4. Verify the staged DB opens with the unwrapped key (sanity check
         contro un backup corrotto in modo non rilevato dal manifest).
      5. Write the unwrapped key to the pending keyring slot.
      6. Write the marker JSON.

    Se step 4-6 falliscono, cleanup completo: niente file residui, niente
    slot keyring orfano. L'utente può ritentare.
    """
    import keyring

    # 1+2: validate + unwrap. Niente side effect su disco prima di qui.
    validate_backup_zip(zip_path)
    envelope = read_envelope_from_zip(zip_path)
    db_key_hex = unwrap_db_key(passphrase, envelope)  # raises InvalidPassphrase

    staging_dir = data_dir / _STAGING_DIRNAME
    staged_db = staging_dir / _STAGING_DB_NAME
    marker = data_dir / _MARKER_FILENAME

    # 3: extract. Pulisci una staging precedente se presente.
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        extract_db_from_zip(zip_path, staged_db)

        # 4: sanity check con la chiave appena unwrappata.
        from app.storage.encryption import _can_open_encrypted  # noqa: PLC0415
        if not _can_open_encrypted(staged_db, SecretStr(db_key_hex)):
            raise BackupCorrupt(
                "staged DB cannot be opened with the unwrapped key — "
                "envelope and DB likely mismatched"
            )

        # 5: scrivi la chiave nel keyring (slot pending).
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_PENDING_USER, db_key_hex)

        # 6: marker. La presenza del file è il trigger del boot-time apply.
        staged_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker.write_text(
            json.dumps({
                "format_version": 1,
                "staged_at": staged_at,
                "source_filename": zip_path.name,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Best-effort cleanup. Se anche questo fallisce, l'utente vede
        # rumore in data_dir ma il DB live è intatto: l'unica cosa che
        # avvia il restore al prossimo boot è la presenza del marker.
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_PENDING_USER)
        except Exception:
            pass
        raise

    return StagedRestore(
        staged_at=staged_at,
        staging_dir=staging_dir,
        marker_path=marker,
    )


def apply_pending_restore(data_dir: Path, db_path: Path) -> bool:
    """Chiamata da run.py al boot, PRIMA di aprire qualunque connessione.

    Se non c'è marker: no-op, return False. Altrimenti applica la swap:
      - sposta il DB corrente a `<db>.pre-restore.bak` (safety net).
      - sposta il staged DB nella posizione live.
      - migra la chiave dallo slot pending allo slot canonico.
      - pulisce marker + staging dir + pending slot.

    Se manca uno dei requisiti (staged DB o pending key non trovati),
    cleanup del marker senza toccare il DB live: meglio un restore
    silenziosamente abortito che un DB rotto.
    """
    import keyring

    marker = data_dir / _MARKER_FILENAME
    if not marker.is_file():
        return False

    staged_db = data_dir / _STAGING_DIRNAME / _STAGING_DB_NAME
    try:
        pending_key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_PENDING_USER)
    except Exception:
        pending_key = None

    if not staged_db.is_file() or not pending_key:
        log.warning(
            "restore marker present but staged_db=%s / pending_key=%s; aborting restore",
            staged_db.is_file(), bool(pending_key),
        )
        _cleanup_restore_artifacts(data_dir)
        return False

    backup_path = db_path.with_suffix(db_path.suffix + ".pre-restore.bak")

    # 1. Sposta il DB corrente (se esiste) al .pre-restore.bak.
    if db_path.exists():
        # I sidecar -wal/-shm sono incompatibili con un DB diverso —
        # vanno rimossi prima dello swap.
        for s in ("-wal", "-shm"):
            sc = db_path.with_name(db_path.name + s)
            if sc.exists():
                try:
                    sc.unlink()
                except OSError as e:
                    log.warning("could not remove stale sidecar %s: %s", sc, e)
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError as e:
                # Non fatale: usiamo .bak.N come ripiego per non perdere
                # il file vecchio.
                fallback = backup_path.with_suffix(
                    backup_path.suffix + f".{int(datetime.now().timestamp())}"
                )
                log.warning("pre-restore backup exists; saving to %s instead", fallback)
                backup_path = fallback
                if backup_path.exists():
                    try: backup_path.unlink()
                    except OSError: pass
        shutil.move(str(db_path), str(backup_path))

    # 2. Swap in del nuovo DB.
    shutil.move(str(staged_db), str(db_path))

    # 3. Migra la chiave: pending → canonical, poi cancella pending.
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_CANONICAL_USER, pending_key)
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_PENDING_USER)
    except Exception:
        log.warning("could not delete pending keyring slot; harmless leftover")

    # 4. Cleanup file system.
    _cleanup_restore_artifacts(data_dir)

    log.info("restore applied; previous DB saved at %s", backup_path)
    return True


def _cleanup_restore_artifacts(data_dir: Path) -> None:
    """Rimuovi marker + staging dir. Idempotente, swallows errors."""
    marker = data_dir / _MARKER_FILENAME
    staging_dir = data_dir / _STAGING_DIRNAME
    try:
        if marker.is_file():
            marker.unlink()
    except OSError:
        pass
    try:
        if staging_dir.is_dir():
            shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        pass


def cancel_pending_restore(data_dir: Path) -> bool:
    """Annulla un restore staged ma non ancora applicato. Per l'API.

    Usato se l'utente fa restore, ci ripensa, e vuole annullare senza
    riavviare. Pulisce anche il pending keyring slot.
    """
    import keyring
    marker = data_dir / _MARKER_FILENAME
    if not marker.is_file():
        return False
    _cleanup_restore_artifacts(data_dir)
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_PENDING_USER)
    except Exception:
        pass
    return True


def restore_pending_info(data_dir: Path) -> dict | None:
    """Legge il marker se presente. Per l'API GET status."""
    marker = data_dir / _MARKER_FILENAME
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

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


def _ensure_db_state() -> None:
    """Pre-flight di cifratura, prima che chiunque apra una connessione.

    Stati possibili e azione:
      - missing       → noop. Alembic creerà il file: il connect listener
                        emette `PRAGMA key=...` come primo statement, il
                        DB nasce direttamente cifrato.
      - encrypted_ok  → noop. Il flusso normale.
      - plaintext     → migra in-place via `sqlcipher_export()`, lascia
                        `<db>.pre-encrypt.bak` come safety net.
      - unreadable    → exit(2). Né plaintext né apribile con la chiave
                        attuale: chiave rigenerata, file corrotto, o DB
                        di un'altra installazione. Non distruggiamo nulla.
    """
    from app.core.config import get_settings
    from app.storage.encryption import (
        detect_db_state,
        migrate_plaintext_to_encrypted,
    )

    settings = get_settings()
    state = detect_db_state(settings.db_path, settings.db_key)

    if state in ("missing", "encrypted_ok"):
        return
    if state == "plaintext":
        print(
            f"[keylife] DB plaintext rilevato a {settings.db_path}: "
            "migrazione a SQLCipher in corso...",
            file=sys.stderr,
        )
        migrate_plaintext_to_encrypted(settings.db_path, settings.db_key)
        print(
            f"[keylife] Migrazione completata. Backup plaintext: "
            f"{settings.db_path}.pre-encrypt.bak (cancellabile a mano "
            "una volta verificato che tutto funzioni).",
            file=sys.stderr,
        )
        return

    print(
        f"[keylife] ERRORE: il DB a {settings.db_path} esiste ma non si "
        "apre né come SQLite plaintext né con la chiave attualmente nel "
        "Windows Credential Manager. Cause tipiche: chiave rigenerata "
        "(es. profilo utente reinstallato), file corrotto, oppure è il "
        "DB di un'altra installazione. Per ripartire da zero cancella "
        "il file (perdi i dati). Per ripristinare un backup, cancella "
        "il .sqlite e rinomina <db>.pre-encrypt.bak in <db>.",
        file=sys.stderr,
    )
    sys.exit(2)


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
    # Order matters: lo stato cifrato deve essere risolto PRIMA che alembic
    # apra il suo engine. Se troviamo plaintext lo ricifriamo a `db_path`
    # in-place così la successiva `command.upgrade` lavora sul file corretto.
    _ensure_db_state()
    _run_migrations()
    from app.__main__ import main as app_main
    # No CLI args from the IDE? Default to Qt UI + API server.
    args = sys.argv[1:] or ["--api"]
    return app_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

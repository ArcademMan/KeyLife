from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.storage.encryption import open_sqlcipher


def _build_engine() -> Engine:
    settings = get_settings()

    # check_same_thread=False is safe because:
    #   - writes are serialized through KeyLifeDaemon._flush_lock (single
    #     writer thread: the periodic flush);
    #   - reads from other threads (e.g. the Qt UI thread polling stats)
    #     run as concurrent readers under SQLite WAL, each opening its own
    #     short-lived Connection from the SQLAlchemy pool.
    # Do NOT issue WRITES from threads other than the flush thread without
    # re-evaluating this assumption.
    #
    # Per usare SQLCipher invece dello sqlite3 stdlib bypassiamo il default
    # del dialect via `creator=`: SQLAlchemy continua a parlare dialect
    # SQLite ma le connessioni nascono da `sqlcipher3.dbapi2.connect`. Il
    # `module=` allinea anche il mapping delle eccezioni del DB-API così
    # che SQLAlchemy sappia riconoscere gli errori sqlcipher come SQLite.
    import sqlcipher3.dbapi2 as sqlcipher_dbapi

    db_path = str(settings.db_path)

    def _creator():
        return open_sqlcipher(db_path)

    engine = create_engine(
        settings.db_url,
        module=sqlcipher_dbapi,
        creator=_creator,
        future=True,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
        cur = dbapi_conn.cursor()
        # PRAGMA key MUST be the first statement on a SQLCipher connection:
        # le pagine sono cifrate, qualunque altra operazione prima di key
        # fallisce o (peggio) sembra riuscire e legge dati corrotti.
        hex_key = settings.db_key.get_secret_value()
        cur.execute(f"PRAGMA key = \"x'{hex_key}'\"")
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA foreign_keys=ON;")
        # Cap the -wal sidecar: without this the file grows unbounded between
        # connection closes (default 1000 pages). 100 pages ≈ 400 KB.
        cur.execute("PRAGMA wal_autocheckpoint=100;")
        cur.close()

    return engine


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal

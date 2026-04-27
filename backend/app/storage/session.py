from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


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
    engine = create_engine(
        settings.db_url,
        future=True,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
        cur = dbapi_conn.cursor()
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

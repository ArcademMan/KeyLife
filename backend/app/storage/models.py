from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyKeyCount(Base):
    """Per-key daily aggregate.

    Granularity is intentionally coarse (date + vk + scancode -> count).
    No timestamps, no order, no co-occurrence — a single keystroke is
    statistically indistinguishable inside a day's bucket.
    """

    __tablename__ = "daily_key_counts"

    date: Mapped[str] = mapped_column(String(10))  # ISO date YYYY-MM-DD
    vk: Mapped[int] = mapped_column(Integer)
    scancode: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("date", "vk", "scancode", name="pk_daily_key_counts"),
    )


class HourlyTotal(Base):
    """Per-hour total presses, no per-key breakdown.

    Used for temporal usage patterns; cannot leak which key was pressed.
    """

    __tablename__ = "hourly_totals"

    date: Mapped[str] = mapped_column(String(10))  # ISO date YYYY-MM-DD
    hour: Mapped[int] = mapped_column(Integer)     # 0..23
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("date", "hour", name="pk_hourly_totals"),
    )


# --- Per-application tracking (opt-in feature) ----------------------------
#
# Privacy note: queste tre tabelle popolano solo se l'utente attiva
# esplicitamente il toggle in Settings. Salviamo solo `exe_name` (basename
# dell'eseguibile, es. "chrome.exe"), mai window title o full path: i title
# rivelano URL del browser, nomi file, clienti nei meeting; il full path
# rivela username e installazioni. Il DB è cifrato (vedi CLAUDE.md, sezione
# Encryption-at-rest), ma il principio "minimize what you collect" resta.

class DailyAppCount(Base):
    """Conteggio giornaliero di key press attribuiti a un'applicazione.

    `exe_name` è il basename dell'eseguibile in foreground al momento del
    DOWN. "unknown" è il bucket per processi protetti (anti-cheat, lsass,
    UWP host se ApplicationFrameHost.exe non risolve), "system" per
    lockscreen / secure desktop.
    """

    __tablename__ = "daily_app_counts"

    date: Mapped[str] = mapped_column(String(10))
    exe_name: Mapped[str] = mapped_column(String(260))  # MAX_PATH-safe
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("date", "exe_name", name="pk_daily_app_counts"),
    )


class HourlyAppTotal(Base):
    """Conteggio orario di key press per applicazione."""

    __tablename__ = "hourly_app_totals"

    date: Mapped[str] = mapped_column(String(10))
    hour: Mapped[int] = mapped_column(Integer)
    exe_name: Mapped[str] = mapped_column(String(260))
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "date", "hour", "exe_name", name="pk_hourly_app_totals"
        ),
    )


class AppIcon(Base):
    """Icona PNG (32x32) di un'applicazione, estratta dall'exe.

    Una riga per `exe_name`. PNG come BLOB così l'icona vive nel DB cifrato
    invece che come file separato in `data_dir` (che leakerebbe la lista
    delle app anche con il DB cifrato). `fetched_at` è l'ISO timestamp UTC
    dell'estrazione: serve come ETag per la cache HTTP del frontend.
    """

    __tablename__ = "app_icons"

    exe_name: Mapped[str] = mapped_column(String(260), primary_key=True)
    png: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fetched_at: Mapped[str] = mapped_column(String(32), nullable=False)


class AppSetting(Base):
    """Key-value store per le preferenze utente persistite nel DB.

    Lo usiamo per il toggle del per-app tracking e per la blocklist. Il DB
    è già lì e cifrato — preferito a un secondo file JSON in chiaro in
    data_dir. Convenzioni dei valori: tracking_enabled = "0"/"1",
    blocklist = JSON array di stringhe.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

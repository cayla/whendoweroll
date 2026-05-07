"""SQLite engine + session helpers.

We keep this tiny on purpose: one file-backed SQLite database, one engine,
short-lived sessions per request. SQLite is fine for a single-process MVP;
if this ever needs multiple workers, swap the URL for Postgres.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "WHENDOWEROLL_DB_URL",
    "sqlite:///./whendoweroll.sqlite3",
)

# check_same_thread=False is required because FastAPI may run handlers in a
# threadpool; SQLite would otherwise reject reuse across threads.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def _hours_between_local_hhmm(start_hhmm: str, end_hhmm: str) -> float:
    s = datetime.strptime(start_hhmm.strip()[:5], "%H:%M")
    e = datetime.strptime(end_hhmm.strip()[:5], "%H:%M")
    ds = timedelta(hours=s.hour, minutes=s.minute)
    de = timedelta(hours=e.hour, minutes=e.minute)
    diff_h = (de - ds).total_seconds() / 3600.0
    if diff_h <= 0:
        diff_h += 24.0
    return diff_h


def _utc_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def migrate_sqlite_slot_schema(eng) -> None:
    """SQLite only: add ``duration_hours`` to legacy ``slot`` rows and backfill.

    Older DBs had ``end_local`` (HH:MM) for recurring slots; we derive hours from
    that, or from ``starts_at_utc``/``ends_at_utc`` for ad-hoc rows.
    """
    with eng.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(slot)")).fetchall()
        if not info:
            return
        names = {row[1] for row in info}
        if "duration_hours" not in names:
            conn.execute(text("ALTER TABLE slot ADD COLUMN duration_hours REAL"))
        has_end_local = "end_local" in names
        cols = "id, kind, start_local, starts_at_utc, ends_at_utc, duration_hours"
        if has_end_local:
            cols = "id, kind, start_local, end_local, starts_at_utc, ends_at_utc, duration_hours"
        rows = conn.execute(text(f"SELECT {cols} FROM slot")).mappings().all()
        for row in rows:
            if row.get("duration_hours") is not None:
                continue
            dh: float
            kind = row.get("kind")
            if kind == "recurring" and row.get("start_local") and has_end_local and row.get("end_local"):
                dh = _hours_between_local_hhmm(row["start_local"], row["end_local"])
            elif kind == "adhoc":
                su, eu = _utc_dt(row.get("starts_at_utc")), _utc_dt(row.get("ends_at_utc"))
                if su and eu:
                    dh = max((eu - su).total_seconds() / 3600.0, _MIN_FALLBACK_H)
                else:
                    dh = _DEFAULT_DURATION_H
            else:
                dh = _DEFAULT_DURATION_H
            conn.execute(
                text("UPDATE slot SET duration_hours = :dh WHERE id = :id"),
                {"dh": dh, "id": row["id"]},
            )


_DEFAULT_DURATION_H = 3.0
_MIN_FALLBACK_H = 1.0 / 60.0


def migrate_sqlite_player_is_dm(eng) -> None:
    """Add ``is_dm`` for legacy SQLite ``player`` rows (default false)."""
    with eng.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(player)")).fetchall()
        if not info:
            return
        names = {row[1] for row in info}
        if "is_dm" not in names:
            conn.execute(text("ALTER TABLE player ADD COLUMN is_dm INTEGER NOT NULL DEFAULT 0"))


def init_db() -> None:
    # Importing models registers them on SQLModel.metadata before create_all.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    if DATABASE_URL.startswith("sqlite"):
        migrate_sqlite_slot_schema(engine)
        migrate_sqlite_player_is_dm(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

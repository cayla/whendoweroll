"""SQLite engine + session helpers.

We keep this tiny on purpose: one file-backed SQLite database, one engine,
short-lived sessions per request. SQLite is fine for a single-process MVP;
if this ever needs multiple workers, swap the URL for Postgres.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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


# Backfill defaults for legacy slot rows missing duration_hours.
_DEFAULT_DURATION_H = 3.0
_MIN_FALLBACK_H = 1.0 / 60.0


def _hours_between_local_hhmm(start_hhmm: str, end_hhmm: str) -> float:
    sh, sm = _split_hhmm(start_hhmm)
    eh, em = _split_hhmm(end_hhmm)
    ds = timedelta(hours=sh, minutes=sm)
    de = timedelta(hours=eh, minutes=em)
    diff_h = (de - ds).total_seconds() / 3600.0
    if diff_h <= 0:
        diff_h += 24.0
    return diff_h


def _split_hhmm(hhmm: str) -> tuple[int, int]:
    h_s, _, m_s = hhmm.strip()[:5].partition(":")
    return int(h_s), int(m_s)


def _utc_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
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
                if su and eu:  # noqa: SIM108 — explicit if/else reads clearer than the long ternary here
                    dh = max((eu - su).total_seconds() / 3600.0, _MIN_FALLBACK_H)
                else:
                    dh = _DEFAULT_DURATION_H
            else:
                dh = _DEFAULT_DURATION_H
            conn.execute(
                text("UPDATE slot SET duration_hours = :dh WHERE id = :id"),
                {"dh": dh, "id": row["id"]},
            )


def migrate_sqlite_player_is_mandatory(eng) -> None:
    """Ensure SQLite ``player`` has ``is_mandatory``, migrating from legacy ``is_dm``.

    Handles three states:
      1. fresh DB (``is_mandatory`` already created by ``SQLModel.metadata.create_all``);
      2. very old DB with neither column → add ``is_mandatory``;
      3. older DB with ``is_dm`` only → add ``is_mandatory``, copy values across,
         then drop ``is_dm`` (SQLite >= 3.35).
    """
    with eng.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(player)")).fetchall()
        if not info:
            return
        names = {row[1] for row in info}
        if "is_mandatory" not in names:
            conn.execute(text("ALTER TABLE player ADD COLUMN is_mandatory INTEGER NOT NULL DEFAULT 0"))
            if "is_dm" in names:
                conn.execute(text("UPDATE player SET is_mandatory = is_dm"))
        if "is_dm" in names:
            # SQLite < 3.35 can't drop columns; leave the legacy column in
            # place. is_mandatory is the source of truth from now on.
            with contextlib.suppress(Exception):
                conn.execute(text("ALTER TABLE player DROP COLUMN is_dm"))


def migrate_sqlite_campaign_consensus_policy(eng) -> None:
    """Add ``consensus_policy`` to legacy ``campaign`` rows.

    Older DBs predate the per-campaign consensus policy. Default everyone
    to ``no_two_nears`` since that matches the public-page semantics those
    campaigns were already running with for the two summary cards. The
    side-effect for existing ICS subscribers is that the feed tightens up
    (two near-consensus windows no longer appear back-to-back), which is
    the explicit design intent — the calendar is the authoritative play
    schedule.
    """
    with eng.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(campaign)")).fetchall()
        if not info:
            return
        names = {row[1] for row in info}
        if "consensus_policy" not in names:
            conn.execute(text("ALTER TABLE campaign ADD COLUMN consensus_policy TEXT NOT NULL DEFAULT 'no_two_nears'"))


def init_db() -> None:
    # Importing models registers them on SQLModel.metadata before create_all.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    if DATABASE_URL.startswith("sqlite"):
        migrate_sqlite_slot_schema(engine)
        migrate_sqlite_player_is_mandatory(engine)
        migrate_sqlite_campaign_consensus_policy(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

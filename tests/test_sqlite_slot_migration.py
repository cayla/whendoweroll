"""Legacy SQLite ``slot`` table gains ``duration_hours`` on startup migration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db import (
    migrate_sqlite_campaign_public_recurrence_mode,
    migrate_sqlite_slot_max_sessions_per_month,
    migrate_sqlite_slot_recurrence_cadence,
    migrate_sqlite_slot_schema,
)


def test_migration_adds_duration_from_end_local():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE slot (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    kind VARCHAR NOT NULL,
                    label VARCHAR,
                    weekday INTEGER,
                    start_local VARCHAR,
                    end_local VARCHAR,
                    starts_at_utc VARCHAR,
                    ends_at_utc VARCHAR,
                    created_at VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO slot (id, campaign_id, kind, weekday, start_local, end_local, created_at)
                VALUES (1, 1, 'recurring', 4, '18:00', '21:00', '2026-01-01')
                """
            )
        )
    migrate_sqlite_slot_schema(eng)
    with eng.connect() as conn:
        dh = conn.execute(text("SELECT duration_hours FROM slot WHERE id = 1")).scalar_one()
    assert dh == 3.0


def test_migration_adhoc_from_utc_bounds():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
    end = start + timedelta(hours=2, minutes=30)
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE slot (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    kind VARCHAR NOT NULL,
                    label VARCHAR,
                    weekday INTEGER,
                    start_local VARCHAR,
                    end_local VARCHAR,
                    starts_at_utc VARCHAR,
                    ends_at_utc VARCHAR,
                    created_at VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO slot (id, campaign_id, kind, starts_at_utc, ends_at_utc, created_at)
                VALUES (1, 1, 'adhoc', :su, :eu, '2026-01-01')
                """
            ),
            {"su": start.isoformat(), "eu": end.isoformat()},
        )
    migrate_sqlite_slot_schema(eng)
    with eng.connect() as conn:
        dh = conn.execute(text("SELECT duration_hours FROM slot WHERE id = 1")).scalar_one()
    assert abs(dh - 2.5) < 1e-6


def test_migration_adds_max_sessions_per_month_column():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE slot (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    kind VARCHAR NOT NULL
                )
                """
            )
        )
    migrate_sqlite_slot_max_sessions_per_month(eng)
    with eng.connect() as conn:
        names = {row[1] for row in conn.execute(text("PRAGMA table_info(slot)")).fetchall()}
    assert "max_sessions_per_month" in names


def test_migration_adds_recurrence_cadence_columns():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE slot (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    kind VARCHAR NOT NULL
                )
                """
            )
        )
    migrate_sqlite_slot_recurrence_cadence(eng)
    with eng.connect() as conn:
        names = {row[1] for row in conn.execute(text("PRAGMA table_info(slot)")).fetchall()}
    assert "every_n_weeks" in names
    assert "recurrence_anchor_local_date" in names


def test_migration_adds_campaign_public_recurrence_mode_and_backfills():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE campaign (
                    id INTEGER PRIMARY KEY,
                    public_id VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    timezone VARCHAR NOT NULL,
                    admin_secret_hash VARCHAR NOT NULL,
                    horizon_weeks INTEGER NOT NULL DEFAULT 12,
                    consensus_policy VARCHAR NOT NULL DEFAULT 'no_two_nears',
                    created_at VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO campaign (id, public_id, name, timezone, admin_secret_hash) "
                "VALUES (1, 'pid', 'n', 'UTC', 'h')"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE slot (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    kind VARCHAR NOT NULL,
                    public_recurrence_mode VARCHAR NOT NULL DEFAULT 'weekly'
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO slot (id, campaign_id, kind, public_recurrence_mode) "
                "VALUES (1, 1, 'recurring', 'twice_per_month')"
            )
        )
    migrate_sqlite_campaign_public_recurrence_mode(eng)
    with eng.connect() as conn:
        names = {row[1] for row in conn.execute(text("PRAGMA table_info(campaign)")).fetchall()}
        row = conn.execute(text("SELECT public_recurrence_mode FROM campaign WHERE id = 1")).one()
    assert "public_recurrence_mode" in names
    assert row[0] == "twice_per_month"

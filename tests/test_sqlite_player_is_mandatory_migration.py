"""Legacy SQLite ``player`` table gains ``is_mandatory`` (and migrates from ``is_dm``)."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db import migrate_sqlite_player_is_mandatory


def _legacy_player_engine(extra_columns: str = ""):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    cols = (
        "id INTEGER PRIMARY KEY,"
        "campaign_id INTEGER NOT NULL,"
        "display_name VARCHAR NOT NULL,"
        "token_hash VARCHAR NOT NULL,"
        "sort_order INTEGER NOT NULL,"
        "created_at VARCHAR"
    )
    if extra_columns:
        cols += "," + extra_columns
    with eng.begin() as conn:
        conn.execute(text(f"CREATE TABLE player ({cols})"))
    return eng


def test_migration_adds_is_mandatory_when_no_legacy_column():
    eng = _legacy_player_engine()
    migrate_sqlite_player_is_mandatory(eng)
    with eng.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(player)")).fetchall()]
    assert "is_mandatory" in cols
    assert "is_dm" not in cols


def test_migration_copies_is_dm_into_is_mandatory_then_drops_is_dm():
    eng = _legacy_player_engine("is_dm INTEGER NOT NULL DEFAULT 0")
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO player "
                "(id, campaign_id, display_name, token_hash, sort_order, created_at, is_dm) "
                "VALUES (1, 1, 'GM', 'h1', 0, '2026-01-01', 1), "
                "(2, 1, 'Player', 'h2', 1, '2026-01-01', 0)"
            )
        )
    migrate_sqlite_player_is_mandatory(eng)
    with eng.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(player)")).fetchall()]
        rows = conn.execute(text("SELECT id, is_mandatory FROM player ORDER BY id")).fetchall()
    assert "is_mandatory" in cols
    assert "is_dm" not in cols  # SQLite >= 3.35 supports DROP COLUMN
    assert [(r[0], r[1]) for r in rows] == [(1, 1), (2, 0)]


def test_migration_idempotent_on_modern_schema():
    eng = _legacy_player_engine("is_mandatory INTEGER NOT NULL DEFAULT 0")
    migrate_sqlite_player_is_mandatory(eng)
    migrate_sqlite_player_is_mandatory(eng)  # second pass is a no-op
    with eng.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(player)")).fetchall()]
    assert cols.count("is_mandatory") == 1
    assert "is_dm" not in cols

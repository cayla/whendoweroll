"""Legacy SQLite ``player`` table gains ``is_dm``."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db import migrate_sqlite_player_is_dm


def test_migration_adds_is_dm_column():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE player (
                    id INTEGER PRIMARY KEY,
                    campaign_id INTEGER NOT NULL,
                    display_name VARCHAR NOT NULL,
                    token_hash VARCHAR NOT NULL,
                    sort_order INTEGER NOT NULL,
                    created_at VARCHAR
                )
                """
            )
        )
    migrate_sqlite_player_is_dm(eng)
    with eng.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(player)")).fetchall()]
    assert "is_dm" in cols

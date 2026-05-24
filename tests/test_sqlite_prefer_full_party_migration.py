"""SQLite migration for campaign.prefer_full_party."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.db import migrate_sqlite_campaign_prefer_full_party


def test_migration_adds_prefer_full_party_default_on():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
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
                    consensus_policy VARCHAR NOT NULL DEFAULT 'no_two_nears'
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO campaign (id, public_id, name, timezone, admin_secret_hash) "
                "VALUES (1, 'x', 'n', 'UTC', 'h')"
            )
        )
    migrate_sqlite_campaign_prefer_full_party(eng)
    with eng.connect() as conn:
        row = conn.execute(text("SELECT prefer_full_party FROM campaign WHERE id = 1")).one()
    assert row[0] == 1

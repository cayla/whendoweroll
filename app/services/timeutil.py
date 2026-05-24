"""UTC normalization for occurrence keys (DB round-trips, comparisons)."""

from __future__ import annotations

from datetime import UTC, datetime


def ensure_utc(value: datetime) -> datetime:
    """Return an aware UTC instant (SQLite often drops tzinfo on read)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_occurrence_start(value: datetime) -> datetime:
    """Return an aware UTC instant with microseconds cleared for stable keys."""
    return ensure_utc(value).replace(microsecond=0)

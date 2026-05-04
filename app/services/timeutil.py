"""UTC normalization for occurrence keys (DB round-trips, comparisons)."""

from __future__ import annotations

from datetime import datetime, timezone


def normalize_occurrence_start(value: datetime) -> datetime:
    """Return an aware UTC instant with microseconds cleared for stable keys."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)

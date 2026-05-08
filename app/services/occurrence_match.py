"""Validate that a client-submitted instant matches a real slot occurrence."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import Campaign, Slot
from app.services.slots import Occurrence, upcoming_occurrences_for_slot
from app.services.timeutil import normalize_occurrence_start


def parse_occurrence_start(value: str) -> datetime:
    v = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(v)


def resolve_occurrence(slot: Slot, campaign: Campaign, occurrence_start: str) -> Occurrence | None:
    try:
        parsed = parse_occurrence_start(occurrence_start)
    except ValueError:
        return None
    tz = ZoneInfo(campaign.timezone)
    target = normalize_occurrence_start(parsed)
    for occ in upcoming_occurrences_for_slot(slot, tz=tz, horizon_weeks=campaign.horizon_weeks):
        if normalize_occurrence_start(occ.starts_at_utc) == target:
            return occ
    return None

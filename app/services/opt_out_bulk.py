"""Bulk per-occurrence opt-outs over a calendar-day range in the campaign timezone."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models import AvailabilityStatus, Campaign, OccurrenceOptOut, Player, Slot, SlotKind
from app.services.opt_outs import load_opt_out_set
from app.services.player_view import exception_horizon_weeks
from app.services.slots import upcoming_occurrences_for_slot
from app.services.timeutil import normalize_occurrence_start


def calendar_week_range(campaign: Campaign, *, offset_weeks: int = 0) -> tuple[date, date]:
    """Monday through Sunday in the campaign timezone (``offset_weeks=1`` for next week)."""
    tz = ZoneInfo(campaign.timezone)
    today = datetime.now(tz).date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    return monday, monday + timedelta(days=6)


def add_opt_outs_in_calendar_range(
    session: Session,
    *,
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    availability_by_slot: dict[int, AvailabilityStatus],
    start_day: date,
    end_day: date,
) -> int:
    """Opt out of recurring occurrences whose local calendar day is in [start_day, end_day].

    Only slots where the player has standing *yes* are considered. Returns the number
    of new opt-out rows inserted (idempotent for occurrences already opted out).
    """
    if start_day > end_day:
        return 0

    player_id = player.id
    if player_id is None:
        return 0

    tz = ZoneInfo(campaign.timezone)
    horizon = exception_horizon_weeks(campaign)
    existing = load_opt_out_set(session, [player_id])

    to_add: list[OccurrenceOptOut] = []
    for slot in slots:
        if slot.kind is not SlotKind.recurring:
            continue
        if availability_by_slot.get(slot.id) is not AvailabilityStatus.yes:
            continue
        sid = slot.id
        if sid is None:
            continue
        for occ in upcoming_occurrences_for_slot(slot, tz=tz, horizon_weeks=horizon):
            local_day = occ.starts_at_utc.astimezone(tz).date()
            if local_day < start_day or local_day > end_day:
                continue
            key_start = normalize_occurrence_start(occ.starts_at_utc)
            key = (player_id, sid, key_start)
            if key in existing:
                continue
            existing.add(key)
            to_add.append(
                OccurrenceOptOut(
                    player_id=player_id,
                    slot_id=sid,
                    starts_at_utc=key_start,
                )
            )

    for row in to_add:
        session.add(row)
    if to_add:
        session.commit()
    return len(to_add)


def remove_opt_outs_in_calendar_range(
    session: Session,
    *,
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    availability_by_slot: dict[int, AvailabilityStatus],
    start_day: date,
    end_day: date,
) -> int:
    """Remove per-date opt-outs whose local calendar day is in [start_day, end_day]."""
    if start_day > end_day:
        return 0

    player_id = player.id
    if player_id is None:
        return 0

    tz = ZoneInfo(campaign.timezone)
    yes_slot_ids = {
        slot.id
        for slot in slots
        if slot.kind is SlotKind.recurring
        and slot.id is not None
        and availability_by_slot.get(slot.id) is AvailabilityStatus.yes
    }
    if not yes_slot_ids:
        return 0

    rows = session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id == player_id)).all()
    removed = 0
    for row in rows:
        if row.slot_id not in yes_slot_ids:
            continue
        local_day = normalize_occurrence_start(row.starts_at_utc).astimezone(tz).date()
        if start_day <= local_day <= end_day:
            session.delete(row)
            removed += 1
    if removed:
        session.commit()
    return removed


def clear_all_opt_outs_for_standing_yes(
    session: Session,
    *,
    player: Player,
    slots: list[Slot],
    availability_by_slot: dict[int, AvailabilityStatus],
) -> int:
    """Remove every per-date opt-out on recurring slots where the player has standing *yes*."""
    player_id = player.id
    if player_id is None:
        return 0

    yes_slot_ids = {
        slot.id
        for slot in slots
        if slot.kind is SlotKind.recurring
        and slot.id is not None
        and availability_by_slot.get(slot.id) is AvailabilityStatus.yes
    }
    if not yes_slot_ids:
        return 0

    rows = session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id == player_id)).all()
    removed = 0
    for row in rows:
        if row.slot_id in yes_slot_ids:
            session.delete(row)
            removed += 1
    if removed:
        session.commit()
    return removed

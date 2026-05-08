"""Pure helpers for the per-player template + iCal feed.

Lives outside ``app/routes`` so the same roster math can be unit-tested
without HTTP and reused from other views if needed.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models import (
    AvailabilityStatus,
    Campaign,
    OccurrenceOptOut,
    Player,
    Slot,
    SlotKind,
)
from app.services.availability import (
    load_availability_map,
    roster_can_make_occurrence,
)
from app.services.opt_outs import load_opt_out_set
from app.services.slots import expand_all, upcoming_occurrences_for_slot
from app.services.timeutil import normalize_occurrence_start

# Show "exception" rows up to half a year out at most so the table stays
# scannable even on a long campaign horizon.
_EXCEPTION_HORIZON_WEEKS_CAP = 26


def has_recurring_slot(slots: list[Slot]) -> bool:
    return any(s.kind is SlotKind.recurring for s in slots)


def roster_availability_context(
    session: Session, campaign_id: int
) -> tuple[
    list[Player],
    dict[tuple[int, int], AvailabilityStatus],
    set[tuple[int, int, datetime]],
]:
    """Load roster + full availability map + opt-outs for one campaign."""
    all_players = session.exec(
        select(Player).where(Player.campaign_id == campaign_id).order_by(Player.sort_order)
    ).all()
    full_map = load_availability_map(session, all_players)
    player_ids = [p.id for p in all_players if p.id is not None]
    opt_outs = load_opt_out_set(session, player_ids)
    return all_players, full_map, opt_outs


def primary_occurrence_start_for_counts(slot: Slot, campaign: Campaign) -> datetime | None:
    """UTC start used for roster counts on the main slot table.

    Matches the start the primary "Slot" cell label points at: the next
    upcoming occurrence for recurring rows, or the slot's own start for
    one-offs. Returns ``None`` if the slot has no future occurrence (e.g. an
    expired one-off).
    """
    if slot.kind is SlotKind.recurring:
        z = ZoneInfo(campaign.timezone)
        horizon = min(campaign.horizon_weeks, _EXCEPTION_HORIZON_WEEKS_CAP)
        occs = upcoming_occurrences_for_slot(slot, tz=z, horizon_weeks=horizon)
        if not occs:
            return None
        return occs[0].starts_at_utc
    if slot.kind is SlotKind.adhoc:
        return slot.starts_at_utc
    return None


def slot_can_make_pairs(
    slots: list[Slot],
    campaign: Campaign,
    full_map: dict[tuple[int, int], AvailabilityStatus],
    all_players: list[Player],
    opt_outs: set[tuple[int, int, datetime]],
) -> dict[int, tuple[int, int]]:
    """``slot_id -> (can_make, roster_n)`` for the window shown on that row."""
    out: dict[int, tuple[int, int]] = {}
    for slot in slots:
        sid = slot.id
        if sid is None:
            continue
        start = primary_occurrence_start_for_counts(slot, campaign)
        if start is None:
            continue
        out[sid] = roster_can_make_occurrence(full_map, all_players, opt_outs, slot_id=sid, starts_at_utc=start)
    return out


def unified_recurring_opt_out_rows(
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    session: Session,
    availability_by_slot: dict[int, AvailabilityStatus],
    *,
    all_players: list[Player],
    full_availability: dict[tuple[int, int], AvailabilityStatus],
    opt_outs: set[tuple[int, int, datetime]],
) -> list[dict]:
    """Recurring occurrences in the horizon where this player said *yes*, sorted by start.

    Each row dict is ready for the per-date opt-out fragment template.
    """
    campaign_tz = ZoneInfo(campaign.timezone)
    pid = player.id
    if pid is None:
        return []

    iso_keys: set[tuple[int, str]] = set()
    for row in session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id == pid)).all():
        iso_keys.add((row.slot_id, normalize_occurrence_start(row.starts_at_utc).isoformat()))

    horizon = min(campaign.horizon_weeks, _EXCEPTION_HORIZON_WEEKS_CAP)
    rows: list[dict] = []
    for slot in slots:
        if slot.kind is not SlotKind.recurring:
            continue
        if availability_by_slot.get(slot.id) is not AvailabilityStatus.yes:
            continue
        sid = slot.id
        if sid is None:
            continue
        for o in upcoming_occurrences_for_slot(slot, tz=campaign_tz, horizon_weeks=horizon):
            can_make, roster_n = roster_can_make_occurrence(
                full_availability,
                all_players,
                opt_outs,
                slot_id=sid,
                starts_at_utc=o.starts_at_utc,
            )
            iso = normalize_occurrence_start(o.starts_at_utc).isoformat()
            rows.append(
                {
                    "slot": slot,
                    "occ": o,
                    "start_iso": iso,
                    "busy": (sid, iso) in iso_keys,
                    "can_make": can_make,
                    "roster_n": roster_n,
                }
            )
    rows.sort(key=lambda r: r["occ"].starts_at_utc)
    return rows


def player_calendar_events(
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    session: Session,
) -> list[tuple[str, datetime, datetime, str]]:
    """``(uid, dtstart, dtend, summary)`` tuples for this player's `.ics` feed."""
    pid = player.id
    if pid is None:
        return []
    tz = ZoneInfo(campaign.timezone)
    occurrences = expand_all(slots, tz=tz, horizon_weeks=campaign.horizon_weeks)
    availability = load_availability_map(session, [player])
    opt_outs = load_opt_out_set(session, [pid])
    events: list[tuple[str, datetime, datetime, str]] = []
    for occ in occurrences:
        if availability.get((pid, occ.slot_id)) is not AvailabilityStatus.yes:
            continue
        key = (pid, occ.slot_id, normalize_occurrence_start(occ.starts_at_utc))
        if key in opt_outs:
            continue
        uid = f"{campaign.public_id}-p{pid}-s{occ.slot_id}-{int(occ.starts_at_utc.timestamp())}@whendoweroll.com"
        events.append(
            (
                uid,
                occ.starts_at_utc,
                occ.ends_at_utc,
                f"{campaign.name} — {occ.label} ({player.display_name} available)",
            )
        )
    return events

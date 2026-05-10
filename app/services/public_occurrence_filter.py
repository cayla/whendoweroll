"""Thin recurring occurrences for the public page and consensus ICS only.

Player-facing routes use full ``expand_all`` output unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.models import AvailabilityStatus, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.services.consensus import occurrence_qualifies_under_policy
from app.services.slots import Occurrence


def _apply_public_min_gap_days(
    occurrences: Sequence[Occurrence],
    *,
    tz: ZoneInfo,
    min_gap_days: int,
) -> list[Occurrence]:
    """Drop rows that fall inside ``min_gap_days`` of the previous kept start (local dates)."""
    if min_gap_days <= 0:
        return list(occurrences)
    sorted_occs = sorted(occurrences, key=lambda o: o.starts_at_utc)
    last_kept: date | None = None
    out: list[Occurrence] = []
    for occ in sorted_occs:
        d = occ.starts_at_utc.astimezone(tz).date()
        if last_kept is None:
            out.append(occ)
            last_kept = d
            continue
        if (d - last_kept).days >= min_gap_days:
            out.append(occ)
            last_kept = d
    return out


def filter_occurrences_for_public_display(
    occurrences: Sequence[Occurrence],
    slots: Sequence[Slot],
    *,
    tz: ZoneInfo,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
    public_recurrence_mode: PublicRecurrenceMode,
    public_min_gap_days: int = 0,
) -> list[Occurrence]:
    """Drop recurring dates per ``Campaign.public_recurrence_mode``; keep ad-hoc rows."""
    by_id = {s.id: s for s in slots if s.id is not None}
    mode = public_recurrence_mode
    if not isinstance(mode, PublicRecurrenceMode):
        try:
            mode = PublicRecurrenceMode(str(mode))
        except ValueError:
            mode = PublicRecurrenceMode.weekly

    twice_counts: dict[tuple[int, int], int] = {}
    once_done: set[tuple[int, int]] = set()
    out: list[Occurrence] = []

    for occ in sorted(occurrences, key=lambda o: o.starts_at_utc):
        slot = by_id.get(occ.slot_id)
        if slot is None or slot.kind is not SlotKind.recurring:
            out.append(occ)
            continue

        if mode is PublicRecurrenceMode.weekly:
            out.append(occ)
            continue

        local = occ.starts_at_utc.astimezone(tz)
        key = (local.year, local.month)

        if mode is PublicRecurrenceMode.twice_per_month:
            n = twice_counts.get(key, 0)
            if n >= 2:
                continue
            twice_counts[key] = n + 1
            out.append(occ)
            continue

        if mode is PublicRecurrenceMode.once_per_month:
            if key in once_done:
                continue
            if occurrence_qualifies_under_policy(occ, players, availability, policy, opt_outs):
                once_done.add(key)
                out.append(occ)
            continue

        out.append(occ)

    return _apply_public_min_gap_days(out, tz=tz, min_gap_days=public_min_gap_days)

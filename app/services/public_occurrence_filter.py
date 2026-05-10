"""Thin recurring occurrences for the public page and consensus ICS only.

Player-facing routes use full ``expand_all`` output unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import AvailabilityStatus, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.services.consensus import occurrence_qualifies_under_policy
from app.services.slots import Occurrence


def filter_occurrences_for_public_display(
    occurrences: Sequence[Occurrence],
    slots: Sequence[Slot],
    *,
    tz: ZoneInfo,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
) -> list[Occurrence]:
    """Drop recurring dates per ``Slot.public_recurrence_mode``; keep ad-hoc rows."""
    by_id = {s.id: s for s in slots if s.id is not None}
    twice_counts: dict[tuple[int, int, int], int] = {}
    once_done: set[tuple[int, int, int]] = set()
    out: list[Occurrence] = []

    for occ in sorted(occurrences, key=lambda o: o.starts_at_utc):
        slot = by_id.get(occ.slot_id)
        if slot is None or slot.kind is not SlotKind.recurring:
            out.append(occ)
            continue

        mode = slot.public_recurrence_mode
        if not isinstance(mode, PublicRecurrenceMode):
            try:
                mode = PublicRecurrenceMode(str(mode))
            except ValueError:
                mode = PublicRecurrenceMode.weekly

        if mode is PublicRecurrenceMode.weekly:
            out.append(occ)
            continue

        local = occ.starts_at_utc.astimezone(tz)
        key = (occ.slot_id, local.year, local.month)

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

    return out

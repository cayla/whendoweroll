"""Consensus computation: next time everyone (or everyone-but-one) can meet.

Policy: an *unset* response is treated as **not available** for "next meet".
Players who haven't replied yet should not pull a session into the green;
they have to opt-in. This is conservative on purpose so the organiser
doesn't over-promise.

Per-occurrence opt-outs: if a player said *yes* to a recurring slot but
recorded an opt-out for ``May 29``'s concrete start time, they count as
missing for that occurrence only.

Mandatory attendees: every player with ``Player.is_mandatory == True`` must
be in the yes set (and not opted out) for the occurrence to qualify.
Multiple mandatory attendees are supported — *all* of them must be present.
This rule overrides ``max_missing``: an occurrence with a missing mandatory
attendee never qualifies, even if the total missing count is otherwise low
enough.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.models import AvailabilityStatus, Player
from app.services.slots import Occurrence
from app.services.timeutil import normalize_occurrence_start


@dataclass(frozen=True)
class ConsensusResult:
    occurrence: Occurrence
    yes_player_ids: tuple[int, ...]
    missing_player_ids: tuple[int, ...]  # said no, unset, or opted out

    @property
    def missing_count(self) -> int:
        return len(self.missing_player_ids)


def _mandatory_missing(players: Sequence[Player], missing_ids: tuple[int, ...]) -> bool:
    """True if any mandatory attendee is absent (unset, no, or opted out) for this occurrence."""
    missing = set(missing_ids)
    for player in players:
        pid = player.id  # type: ignore[assignment]
        if player.is_mandatory and pid in missing:
            return True
    return False


def _yes_set_for_occurrence(
    occ: Occurrence,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    opt_outs: set[tuple[int, int, datetime]],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """``opt_outs`` contains ``(player_id, slot_id, normalized_start_datetime)``."""
    occ_key_start = normalize_occurrence_start(occ.starts_at_utc)
    yes_ids: list[int] = []
    missing_ids: list[int] = []
    for player in players:
        pid = player.id  # type: ignore[assignment]
        status = availability.get((pid, occ.slot_id))
        key = (pid, occ.slot_id, occ_key_start)
        if status is AvailabilityStatus.yes and key not in opt_outs:
            yes_ids.append(pid)
        else:
            missing_ids.append(pid)
    return tuple(yes_ids), tuple(missing_ids)


def find_next_meet(
    occurrences: Sequence[Occurrence],
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    *,
    max_missing: int = 0,
    opt_outs: set[tuple[int, int, datetime]] | None = None,
) -> ConsensusResult | None:
    """Return the earliest occurrence whose missing-player count <= ``max_missing``.

    ``availability`` is keyed by ``(player_id, slot_id)``. Anything not in the
    map counts as missing.
    """
    if not players:
        return None
    oo = opt_outs or set()
    for occ in occurrences:
        yes_ids, missing_ids = _yes_set_for_occurrence(occ, players, availability, oo)
        if _mandatory_missing(players, missing_ids):
            continue
        if len(missing_ids) <= max_missing:
            return ConsensusResult(occ, yes_ids, missing_ids)
    return None


def list_consensus_occurrences(
    occurrences: Sequence[Occurrence],
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    *,
    max_missing: int = 0,
    opt_outs: set[tuple[int, int, datetime]] | None = None,
    limit: int = 50,
) -> list[ConsensusResult]:
    """All upcoming windows in order that satisfy the missing-player bound."""
    if not players:
        return []
    oo = opt_outs or set()
    out: list[ConsensusResult] = []
    for occ in occurrences:
        yes_ids, missing_ids = _yes_set_for_occurrence(occ, players, availability, oo)
        if _mandatory_missing(players, missing_ids):
            continue
        if len(missing_ids) <= max_missing:
            out.append(ConsensusResult(occ, yes_ids, missing_ids))
            if len(out) >= limit:
                break
    return out


def player_lookup(players: Sequence[Player]) -> dict[int, Player]:
    return {p.id: p for p in players if p.id is not None}


def count_yes_for_occurrence(
    occ: Occurrence,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    opt_outs: set[tuple[int, int, datetime]] | None = None,
) -> int:
    yes, _missing = _yes_set_for_occurrence(occ, players, availability, opt_outs or set())
    return len(yes)

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
from datetime import datetime, timedelta

from app.models import AvailabilityStatus, ConsensusPolicy, Player
from app.services.slots import Occurrence
from app.services.timeutil import normalize_occurrence_start

# When the soonest qualifying window is all-but-one, prefer a full-consensus
# window that starts within this many hours afterward (e.g. Fri eve → Sat afternoon).
FULL_OVER_NEAR_MAX_DELTA = timedelta(hours=48)


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


def _max_missing_for(policy: ConsensusPolicy) -> int:
    """How many missing players a single window may have under this policy."""
    if policy is ConsensusPolicy.strict:
        return 0
    return 1


def occurrence_qualifies_under_policy(
    occ: Occurrence,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]] | None = None,
) -> bool:
    """Whether this window meets the same bar as public consensus cards (per-window only).

    Does not apply between-window guardrails from ``find_next_meets``; those
    run after the occurrence list is built.

    With an empty ``players`` sequence, returns ``False`` (no one can count as
    present). The public tempo chain therefore yields **no** recurring rows when
    the roster is empty, rather than guessing a first row.
    """
    if not players:
        return False
    _yes_ids, missing_ids = _yes_set_for_occurrence(occ, players, availability, opt_outs or set())
    if _mandatory_missing(players, missing_ids):
        return False
    return len(missing_ids) <= _max_missing_for(policy)


def _occurrence_key(result: ConsensusResult) -> tuple[int, datetime]:
    return (result.occurrence.slot_id, normalize_occurrence_start(result.occurrence.starts_at_utc))


def _maybe_prefer_full_over_near(
    pick: ConsensusResult,
    *,
    policy: ConsensusPolicy,
    full_pool: Sequence[ConsensusResult],
    out: list[ConsensusResult],
    picked_keys: set[tuple[int, datetime]],
) -> ConsensusResult | None:
    """Return a better full-consensus pick, or ``None`` if ``pick`` should be skipped.

    Returns ``None`` when ``pick`` is all-but-one but a nearby full window was
    already chosen (the near window is redundant).
    """
    if pick.missing_count != 1 or policy is ConsensusPolicy.strict:
        return pick
    full_nearby = _find_full_consensus_within_hours_after(full_pool, pick)
    if full_nearby is None:
        return pick
    if _occurrence_key(full_nearby) in picked_keys:
        return None
    if out and _guardrail_blocks(policy, out[-1], full_nearby):
        return pick
    return full_nearby


def _find_full_consensus_within_hours_after(
    full_windows: Sequence[ConsensusResult],
    near: ConsensusResult,
    *,
    max_delta: timedelta = FULL_OVER_NEAR_MAX_DELTA,
) -> ConsensusResult | None:
    """Earliest full-consensus window starting after ``near`` but within ``max_delta``."""
    near_start = near.occurrence.starts_at_utc
    best: ConsensusResult | None = None
    for c in full_windows:
        if c.missing_count != 0:
            continue
        start = c.occurrence.starts_at_utc
        if start <= near_start:
            continue
        if start - near_start > max_delta:
            continue
        if best is None or start < best.occurrence.starts_at_utc:
            best = c
    return best


def _guardrail_blocks(policy: ConsensusPolicy, prev: ConsensusResult, curr: ConsensusResult) -> bool:
    """Between-window guardrail: should ``curr`` be skipped given the previously picked ``prev``?

    Both ``prev`` and ``curr`` already satisfy the per-window ``max_missing``
    bound for the policy. The guardrail is the *sequence* constraint that
    prevents pathological back-to-back near-consensus emissions.
    """
    if policy in (ConsensusPolicy.strict, ConsensusPolicy.allow_one):
        return False
    if policy is ConsensusPolicy.no_two_nears:
        return prev.missing_count > 0 and curr.missing_count > 0
    if policy is ConsensusPolicy.no_repeat_holdout:
        # When either side is full consensus there's no holdout to repeat.
        if not prev.missing_player_ids or not curr.missing_player_ids:
            return False
        return set(prev.missing_player_ids) == set(curr.missing_player_ids)
    return False


def find_next_meets(
    occurrences: Sequence[Occurrence],
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    *,
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]] | None = None,
    limit: int = 2,
    proximity_occurrences: Sequence[Occurrence] | None = None,
) -> list[ConsensusResult]:
    """Greedy forward walk picking up to ``limit`` qualifying upcoming windows.

    Each picked window satisfies the policy's per-window missing bound, and the
    sequence as a whole satisfies the policy's between-window guardrail (e.g.
    no two near-consensus windows in a row). Mandatory-attendee rules apply on
    top of every policy.

    The walk is deliberately greedy: we always take the soonest qualifying
    window, then look forward for the soonest next pick that doesn't trip the
    guardrail relative to it, and so on. This keeps "the next session" as
    close to today as the rules allow, at the cost of *occasionally* surfacing
    a slightly later runner-up than a globally optimal sequence might.

    **Full-over-near proximity:** Whenever a pick would be all-but-one, look for
    the earliest **full** window within ``FULL_OVER_NEAR_MAX_DELTA`` (48 hours)
    afterward in ``proximity_occurrences``. Public routes pass the **expanded**
    horizon (before tempo thinning) so
    a full Saturday is not missed when Friday is the tempo-chain row. Policies
    that never allow a holdout (``strict``) skip this step.

    Used by both the public-page summary cards and the consensus ``.ics`` feed
    (both use ``PUBLIC_LOCKED_SESSION_LIMIT`` from ``consensus_ics``); the feed
    is intentionally tight to match the cards so subscribers can rely on it as
    the actual play schedule.

    **Ordering vs tempo:** Callers (e.g. the public routes) usually pass
    occurrences that have already been **tempo-thinned** by
    ``filter_occurrences_for_public_display``. This function then walks that
    list in time order, keeping each window that satisfies the per-window
    missing bound **and** does not violate the policy's **between-window**
    guardrails (e.g. ``no_two_nears``). So the first green summary card is **not**
    guaranteed to be the first tempo-chain row: it is the first row that survives
    *both* the tempo pass and this guardrail pass. A chronologically earlier
    window can be skipped if it would pair badly with the previous kept card.
    """
    candidates = list_consensus_occurrences(
        occurrences,
        players,
        availability,
        max_missing=_max_missing_for(policy),
        opt_outs=opt_outs,
        limit=max(limit * 4, 200),
    )
    full_pool: list[ConsensusResult] = []
    if proximity_occurrences is not None and policy is not ConsensusPolicy.strict:
        full_pool = list_consensus_occurrences(
            proximity_occurrences,
            players,
            availability,
            max_missing=0,
            opt_outs=opt_outs,
            limit=500,
        )
    out: list[ConsensusResult] = []
    picked_keys: set[tuple[int, datetime]] = set()
    for c in candidates:
        if _occurrence_key(c) in picked_keys:
            continue
        if out and _guardrail_blocks(policy, out[-1], c):
            continue
        pick = c
        if full_pool:
            pick = _maybe_prefer_full_over_near(
                c, policy=policy, full_pool=full_pool, out=out, picked_keys=picked_keys
            )
        if pick is None:
            picked_keys.add(_occurrence_key(c))
            continue
        picked_keys.add(_occurrence_key(pick))
        if pick is not c:
            picked_keys.add(_occurrence_key(c))
        out.append(pick)
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


def count_availability_buckets_for_occurrence(
    occ: Occurrence,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    opt_outs: set[tuple[int, int, datetime]] | None = None,
) -> tuple[int, int, int]:
    """Roster counts for one concrete session: ``(can_make, cant_make, no_answer)``.

    * **can_make** — standing *yes* on the slot and not opted out of this start.
    * **cant_make** — standing *no*, or *yes* but opted out for this occurrence.
    * **no_answer** — no saved answer yet for this slot (unset for consensus).
    """
    oo = opt_outs or set()
    occ_key_start = normalize_occurrence_start(occ.starts_at_utc)
    can_make = 0
    cant_make = 0
    no_answer = 0
    for player in players:
        pid = player.id  # type: ignore[assignment]
        if pid is None:
            continue
        status = availability.get((pid, occ.slot_id))
        key = (pid, occ.slot_id, occ_key_start)
        if status is AvailabilityStatus.yes and key not in oo:
            can_make += 1
        elif status is AvailabilityStatus.no or (status is AvailabilityStatus.yes and key in oo):
            cant_make += 1
        else:
            no_answer += 1
    return can_make, cant_make, no_answer

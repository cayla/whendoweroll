"""Consensus math: finds earliest occurrence with <= max_missing missing players."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import AvailabilityStatus, Player
from app.services.consensus import find_next_meet
from app.services.slots import Occurrence
from app.services.timeutil import normalize_occurrence_start


def _occ(slot_id: int, hours_from_now: int) -> Occurrence:
    start = datetime.now(UTC) + timedelta(hours=hours_from_now)
    return Occurrence(
        slot_id=slot_id,
        label=f"slot {slot_id}",
        starts_at_utc=start,
        ends_at_utc=start + timedelta(hours=3),
    )


def _player(pid: int, name: str) -> Player:
    return Player(id=pid, campaign_id=1, display_name=name, token_hash=f"h{pid}")


def test_no_players_returns_none():
    occs = [_occ(1, 24)]
    assert find_next_meet(occs, [], {}) is None


def test_unset_counts_as_unavailable_for_strict_consensus():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {(1, 1): AvailabilityStatus.yes}  # B never replied
    assert find_next_meet(occs, players, availability, max_missing=0) is None


def test_strict_consensus_picks_earliest_full_yes():
    # Slot 1 has player 2 saying no (disqualifies); slot 2 has full yes.
    occs = [_occ(1, 24), _occ(2, 48)]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.no,
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
    }
    result = find_next_meet(occs, players, availability, max_missing=0)
    assert result is not None
    assert result.occurrence.slot_id == 2
    assert result.missing_count == 0


def test_all_but_one_picks_earliest_window_with_one_holdout():
    occs = [_occ(1, 24), _occ(2, 48)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        # Player 3 didn't reply -> counts as missing.
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
    }
    result = find_next_meet(occs, players, availability, max_missing=1)
    assert result is not None
    assert result.occurrence.slot_id == 1
    assert result.missing_player_ids == (3,)


def test_recurring_slot_id_shared_across_occurrences():
    """Each Friday window shares the same slot_id, so a single 'yes' counts
    for every future Friday. This is the 'indefinite choices' policy.
    """
    occs = [_occ(7, 24), _occ(7, 24 * 8), _occ(7, 24 * 15)]  # three Fridays
    players = [_player(1, "A")]
    availability = {(1, 7): AvailabilityStatus.yes}
    result = find_next_meet(occs, players, availability, max_missing=0)
    assert result is not None
    assert result.occurrence.starts_at_utc == occs[0].starts_at_utc


def test_opt_out_skips_player_for_that_occurrence_only():
    t0 = datetime.now(UTC) + timedelta(hours=24)
    t1 = datetime.now(UTC) + timedelta(hours=48)
    occs = [
        Occurrence(1, "a", t0, t0 + timedelta(hours=3)),
        Occurrence(1, "a", t1, t1 + timedelta(hours=3)),
    ]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
    }
    opt = {(1, 1, normalize_occurrence_start(t0))}
    result = find_next_meet(occs, players, availability, max_missing=0, opt_outs=opt)
    assert result is not None
    assert normalize_occurrence_start(result.occurrence.starts_at_utc) == normalize_occurrence_start(t1)


def test_returns_none_when_nothing_qualifies():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        # Two players unset -> two missing, exceeds max_missing=1.
    }
    assert find_next_meet(occs, players, availability, max_missing=1) is None

"""Consensus math: finds earliest occurrence with <= max_missing missing players."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import AvailabilityStatus, Player
from app.services.consensus import find_next_meet, find_next_two_meets
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


# ---------------------------------------------------------------------------
# find_next_two_meets: the two-card landing helper. Drives the public page,
# whose constraint is "never two near-consensus rows in a row".
# ---------------------------------------------------------------------------


def test_next_two_returns_empty_when_nothing_qualifies():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {(1, 1): AvailabilityStatus.yes}  # 2 missing -> nothing qualifies.
    assert find_next_two_meets(occs, players, availability) == []


def test_next_two_returns_single_when_only_one_qualifies():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {(1, 1): AvailabilityStatus.yes, (2, 1): AvailabilityStatus.yes}
    out = find_next_two_meets(occs, players, availability)
    assert len(out) == 1
    assert out[0].missing_count == 0


def test_next_two_picks_two_full_consensus_in_order():
    occs = [_occ(7, 24), _occ(7, 24 * 8), _occ(7, 24 * 15)]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {(1, 7): AvailabilityStatus.yes, (2, 7): AvailabilityStatus.yes}
    out = find_next_two_meets(occs, players, availability)
    assert len(out) == 2
    assert all(r.missing_count == 0 for r in out)
    assert out[0].occurrence.starts_at_utc < out[1].occurrence.starts_at_utc


def test_next_two_full_then_near_keeps_chronological_pair():
    """If chronologically the 2nd window is near-consensus, we still show it
    because the 1st card is the "everyone" anchor — only one near in a row.
    """
    occs = [_occ(1, 24), _occ(2, 48)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        # Slot 1: full consensus.
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        (3, 1): AvailabilityStatus.yes,
        # Slot 2: C unset -> near-consensus.
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
    }
    out = find_next_two_meets(occs, players, availability)
    assert len(out) == 2
    assert out[0].missing_count == 0
    assert out[1].missing_count == 1
    assert out[1].missing_player_ids == (3,)


def test_next_two_skips_second_near_in_a_row_to_show_full_consensus():
    """Chronological order: near, near, full. We must not show two nears in a
    row, so the helper jumps over the 2nd near to the next full consensus.
    """
    occs = [_occ(1, 24), _occ(2, 48), _occ(3, 72)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        # Slot 1 (earliest): C missing -> near.
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        # Slot 2: B missing -> near. Would be the chronological #2.
        (1, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
        # Slot 3: full consensus -> what we expect as the second card.
        (1, 3): AvailabilityStatus.yes,
        (2, 3): AvailabilityStatus.yes,
        (3, 3): AvailabilityStatus.yes,
    }
    out = find_next_two_meets(occs, players, availability)
    assert len(out) == 2
    assert out[0].occurrence.slot_id == 1
    assert out[0].missing_count == 1
    assert out[1].occurrence.slot_id == 3
    assert out[1].missing_count == 0


def test_next_two_returns_solo_near_when_no_full_consensus_exists():
    """Group never has a full-yes window? Show the one near-consensus card
    rather than padding with another near (the rule forbids two nears).
    """
    occs = [_occ(1, 24), _occ(2, 48)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
    }
    out = find_next_two_meets(occs, players, availability)
    assert len(out) == 1
    assert out[0].missing_count == 1
    assert out[0].occurrence.slot_id == 1


def test_next_two_collapses_when_mandatory_blocks_earlier_nears():
    """Edge case from the wild: mandatory attendee declines early occurrences,
    so the only qualifying window is the full-consensus one. Both cards used
    to point at the same date — now we return [full, full] instead of
    [full, full] duplicated, listing the *next* full consensus as #2.
    """
    occs = [_occ(1, 24), _occ(1, 24 * 8), _occ(1, 24 * 15)]  # weekly recurring slot
    gm = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    pl = Player(id=2, campaign_id=1, display_name="P", token_hash="h2", is_mandatory=False)
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
    }
    # GM opts out of the first occurrence specifically.
    opt = {(1, 1, normalize_occurrence_start(occs[0].starts_at_utc))}
    out = find_next_two_meets(occs, [gm, pl], availability, opt_outs=opt)
    assert len(out) == 2
    assert out[0].missing_count == 0
    assert out[1].missing_count == 0
    # The first occurrence is filtered (mandatory missing), so we expect
    # the next two upcoming occurrences instead.
    assert normalize_occurrence_start(out[0].occurrence.starts_at_utc) == normalize_occurrence_start(
        occs[1].starts_at_utc
    )
    assert normalize_occurrence_start(out[1].occurrence.starts_at_utc) == normalize_occurrence_start(
        occs[2].starts_at_utc
    )

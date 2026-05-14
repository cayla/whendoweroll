"""Consensus math: finds earliest occurrence with <= max_missing missing players."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import AvailabilityStatus, ConsensusPolicy, Player
from app.services.consensus import find_next_meet, find_next_meets
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
# find_next_meets: greedy forward walk that drives both the public summary
# cards (limit=2) and the consensus ICS feed (large limit). Each policy has
# its own per-window bound and between-window guardrail.
# ---------------------------------------------------------------------------


def _three_player_chrono_nears_then_full():
    """Fixture: three windows in chronological order — near (C missing),
    near (B missing), full consensus. Reused by several policy tests.
    """
    occs = [_occ(1, 24), _occ(2, 48), _occ(3, 72)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
        (1, 3): AvailabilityStatus.yes,
        (2, 3): AvailabilityStatus.yes,
        (3, 3): AvailabilityStatus.yes,
    }
    return occs, players, availability


def test_next_meets_returns_empty_when_nothing_qualifies():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {(1, 1): AvailabilityStatus.yes}  # 2 missing -> over even allow_one bound
    assert find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_two_nears) == []


def test_next_meets_strict_only_returns_full_consensus_windows():
    occs, players, availability = _three_player_chrono_nears_then_full()
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.strict, limit=5)
    assert len(out) == 1  # only slot 3 is full consensus
    assert out[0].occurrence.slot_id == 3
    assert out[0].missing_count == 0


def test_next_meets_allow_one_takes_consecutive_nears_in_order():
    """No guardrail under allow_one: just walk forward greedily."""
    occs, players, availability = _three_player_chrono_nears_then_full()
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.allow_one, limit=5)
    assert [r.occurrence.slot_id for r in out] == [1, 2, 3]


def test_next_meets_no_two_nears_skips_second_near_to_next_full():
    occs, players, availability = _three_player_chrono_nears_then_full()
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_two_nears, limit=5)
    assert [r.occurrence.slot_id for r in out] == [1, 3]
    assert out[0].missing_count == 1
    assert out[1].missing_count == 0


def test_next_meets_no_repeat_holdout_allows_different_holdout_back_to_back():
    """Slot 1 has C missing; slot 2 has B missing. Different people, so the
    no_repeat_holdout policy lets them sit adjacent — only the same holdout
    twice in a row is forbidden.
    """
    occs, players, availability = _three_player_chrono_nears_then_full()
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_repeat_holdout, limit=5)
    assert [r.occurrence.slot_id for r in out] == [1, 2, 3]


def test_next_meets_no_repeat_holdout_skips_when_same_person_misses_twice():
    """If the same player is the holdout in two adjacent qualifying windows,
    the second is dropped — bridge over to a window with someone else missing
    or with full consensus.
    """
    occs = [_occ(1, 24), _occ(2, 48), _occ(3, 72)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        # Slot 1: C missing.
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        # Slot 2: C missing again.
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
        # Slot 3: full consensus.
        (1, 3): AvailabilityStatus.yes,
        (2, 3): AvailabilityStatus.yes,
        (3, 3): AvailabilityStatus.yes,
    }
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_repeat_holdout, limit=5)
    assert [r.occurrence.slot_id for r in out] == [1, 3]


def test_next_meets_returns_single_when_only_one_window_exists():
    occs = [_occ(1, 24)]
    players = [_player(1, "A"), _player(2, "B")]
    availability = {(1, 1): AvailabilityStatus.yes, (2, 1): AvailabilityStatus.yes}
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_two_nears, limit=2)
    assert len(out) == 1
    assert out[0].missing_count == 0


def test_next_meets_no_two_nears_returns_solo_near_when_no_full_exists():
    """Pathological campaign: no full-consensus window in the horizon. The
    no-two-nears rule forbids padding with a second near, so we honestly
    return just one card.
    """
    occs = [_occ(1, 24), _occ(2, 48)]
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
    }
    out = find_next_meets(occs, players, availability, policy=ConsensusPolicy.no_two_nears, limit=2)
    assert len(out) == 1
    assert out[0].missing_count == 1
    assert out[0].occurrence.slot_id == 1


def test_next_meets_mandatory_blocks_earlier_nears_so_first_pick_is_full_consensus():
    """The original wild edge case: alice (mandatory) blocks the first two
    weekly occurrences, so under any policy the first qualifying window is
    the third occurrence (full consensus) — and the second card moves on
    to the *next* occurrence rather than echoing the first.
    """
    occs = [_occ(1, 24), _occ(1, 24 * 8), _occ(1, 24 * 15)]  # weekly recurring slot
    gm = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    pl = Player(id=2, campaign_id=1, display_name="P", token_hash="h2", is_mandatory=False)
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
    }
    opt = {(1, 1, normalize_occurrence_start(occs[0].starts_at_utc))}
    out = find_next_meets(occs, [gm, pl], availability, policy=ConsensusPolicy.no_two_nears, opt_outs=opt, limit=2)
    assert len(out) == 2
    assert all(r.missing_count == 0 for r in out)
    assert normalize_occurrence_start(out[0].occurrence.starts_at_utc) == normalize_occurrence_start(
        occs[1].starts_at_utc
    )
    assert normalize_occurrence_start(out[1].occurrence.starts_at_utc) == normalize_occurrence_start(
        occs[2].starts_at_utc
    )


def test_bucket_counts_full_yes():
    from app.services.consensus import count_availability_buckets_for_occurrence

    occ = _occ(1, 24)
    players = [_player(1, "A"), _player(2, "B")]
    av = {(1, 1): AvailabilityStatus.yes, (2, 1): AvailabilityStatus.yes}
    assert count_availability_buckets_for_occurrence(occ, players, av, set()) == (2, 0, 0)


def test_bucket_counts_never_cant_and_unset():
    from app.services.consensus import count_availability_buckets_for_occurrence

    occ = _occ(3, 48)
    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    av = {(1, 3): AvailabilityStatus.yes, (2, 3): AvailabilityStatus.no}
    assert count_availability_buckets_for_occurrence(occ, players, av, set()) == (1, 1, 1)


def test_bucket_yes_with_opt_out_counts_as_cant():
    from app.services.consensus import count_availability_buckets_for_occurrence

    occ = _occ(5, 72)
    players = [_player(1, "A"), _player(2, "B")]
    av = {(1, 5): AvailabilityStatus.yes, (2, 5): AvailabilityStatus.yes}
    key = normalize_occurrence_start(occ.starts_at_utc)
    opt = {(1, 5, key)}
    assert count_availability_buckets_for_occurrence(occ, players, av, opt) == (1, 1, 0)

"""Public-only occurrence thinning (player views use full expansion)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from app.models import AvailabilityStatus, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.services.public_occurrence_filter import _pick_rhythm_occurrence, filter_occurrences_for_public_display
from app.services.slots import Occurrence, expand_all
from app.services.timeutil import normalize_occurrence_start


def _player(pid: int, name: str) -> Player:
    return Player(id=pid, campaign_id=1, display_name=name, token_hash=f"h{pid}")


def _occ(slot_id: int, start: datetime, hours: float = 2.0) -> Occurrence:
    end = start + timedelta(hours=hours)
    return Occurrence(
        slot_id=slot_id,
        label="test",
        starts_at_utc=start,
        ends_at_utc=end,
        kind=SlotKind.recurring,
    )


def test_rhythm_picks_near_ideal_when_exact_anchor_is_short_handed():
    """May 17 anchor fails strict consensus → prefer May 16 over May 20 (closer to ideal)."""
    tz = ZoneInfo("UTC")
    last = _occ(3, datetime(2026, 5, 10, 12, 0, tzinfo=UTC))
    ideal = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    may13 = _occ(1, datetime(2026, 5, 13, 19, 0, tzinfo=UTC))
    may16 = _occ(2, datetime(2026, 5, 16, 12, 0, tzinfo=UTC))
    may17_bad = _occ(3, datetime(2026, 5, 17, 12, 0, tzinfo=UTC))
    may20 = _occ(1, datetime(2026, 5, 20, 19, 0, tzinfo=UTC))
    window = [may13, may16, may17_bad, may20]

    players = [_player(1, "A"), _player(2, "B"), _player(3, "C")]
    avail = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        (3, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
        (3, 2): AvailabilityStatus.yes,
        (1, 3): AvailabilityStatus.yes,
        (2, 3): AvailabilityStatus.no,
        (3, 3): AvailabilityStatus.yes,
    }
    pick = _pick_rhythm_occurrence(
        window,
        last_occ=last,
        ideal_utc=ideal,
        period_days=7,
        tz=tz,
        players=players,
        availability=avail,
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
    )
    assert pick.starts_at_utc == may16.starts_at_utc


def test_twice_per_month_picks_two_spaced_by_closest_to_fourteen_day_beat():
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=0,
        start_local="10:00",
        duration_hours=1.0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all([slot], tz=tz, horizon_weeks=5, now=now)
    jan_all = [o for o in full if o.starts_at_utc.astimezone(tz).month == 1]
    assert len(jan_all) == 4

    players = [_player(1, "A")]
    filtered = filter_occurrences_for_public_display(
        full,
        [slot],
        tz=tz,
        players=players,
        availability={(1, 1): AvailabilityStatus.yes},
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
        public_recurrence_mode=PublicRecurrenceMode.twice_per_month,
    )
    jan_pub = [o for o in filtered if o.starts_at_utc.astimezone(tz).month == 1]
    assert len(jan_pub) == 2
    assert jan_pub[0].starts_at_utc.astimezone(tz).day == 6
    # Second pick is closest to Jan 6 + 14d (= Jan 20) among later Mondays → Jan 20, not Jan 13.
    assert jan_pub[1].starts_at_utc.astimezone(tz).day == 20


def test_twice_per_month_tempo_chain_across_two_slots():
    mon = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=0,
        start_local="10:00",
        duration_hours=1.0,
    )
    wed = Slot(
        id=2,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=2,
        start_local="14:00",
        duration_hours=1.0,
    )
    slots = [mon, wed]
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all(slots, tz=tz, horizon_weeks=3, now=now)
    jan_pub = filter_occurrences_for_public_display(
        full,
        slots,
        tz=tz,
        players=[_player(1, "A")],
        availability={(1, 1): AvailabilityStatus.yes, (1, 2): AvailabilityStatus.yes},
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
        public_recurrence_mode=PublicRecurrenceMode.twice_per_month,
    )
    jan = [o for o in jan_pub if o.starts_at_utc.astimezone(tz).month == 1]
    # 14-day tempo can surface more than two January rows when the horizon is short; the chain
    # is no longer capped at "two per calendar month".
    assert len(jan) >= 2


def test_weekly_rhythm_spacing():
    """Weekly tempo snaps picks toward a 7-day beat (bracket + soft slot rotation)."""
    wed = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=2,
        start_local="12:00",
        duration_hours=1.0,
    )
    sat = Slot(
        id=2,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=5,
        start_local="12:00",
        duration_hours=1.0,
    )
    sun = Slot(
        id=3,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=6,
        start_local="12:00",
        duration_hours=1.0,
    )
    slots = [wed, sat, sun]
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all(slots, tz=tz, horizon_weeks=5, now=now)
    avail = {(1, 1): AvailabilityStatus.yes, (1, 2): AvailabilityStatus.yes, (1, 3): AvailabilityStatus.yes}
    players = [_player(1, "A")]
    default_beat = filter_occurrences_for_public_display(
        full,
        slots,
        tz=tz,
        players=players,
        availability=avail,
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
        public_recurrence_mode=PublicRecurrenceMode.weekly,
    )
    assert len(default_beat) < len(full)
    dates = [o.starts_at_utc.astimezone(tz).date() for o in default_beat]
    for a, b in pairwise(dates):
        # Mostly one week apart; the last hop can be shorter when the horizon ends mid-beat.
        assert (b - a).days >= 4


def test_once_per_month_picks_earliest_in_month():
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=4,
        start_local="18:00",
        duration_hours=2.0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all([slot], tz=tz, horizon_weeks=10, now=now)
    players = [_player(1, "A")]
    availability = {(1, 1): AvailabilityStatus.yes}
    filtered = filter_occurrences_for_public_display(
        full,
        [slot],
        tz=tz,
        players=players,
        availability=availability,
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
        public_recurrence_mode=PublicRecurrenceMode.once_per_month,
    )
    jan_pub = [o for o in filtered if o.starts_at_utc.astimezone(tz).month == 1]
    assert len(jan_pub) == 1
    # Earliest qualifying Friday in January (not mid-month pinned).
    assert jan_pub[0].starts_at_utc.astimezone(tz).day == 3


def test_tempo_chain_starts_at_first_policy_qualifying_not_earliest_row():
    """First public pick is earliest qualifying window, not earliest row when it fails policy."""
    mon = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=0,
        start_local="12:00",
        duration_hours=1.0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all([mon], tz=tz, horizon_weeks=3, now=now)
    first_mon = next(o for o in full if o.starts_at_utc.astimezone(tz).date() == date(2025, 1, 6))
    oo = {(1, 1, normalize_occurrence_start(first_mon.starts_at_utc))}
    players = [_player(1, "A")]
    avail = {(1, 1): AvailabilityStatus.yes}
    filtered = filter_occurrences_for_public_display(
        full,
        [mon],
        tz=tz,
        players=players,
        availability=avail,
        policy=ConsensusPolicy.strict,
        opt_outs=oo,
        public_recurrence_mode=PublicRecurrenceMode.weekly,
    )
    assert filtered[0].starts_at_utc.astimezone(tz).day == 13


def test_monthly_tempo_second_anchor_one_calendar_month_after_first():
    fri = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=4,
        start_local="18:00",
        duration_hours=2.0,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all([fri], tz=tz, horizon_weeks=12, now=now)
    players = [_player(1, "A")]
    filtered = filter_occurrences_for_public_display(
        full,
        [fri],
        tz=tz,
        players=players,
        availability={(1, 1): AvailabilityStatus.yes},
        policy=ConsensusPolicy.strict,
        opt_outs=set(),
        public_recurrence_mode=PublicRecurrenceMode.once_per_month,
    )
    assert filtered[0].starts_at_utc.astimezone(tz).date() == date(2025, 1, 3)
    # Ideal one month after Jan 3 is Feb 3; closest Friday in bracket is Feb 7.
    assert filtered[1].starts_at_utc.astimezone(tz).date() == date(2025, 2, 7)

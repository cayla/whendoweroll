"""Public-only occurrence thinning (player views use full expansion)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import AvailabilityStatus, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.services.public_occurrence_filter import filter_occurrences_for_public_display
from app.services.slots import expand_all


def _player(pid: int, name: str) -> Player:
    return Player(id=pid, campaign_id=1, display_name=name, token_hash=f"h{pid}")


def test_twice_per_month_keeps_first_two_weekdays_per_month():
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=0,
        start_local="10:00",
        duration_hours=1.0,
        public_recurrence_mode=PublicRecurrenceMode.twice_per_month,
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
    )
    jan_pub = [o for o in filtered if o.starts_at_utc.astimezone(tz).month == 1]
    assert len(jan_pub) == 2
    assert jan_pub[0].starts_at_utc.astimezone(tz).day == 6
    assert jan_pub[1].starts_at_utc.astimezone(tz).day == 13


def test_once_per_month_keeps_first_policy_qualifying_date():
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=4,
        start_local="18:00",
        duration_hours=2.0,
        public_recurrence_mode=PublicRecurrenceMode.once_per_month,
    )
    tz = ZoneInfo("UTC")
    now = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    full = expand_all([slot], tz=tz, horizon_weeks=5, now=now)
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
    )
    jan_pub = [o for o in filtered if o.starts_at_utc.astimezone(tz).month == 1]
    assert len(jan_pub) == 1
    assert jan_pub[0].starts_at_utc.astimezone(tz).day == 3

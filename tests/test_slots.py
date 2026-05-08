"""Slot expansion, including a DST transition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import Slot, SlotKind
from app.services.slots import expand_all, expand_recurring


def test_recurring_friday_yields_only_fridays():
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=4,
        start_local="18:00",
        duration_hours=3.0,
        label="Friday",
    )
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 5, 1, tzinfo=tz).astimezone(UTC)
    end = start + timedelta(weeks=4)
    occs = list(expand_recurring(slot, tz=tz, start=start, end=end))
    assert len(occs) == 4
    for occ in occs:
        local = occ.starts_at_utc.astimezone(tz)
        assert local.weekday() == 4
        assert local.hour == 18
        assert local.minute == 0


def test_dst_spring_forward_keeps_local_wall_time():
    """In US DST, the second Sunday of March springs forward at 02:00.
    A Sunday 19:00 slot stays at 19:00 *local* on both sides — its UTC
    offset shifts by an hour, which is exactly what we want for a player
    who said 'yes' to Sunday evenings.
    """
    slot = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=6,
        start_local="19:00",
        duration_hours=3.0,
    )
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 1, tzinfo=tz).astimezone(UTC)
    end = datetime(2026, 3, 31, tzinfo=tz).astimezone(UTC)
    occs = list(expand_recurring(slot, tz=tz, start=start, end=end))

    pre_dst = [o for o in occs if o.starts_at_utc.astimezone(tz).day == 1]
    post_dst = [o for o in occs if o.starts_at_utc.astimezone(tz).day == 15]
    assert pre_dst and post_dst

    pre = pre_dst[0].starts_at_utc.astimezone(tz)
    post = post_dst[0].starts_at_utc.astimezone(tz)
    assert pre.hour == 19
    assert post.hour == 19
    assert pre.utcoffset() != post.utcoffset()  # offset changed across DST


def test_adhoc_slot_expanded_to_single_occurrence():
    future = datetime.now(UTC) + timedelta(days=10)
    slot = Slot(
        id=2,
        campaign_id=1,
        kind=SlotKind.adhoc,
        starts_at_utc=future,
        ends_at_utc=future + timedelta(hours=4),
        duration_hours=4.0,
        label="One-shot",
    )
    occs = expand_all([slot], tz=ZoneInfo("UTC"), horizon_weeks=4)
    assert len(occs) == 1
    assert occs[0].label == "One-shot"
    assert occs[0].slot_id == 2


def test_past_adhoc_dropped_from_horizon():
    past = datetime.now(UTC) - timedelta(days=2)
    slot = Slot(
        id=3,
        campaign_id=1,
        kind=SlotKind.adhoc,
        starts_at_utc=past,
        ends_at_utc=past + timedelta(hours=2),
        duration_hours=2.0,
    )
    assert expand_all([slot], tz=ZoneInfo("UTC"), horizon_weeks=4) == []


def test_occurrences_sorted_chronologically():
    tz = ZoneInfo("UTC")
    in_5_days = datetime.now(UTC) + timedelta(days=5)
    in_2_days = datetime.now(UTC) + timedelta(days=2)
    slots = [
        Slot(
            id=1,
            campaign_id=1,
            kind=SlotKind.adhoc,
            starts_at_utc=in_5_days,
            ends_at_utc=in_5_days + timedelta(hours=1),
            duration_hours=1.0,
        ),
        Slot(
            id=2,
            campaign_id=1,
            kind=SlotKind.adhoc,
            starts_at_utc=in_2_days,
            ends_at_utc=in_2_days + timedelta(hours=1),
            duration_hours=1.0,
        ),
    ]
    occs = expand_all(slots, tz=tz, horizon_weeks=4)
    assert [o.slot_id for o in occs] == [2, 1]

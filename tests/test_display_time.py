"""Viewer-local window formatting for recurring / exception rows."""

from __future__ import annotations

from datetime import UTC, datetime

from app.display_time import format_local_window, player_slot_public_frequency_caption
from app.models import PublicRecurrenceMode, Slot, SlotKind


def test_format_local_window_same_day():
    # Fri 2026-05-08 22:00 UTC = Fri 18:00 America/New_York (EDT)
    start = datetime(2026, 5, 8, 22, 0, tzinfo=UTC)
    end = datetime(2026, 5, 9, 1, 0, tzinfo=UTC)
    s = format_local_window(start, end, "America/New_York")
    assert "Fri" in s
    assert "6:00 PM" in s or "06:00 PM" in s  # platform %-I
    assert "9:00 PM" in s or "09:00 PM" in s
    # The viewer's zone is shown once at the top of the page; per-row tz
    # suffixes were intentionally dropped.
    assert "EDT" not in s
    assert "EST" not in s


def test_format_local_window_cross_day():
    # Fri 2026-05-08 02:00 UTC = Thu 22:00 America/New_York (EDT)
    start = datetime(2026, 5, 8, 2, 0, tzinfo=UTC)
    end = datetime(2026, 5, 8, 6, 0, tzinfo=UTC)
    s = format_local_window(start, end, "America/New_York")
    assert "Thu" in s
    assert "Fri" in s
    assert "EDT" not in s
    assert "EST" not in s


def test_player_public_frequency_caption_recurring_only():
    recurring = Slot(
        id=1,
        campaign_id=1,
        kind=SlotKind.recurring,
        weekday=4,
        start_local="19:00",
        duration_hours=3.0,
        public_recurrence_mode=PublicRecurrenceMode.twice_per_month,
    )
    assert player_slot_public_frequency_caption(recurring) == "Tempo: biweekly / twice a month"
    adhoc = Slot(
        id=2,
        campaign_id=1,
        kind=SlotKind.adhoc,
        duration_hours=2.0,
        starts_at_utc=datetime.now(UTC),
        ends_at_utc=datetime.now(UTC),
    )
    assert player_slot_public_frequency_caption(adhoc) == ""

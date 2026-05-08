"""Viewer-local window formatting for recurring / exception rows."""

from __future__ import annotations

from datetime import UTC, datetime

from app.display_time import format_local_window


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

"""iCalendar builder smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.ical import build_ics


def test_build_ics_contains_calendar_wrappers():
    body = build_ics([])
    assert b"BEGIN:VCALENDAR" in body
    assert b"END:VCALENDAR" in body


def test_build_ics_single_event():
    start = datetime(2026, 5, 29, 22, 0, tzinfo=UTC)
    end = start + timedelta(hours=3)
    body = build_ics([("uid-test@whendoweroll.com", start, end, "Game night")])
    assert b"BEGIN:VEVENT" in body
    assert b"DTSTART:20260529T220000Z" in body
    assert b"SUMMARY:Game night" in body


def test_build_ics_emits_refresh_hints_for_subscribed_clients():
    """Apple Calendar / Outlook / Thunderbird respect these TTL hints when
    the user hasn't picked a manual refresh interval; ship both the legacy
    Microsoft form and the RFC 7986 form for maximum coverage.
    """
    body = build_ics([]).decode("utf-8")
    assert "X-PUBLISHED-TTL:PT1H" in body
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in body

"""iCalendar builder smoke tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.ical import build_ics


def test_build_ics_contains_calendar_wrappers():
    body = build_ics([])
    assert b"BEGIN:VCALENDAR" in body
    assert b"END:VCALENDAR" in body


def test_build_ics_single_event():
    start = datetime(2026, 5, 29, 22, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=3)
    body = build_ics([("uid-test@whendoweroll.com", start, end, "Game night")])
    assert b"BEGIN:VEVENT" in body
    assert b"DTSTART:20260529T220000Z" in body
    assert b"SUMMARY:Game night" in body

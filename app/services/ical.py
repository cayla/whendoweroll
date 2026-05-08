"""Minimal RFC 5545 iCalendar generation (UTF-8, UTC DTSTART/DTEND)."""

from __future__ import annotations

from datetime import UTC, datetime


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _ics_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


# Suggested polling cadence for subscribed calendar clients. Apple Calendar,
# Outlook, and Thunderbird honour these hints when the user hasn't picked
# a manual refresh interval; Google Calendar ignores them and polls on its
# own (typically several hours to a day) — there's nothing we can do about
# that from the server side. ``X-PUBLISHED-TTL`` is the older Microsoft form
# (still widely respected) and ``REFRESH-INTERVAL`` is the RFC 7986 standard;
# emit both for maximum client coverage.
_REFRESH_INTERVAL = "PT1H"


def build_ics(events: list[tuple[str, datetime, datetime, str]]) -> bytes:
    """Each tuple is ``(uid, dtstart, dtend, summary)``."""
    stamp = _ics_dt(datetime.now(UTC))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//whendoweroll.com//EN",
        "CALSCALE:GREGORIAN",
        f"X-PUBLISHED-TTL:{_REFRESH_INTERVAL}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{_REFRESH_INTERVAL}",
    ]
    for uid, start, end, summary in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{_ics_dt(start)}",
                f"DTEND:{_ics_dt(end)}",
                f"SUMMARY:{_ics_escape(summary)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")

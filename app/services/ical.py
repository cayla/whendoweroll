"""Minimal RFC 5545 iCalendar generation (UTF-8, UTC DTSTART/DTEND)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


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

# Far-past anchor so placeholder events stay out of "upcoming" views.
_PLACEHOLDER_START = datetime(2000, 1, 1, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class IcsEvent:
    uid: str
    start: datetime
    end: datetime
    summary: str
    cancelled: bool = False
    transparent: bool = False


def placeholder_consensus_event(public_id: str, campaign_name: str) -> IcsEvent:
    """Shadow event for empty consensus feeds — keeps picky clients (e.g. Apple) happy."""
    start = _PLACEHOLDER_START
    return IcsEvent(
        uid=f"{public_id}-placeholder@whendoweroll.com",
        start=start,
        end=start + timedelta(minutes=1),
        summary=f"{campaign_name} — waiting for consensus (placeholder)",
        cancelled=True,
        transparent=True,
    )


def build_ics(events: list[IcsEvent]) -> bytes:
    stamp = _ics_dt(datetime.now(UTC))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//whendoweroll.com//EN",
        "CALSCALE:GREGORIAN",
        f"X-PUBLISHED-TTL:{_REFRESH_INTERVAL}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{_REFRESH_INTERVAL}",
    ]
    for event in events:
        vevent = [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_dt(event.start)}",
            f"DTEND:{_ics_dt(event.end)}",
            f"SUMMARY:{_ics_escape(event.summary)}",
        ]
        if event.transparent:
            vevent.append("TRANSP:TRANSPARENT")
        if event.cancelled:
            vevent.append("STATUS:CANCELLED")
        vevent.append("END:VEVENT")
        lines.extend(vevent)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")

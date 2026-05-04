"""Minimal RFC 5545 iCalendar generation (UTF-8, UTC DTSTART/DTEND)."""

from __future__ import annotations

from datetime import datetime, timezone


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _ics_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(events: list[tuple[str, datetime, datetime, str]]) -> bytes:
    """Each tuple is ``(uid, dtstart, dtend, summary)``."""
    stamp = _ics_dt(datetime.now(timezone.utc))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//dnd-scheduler//EN",
        "CALSCALE:GREGORIAN",
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

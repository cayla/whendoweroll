"""Slot occurrence expansion.

A "slot" is a logical session option (Friday 18:00, the May 30 one-shot, etc.).
An "occurrence" is one concrete time window on the wall calendar that the
group could meet at. Recurring slots fan out into many occurrences across the
horizon; ad-hoc slots become a single occurrence in their own right.

DST policy: we anchor recurring slots to local *wall time* in the campaign's
IANA timezone, so a Sunday 19:00 slot stays at 19:00 local on both sides of a
DST transition (its UTC offset shifts by an hour). For the rare slot that
lands inside a "spring forward" gap (e.g. America/New_York 02:30 on the
second Sunday of March doesn't exist), zoneinfo silently chooses the
post-transition offset (``fold=0``); we accept that here because the
alternative is dropping the session, and the visible effect is rare.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as time_t
from zoneinfo import ZoneInfo

from app.models import Slot, SlotKind


@dataclass(frozen=True)
class Occurrence:
    """A single concrete window. ``slot_id`` ties back to availability rows."""

    slot_id: int
    label: str
    starts_at_utc: datetime
    ends_at_utc: datetime

    @property
    def is_in_future(self) -> bool:
        return self.starts_at_utc > datetime.now(UTC)


_HHMM_FMT = "%H:%M"


def _parse_hhmm(value: str) -> time_t:
    return datetime.strptime(value, _HHMM_FMT).time()


def _localize(local_dt: datetime, tz: ZoneInfo) -> datetime:
    """Attach the timezone and return the equivalent UTC instant.

    Uses Python's default ``fold=0``: for the "fall back" repeat hour this
    picks the earlier (pre-transition) offset; for the "spring forward" gap
    where the local time doesn't exist, zoneinfo returns the post-transition
    offset. See module docstring for the rationale.
    """
    return local_dt.replace(tzinfo=tz).astimezone(UTC)


def expand_recurring(
    slot: Slot,
    *,
    tz: ZoneInfo,
    start: datetime,
    end: datetime,
) -> Iterable[Occurrence]:
    if slot.kind is not SlotKind.recurring:
        return
    if slot.weekday is None or slot.start_local is None or slot.duration_hours is None:
        return
    if slot.duration_hours <= 0:
        return

    start_local_t = _parse_hhmm(slot.start_local)
    duration = timedelta(hours=float(slot.duration_hours))

    # Walk day-by-day in the campaign's local timezone so weekday math
    # respects DST shifts cleanly.
    cursor_local = start.astimezone(tz).date()
    scan_until = end.astimezone(tz).date() + timedelta(days=1)
    while cursor_local < scan_until:
        if cursor_local.weekday() == slot.weekday:
            starts_local = datetime.combine(cursor_local, start_local_t)
            ends_local_naive = starts_local + duration
            occ_start = _localize(starts_local, tz)
            occ_end = _localize(ends_local_naive, tz)
            if occ_end > start and occ_start < end:
                yield Occurrence(
                    slot_id=slot.id,  # type: ignore[arg-type]
                    label=slot.label or _default_label(slot, starts_local),
                    starts_at_utc=occ_start,
                    ends_at_utc=occ_end,
                )
        cursor_local = cursor_local + timedelta(days=1)


def _default_label(slot: Slot, starts_local: datetime) -> str:
    weekday_name = starts_local.strftime("%a")
    dh = float(slot.duration_hours or 0)
    end_naive = starts_local + timedelta(hours=dh)
    end_str = end_naive.strftime("%H:%M")
    return f"{weekday_name} {slot.start_local}-{end_str}"


def expand_adhoc(slot: Slot) -> Iterable[Occurrence]:
    if slot.kind is not SlotKind.adhoc:
        return
    if slot.starts_at_utc is None or slot.ends_at_utc is None:
        return
    yield Occurrence(
        slot_id=slot.id,  # type: ignore[arg-type]
        label=slot.label or "One-off session",
        starts_at_utc=_ensure_utc(slot.starts_at_utc),
        ends_at_utc=_ensure_utc(slot.ends_at_utc),
    )


def _ensure_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on read; we know we wrote UTC so re-attach it.
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def upcoming_occurrences_for_slot(
    slot: Slot,
    *,
    tz: ZoneInfo,
    horizon_weeks: int,
    now: datetime | None = None,
) -> list[Occurrence]:
    """Concrete future windows for a single slot within the campaign horizon."""
    now = now or datetime.now(UTC)
    end = now + timedelta(weeks=horizon_weeks)
    if slot.kind is SlotKind.recurring:
        return list(expand_recurring(slot, tz=tz, start=now, end=end))
    if slot.kind is SlotKind.adhoc:
        out: list[Occurrence] = []
        for occ in expand_adhoc(slot):
            if occ.ends_at_utc > now and occ.starts_at_utc < end:
                out.append(occ)
        return out
    return []


def expand_all(
    slots: Iterable[Slot],
    *,
    tz: ZoneInfo,
    horizon_weeks: int,
    now: datetime | None = None,
) -> list[Occurrence]:
    now = now or datetime.now(UTC)
    end = now + timedelta(weeks=horizon_weeks)
    out: list[Occurrence] = []
    for slot in slots:
        if slot.kind is SlotKind.recurring:
            out.extend(expand_recurring(slot, tz=tz, start=now, end=end))
        else:
            for occ in expand_adhoc(slot):
                if occ.ends_at_utc > now and occ.starts_at_utc < end:
                    out.append(occ)
    out.sort(key=lambda o: o.starts_at_utc)
    return out

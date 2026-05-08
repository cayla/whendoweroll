"""Format UTC instants for viewer-facing templates (player / public pages)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import Slot, SlotKind
from app.services.slots import upcoming_occurrences_for_slot

_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _tz_suffix(dt: datetime, tz_name: str) -> str:
    z = dt.strftime("%Z")
    if z:
        return z
    name = dt.tzname()
    if name:
        return name
    return tz_name


def format_local_window(starts_utc: datetime, ends_utc: datetime, tz_name: str) -> str:
    """Wall-clock window in ``tz_name``, e.g. ``Thu 11:00 AM–2:00 PM SST``."""
    z = ZoneInfo(tz_name)
    a = ensure_utc(starts_utc).astimezone(z)
    b = ensure_utc(ends_utc).astimezone(z)

    def fmt_t(dt: datetime) -> str:
        return dt.strftime("%-I:%M %p")

    day_a = a.strftime("%a")
    day_b = b.strftime("%a")
    za, zb = _tz_suffix(a, tz_name), _tz_suffix(b, tz_name)
    if a.date() == b.date():
        if za == zb:
            return f"{day_a} {fmt_t(a)}–{fmt_t(b)} {za}"
        return f"{day_a} {fmt_t(a)} {za}–{fmt_t(b)} {zb}"
    return f"{day_a} {fmt_t(a)} {za} – {day_b} {fmt_t(b)} {zb}"


def recurring_slot_primary_label(slot: Slot, campaign, display_tz: str) -> str:
    """Primary line for a recurring row: next occurrence in the viewer's zone."""
    if slot.kind is not SlotKind.recurring or slot.weekday is None:
        return ""
    z = ZoneInfo(campaign.timezone)
    horizon = min(campaign.horizon_weeks, 26)
    occs = upcoming_occurrences_for_slot(slot, tz=z, horizon_weeks=horizon)
    if occs:
        return format_local_window(occs[0].starts_at_utc, occs[0].ends_at_utc, display_tz)
    wn = _WEEKDAY_SHORT[slot.weekday]
    dh = slot.duration_hours if slot.duration_hours is not None else 0
    return f"{wn} {slot.start_local}, {dh} h ({campaign.timezone})"

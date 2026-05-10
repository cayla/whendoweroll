"""Format UTC instants for viewer-facing templates (player / public pages)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import Campaign, PublicRecurrenceMode, Slot, SlotKind
from app.services.slots import upcoming_occurrences_for_slot

_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_local_window(starts_utc: datetime, ends_utc: datetime, tz_name: str) -> str:
    """Wall-clock window in ``tz_name``, e.g. ``Thu 11:00 AM–2:00 PM``.

    The displayed zone is shown once per page (in the top-right TZ pill /
    abbreviation chip) so we omit a per-row tz suffix to cut visual noise.
    """
    z = ZoneInfo(tz_name)
    a = ensure_utc(starts_utc).astimezone(z)
    b = ensure_utc(ends_utc).astimezone(z)

    def fmt_t(dt: datetime) -> str:
        return dt.strftime("%-I:%M %p")

    day_a = a.strftime("%a")
    day_b = b.strftime("%a")
    if a.date() == b.date():
        return f"{day_a} {fmt_t(a)}–{fmt_t(b)}"
    return f"{day_a} {fmt_t(a)} – {day_b} {fmt_t(b)}"


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


def player_campaign_tempo_caption(campaign: Campaign) -> str:
    """Short label for how recurring sessions are thinned on the public page and .ics."""
    raw = campaign.public_recurrence_mode
    try:
        mode = raw if isinstance(raw, PublicRecurrenceMode) else PublicRecurrenceMode(str(raw))
    except ValueError:
        mode = PublicRecurrenceMode.weekly
    if mode is PublicRecurrenceMode.weekly:
        return "Tempo: weekly — the public page and consensus calendar list every date below."
    if mode is PublicRecurrenceMode.two_weeks:
        return (
            "Tempo: every two weeks — the public page and calendar walk forward from the "
            "earliest qualifying session, then each next pick is the best match near fourteen days "
            "after the last one shown. You still see every date here."
        )
    if mode is PublicRecurrenceMode.once_per_month:
        return (
            "Tempo: about once a month — same walk, but each next pick is chosen near the same "
            "calendar date one month after the last one shown. You still see every date here."
        )
    return ""


def public_campaign_tempo_caption(campaign: Campaign) -> str:
    """One-line tempo for the anonymous public campaign page."""
    raw = campaign.public_recurrence_mode
    try:
        mode = raw if isinstance(raw, PublicRecurrenceMode) else PublicRecurrenceMode(str(raw))
    except ValueError:
        mode = PublicRecurrenceMode.weekly
    if mode is PublicRecurrenceMode.weekly:
        return (
            "Tempo: weekly — this page and the consensus calendar list every "
            "qualifying session. Player links list every occurrence."
        )
    if mode is PublicRecurrenceMode.two_weeks:
        return (
            "Tempo: every two weeks — earliest qualifying session first, then each next "
            "listing near fourteen days after the previous one here and on the calendar. "
            "Player links list every occurrence."
        )
    if mode is PublicRecurrenceMode.once_per_month:
        return (
            "Tempo: about once a month — earliest qualifying session first, then each next listing "
            "near the same calendar date one month out from the last one here and on the calendar. "
            "Player links list every occurrence."
        )
    return ""

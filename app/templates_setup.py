"""Single Jinja2 environment shared by all route modules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi.templating import Jinja2Templates

from app.display_time import (
    format_datetime_clock_12h,
    format_hhmm_12h,
    format_local_window,
    player_campaign_tempo_caption,
    public_campaign_tempo_caption,
    recurring_slot_primary_label,
)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _format_local(value: datetime, tz_name: str) -> str:
    """Render a UTC instant in ``tz_name`` without a timezone suffix.

    The viewer's zone is shown once at the top of the page (see the modal in
    ``fragments/viewer_tz_modal.html``); repeating ``EDT`` on every row was
    just noise.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    local = value.astimezone(ZoneInfo(tz_name))
    return local.strftime("%a %b ") + str(local.day) + local.strftime(" %Y, ") + format_datetime_clock_12h(local)


def _format_datetime_12h(value: datetime) -> str:
    return value.strftime("%Y-%m-%d ") + format_datetime_clock_12h(value)


def _tz_abbrev(tz_name: str) -> str:
    """Current short timezone abbreviation (``EDT``/``EST``/...) for ``tz_name``.

    Falls back to the IANA name if the zone has no short name (some tzdata
    entries are nameless, in which case the abbreviation chip is just hidden).
    """
    try:
        z = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError, ValueError:
        return ""
    return datetime.now(tz=z).strftime("%Z") or ""


def _pretty_tz(tz_name: str) -> str:
    """Display-only IANA name with underscores swapped for spaces.

    Forms still post the raw IANA name (e.g. ``America/New_York``); this is
    purely for human-readable rendering in chrome and labels.
    """
    return tz_name.replace("_", " ") if tz_name else tz_name


templates.env.filters["local_time"] = _format_local
templates.env.filters["local_window"] = format_local_window
templates.env.filters["datetime_12h"] = _format_datetime_12h
templates.env.filters["hhmm_12h"] = format_hhmm_12h
templates.env.filters["recurring_slot_viewer"] = recurring_slot_primary_label
templates.env.filters["player_tempo"] = player_campaign_tempo_caption
templates.env.filters["public_tempo"] = public_campaign_tempo_caption
templates.env.filters["tz_abbrev"] = _tz_abbrev
templates.env.filters["pretty_tz"] = _pretty_tz


# Cached for the timezone <select> on the create form.
COMMON_TIMEZONES: list[str] = sorted(
    [tz for tz in available_timezones() if "/" in tz and not tz.startswith(("Etc/", "SystemV/", "US/", "Canada/"))]
)


def timezone_select_options() -> list[tuple[str, str]]:
    """(IANA value, display label) pairs for HTML ``<select>`` options.

    Labels use ``_pretty_tz`` so underscores become spaces while ``value``
    stays the real zone name for form posts and ``ZoneInfo``.
    """
    return [(tz, _pretty_tz(tz)) for tz in COMMON_TIMEZONES]

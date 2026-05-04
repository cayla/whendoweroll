"""Single Jinja2 environment shared by all route modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

from fastapi.templating import Jinja2Templates

from app.display_time import format_local_window, recurring_slot_primary_label

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _format_local(value: datetime, tz_name: str) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(ZoneInfo(tz_name))
    return local.strftime("%a %b ") + str(local.day) + local.strftime(" %Y, %-I:%M %p %Z")


templates.env.filters["local_time"] = _format_local
templates.env.filters["local_window"] = format_local_window
templates.env.filters["recurring_slot_viewer"] = recurring_slot_primary_label


# Cached for the timezone <select> on the create form.
COMMON_TIMEZONES: list[str] = sorted(
    [
        tz
        for tz in available_timezones()
        if "/" in tz and not tz.startswith(("Etc/", "SystemV/", "US/", "Canada/"))
    ]
)

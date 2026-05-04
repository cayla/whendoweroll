"""Browser-friendly display timezone via a single cookie.

Recurring slot *definitions* stay in the campaign's IANA timezone; this only
changes how we *render* instants for players and public viewers.
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import Response
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COOKIE_NAME = "dnd_viewer_tz"
COOKIE_MAX_AGE_SECONDS = 400 * 24 * 3600
_MAX_TZ_LEN = 120


def effective_display_timezone(request: Request, campaign_timezone: str) -> str:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return campaign_timezone
    candidate = unquote(raw).strip()
    if not candidate or len(candidate) > _MAX_TZ_LEN:
        return campaign_timezone
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return campaign_timezone
    return candidate


def set_viewer_timezone_on_response(response: Response, timezone: str) -> None:
    """Validate then Set-Cookie (path-wide so player + public share one preference)."""
    timezone = timezone.strip()
    if not timezone or len(timezone) > _MAX_TZ_LEN:
        raise ValueError("bad timezone")
    ZoneInfo(timezone)  # validate
    response.set_cookie(
        key=COOKIE_NAME,
        value=timezone,
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
        samesite="lax",
        httponly=False,
    )

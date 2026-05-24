"""Browser-friendly display timezone via a single cookie.

Recurring slot *definitions* stay in the campaign's IANA timezone; this only
changes how we *render* instants for players and public viewers.
"""

from __future__ import annotations

from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

COOKIE_NAME = "whendoweroll_viewer_tz"
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


def redirect_with_viewer_timezone(url: str, timezone: str) -> RedirectResponse:
    """Validate ``timezone``, set the viewer cookie, and return a 303 redirect."""
    resp = RedirectResponse(url=url, status_code=303)
    set_viewer_timezone_on_response(resp, timezone)
    return resp


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

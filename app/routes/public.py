"""Public read-only campaign home."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_campaign_or_404
from app.models import Player, Slot
from app.services.availability import load_availability_map
from app.services.consensus import count_yes_for_occurrence, find_next_meet, player_lookup
from app.services.opt_outs import load_opt_out_set
from app.services.slots import expand_all
from app.templates_setup import COMMON_TIMEZONES, templates
from app.view_timezone import effective_display_timezone, set_viewer_timezone_on_response

router = APIRouter()


@router.get("/c/{public_id}", response_class=HTMLResponse)
def public_home(
    public_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = get_campaign_or_404(session, public_id)
    players = session.exec(
        select(Player).where(Player.campaign_id == campaign.id).order_by(Player.sort_order)
    ).all()
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()

    display_tz = effective_display_timezone(request, campaign.timezone)

    tz = ZoneInfo(campaign.timezone)
    occurrences = expand_all(slots, tz=tz, horizon_weeks=campaign.horizon_weeks)
    availability = load_availability_map(session, players)
    player_ids = [p.id for p in players if p.id is not None]
    opt_outs = load_opt_out_set(session, player_ids)

    everyone = find_next_meet(
        occurrences, players, availability, max_missing=0, opt_outs=opt_outs
    )
    almost = find_next_meet(
        occurrences, players, availability, max_missing=1, opt_outs=opt_outs
    )

    occurrence_rows = [
        {
            "occ": occ,
            "yes_count": count_yes_for_occurrence(occ, players, availability, opt_outs),
        }
        for occ in occurrences[:25]
    ]

    player_lookup_map = player_lookup(players)
    has_dm = any(bool(p.is_dm) for p in players)

    return templates.TemplateResponse(
        request,
        "public.html",
        {
            "campaign": campaign,
            "players": players,
            "slots": slots,
            "display_tz": display_tz,
            "everyone": everyone,
            "almost": almost,
            "occurrence_rows": occurrence_rows,
            "player_lookup": player_lookup_map,
            "total_players": len(players),
            "has_dm": has_dm,
            "timezones": COMMON_TIMEZONES,
        },
    )


@router.post("/c/{public_id}/display-timezone", response_class=HTMLResponse)
def set_public_display_timezone(
    public_id: str,
    timezone: str = Form(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    get_campaign_or_404(session, public_id)
    try:
        resp = RedirectResponse(url=f"/c/{public_id}", status_code=303)
        set_viewer_timezone_on_response(resp, timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(status_code=400, detail="Unknown timezone") from None
    return resp

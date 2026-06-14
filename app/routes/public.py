"""Public read-only campaign home."""

from __future__ import annotations

from zoneinfo import ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session

from app.db import get_session
from app.deps import get_campaign_or_404
from app.services.availability import eligible_not_never_count_for_slot
from app.services.consensus import (
    count_availability_buckets_for_occurrence,
    find_next_meets,
    player_lookup,
)
from app.services.consensus_ics import PUBLIC_LOCKED_SESSION_LIMIT, build_consensus_ics_events
from app.services.ical import build_ics
from app.services.public_consensus_data import load_public_consensus_data
from app.templates_setup import COMMON_TIMEZONES, templates
from app.view_timezone import effective_display_timezone, redirect_with_viewer_timezone

router = APIRouter()


@router.get("/c/{public_id}", response_class=HTMLResponse)
def public_home(
    public_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = get_campaign_or_404(session, public_id)
    data = load_public_consensus_data(session, campaign)

    display_tz = effective_display_timezone(request, campaign.timezone)

    upcoming_meets = find_next_meets(
        data.occurrences_public,
        data.players,
        data.availability,
        policy=campaign.consensus_policy,
        opt_outs=data.opt_outs,
        limit=PUBLIC_LOCKED_SESSION_LIMIT,
        proximity_occurrences=data.occurrences_full if campaign.prefer_full_party else None,
    )

    horizon_preview = data.occurrences_full[:25]
    occurrence_rows: list[dict] = []
    for occ in horizon_preview:
        yes_denom = eligible_not_never_count_for_slot(data.availability, data.players, occ.slot_id)
        if yes_denom == 0:
            continue
        can_make, cant_make, no_answer = count_availability_buckets_for_occurrence(
            occ, data.players, data.availability, data.opt_outs
        )
        occurrence_rows.append(
            {
                "occ": occ,
                "can_make": can_make,
                "cant_make": cant_make,
                "no_answer": no_answer,
            }
        )
    occurrence_rows_were_filtered = bool(horizon_preview) and not occurrence_rows

    player_lookup_map = player_lookup(data.players)
    mandatory_attendees = [p for p in data.players if p.is_mandatory]
    has_mandatory = bool(mandatory_attendees)

    return templates.TemplateResponse(
        request,
        "public.html",
        {
            "campaign": campaign,
            "players": data.players,
            "slots": data.slots,
            "display_tz": display_tz,
            "upcoming_meets": upcoming_meets,
            "occurrence_rows": occurrence_rows,
            "occurrence_rows_were_filtered": occurrence_rows_were_filtered,
            "player_lookup": player_lookup_map,
            "total_players": len(data.players),
            "has_mandatory": has_mandatory,
            "mandatory_attendees": mandatory_attendees,
            "timezones": COMMON_TIMEZONES,
        },
    )


@router.post("/c/{public_id}/display-timezone", response_class=RedirectResponse)
def set_public_display_timezone(
    public_id: str,
    timezone: str = Form(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    get_campaign_or_404(session, public_id)
    try:
        return redirect_with_viewer_timezone(f"/c/{public_id}", timezone)
    except ValueError, ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail="Unknown timezone") from None


@router.get("/c/{public_id}/calendar-consensus.ics")
def calendar_consensus_ics(
    public_id: str,
    session: Session = Depends(get_session),
) -> Response:
    """Single per-campaign feed: full-consensus windows plus near-consensus
    (one missing) windows whose summaries are prefixed with ``[missing: …]``.

    Public-tier (gated only by the unguessable ``public_id``) so the same URL
    can be shared with the whole roster — there is no per-player feed.
    """
    campaign = get_campaign_or_404(session, public_id)
    data = load_public_consensus_data(session, campaign)
    body = build_ics(build_consensus_ics_events(campaign, data))
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="calendar-consensus.ics"'},
    )

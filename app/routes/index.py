"""Landing page + campaign creation."""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfoNotFoundError, ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.models import Campaign, Player
from app.security import hash_token, new_token
from app.templates_setup import COMMON_TIMEZONES, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"timezones": COMMON_TIMEZONES, "default_tz": "America/New_York"},
    )


@router.post("/", response_class=HTMLResponse)
def create_campaign(
    request: Request,
    name: str = Form(...),
    timezone: str = Form(...),
    player_names: str = Form(""),
    horizon_weeks: int = Form(12),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Unknown timezone") from exc
    horizon_weeks = max(1, min(horizon_weeks, 52))

    public_id = uuid.uuid4().hex
    admin_secret = new_token()

    campaign = Campaign(
        public_id=public_id,
        name=name,
        timezone=timezone,
        admin_secret_hash=hash_token(admin_secret),
        horizon_weeks=horizon_weeks,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    raw_lines = [line.strip() for line in player_names.splitlines()]
    raw_names = [line for line in raw_lines if line]

    created_players: list[tuple[Player, str]] = []
    for sort_order, display_name in enumerate(raw_names):
        token = new_token()
        player = Player(
            campaign_id=campaign.id,  # type: ignore[arg-type]
            display_name=display_name,
            token_hash=hash_token(token),
            sort_order=sort_order,
        )
        session.add(player)
        session.commit()
        session.refresh(player)
        created_players.append((player, token))

    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "created.html",
        {
            "campaign": campaign,
            "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{admin_secret}",
            "public_url": f"{base_url}/c/{campaign.public_id}",
            "players_with_urls": [
                (p, f"{base_url}/c/{campaign.public_id}/p/{tok}") for p, tok in created_players
            ],
        },
    )

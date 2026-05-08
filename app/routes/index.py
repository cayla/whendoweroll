"""Landing page + campaign creation."""

from __future__ import annotations

import json
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.models import Campaign, Player
from app.security import hash_token, new_token
from app.services.campaign_import import CampaignImportError, import_campaign
from app.settings import new_campaigns_disabled
from app.templates_setup import templates, timezone_select_options

router = APIRouter()

_MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MiB; backups for this app are tiny.


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "timezone_options": timezone_select_options(),
            "default_tz": "America/New_York",
            "new_campaigns_disabled": new_campaigns_disabled(),
        },
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
    if new_campaigns_disabled():
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "timezone_options": timezone_select_options(),
                "default_tz": "America/New_York",
                "new_campaigns_disabled": True,
            },
            status_code=403,
        )
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
    session.flush()

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
        created_players.append((player, token))

    session.flush()
    session.commit()
    session.refresh(campaign)

    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "created.html",
        {
            "campaign": campaign,
            "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{admin_secret}",
            "public_url": f"{base_url}/c/{campaign.public_id}",
            "players_with_urls": [(p, f"{base_url}/c/{campaign.public_id}/p/{tok}") for p, tok in created_players],
        },
    )


@router.post("/import", response_class=HTMLResponse)
async def import_campaign_route(
    request: Request,
    backup: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Restore a campaign from a previously-downloaded ``export.json`` file.

    Importing creates a brand-new campaign (fresh admin link, fresh per-player
    links) populated with the file's roster, slots, availability, and
    per-occurrence opt-outs. The original public id and capability secrets
    are intentionally not reused — the export never carried them, and we
    want every link in the system to remain unguessable.
    """
    if new_campaigns_disabled():
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "timezone_options": timezone_select_options(),
                "default_tz": "America/New_York",
                "new_campaigns_disabled": True,
            },
            status_code=403,
        )

    raw = await backup.read(_MAX_IMPORT_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Backup file is too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Backup must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Backup is not valid JSON: {exc.msg}") from exc

    try:
        campaign, admin_secret, created_players = import_campaign(session, payload)
    except CampaignImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "created.html",
        {
            "campaign": campaign,
            "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{admin_secret}",
            "public_url": f"{base_url}/c/{campaign.public_id}",
            "players_with_urls": [(p, f"{base_url}/c/{campaign.public_id}/p/{tok}") for p, tok in created_players],
        },
    )

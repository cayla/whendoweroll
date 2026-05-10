"""Landing page + campaign creation."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

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


def _safe_filename_stub(name: str) -> str:
    """Short ASCII-ish slug for downloadable filenames."""
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s.strip()).lower()
    return (s[:40] or "campaign").strip("-")


def _created_page_context(
    campaign: Campaign,
    admin_url: str,
    public_url: str,
    players_with_urls: list[tuple[Player, str]],
    campaign_origin: Literal["created", "imported"],
) -> dict[str, Any]:
    """Shared template context for the post-create / post-import success page."""
    manifest_rows: list[dict[str, str]] = [
        {
            "link_type": "Admin",
            "link_description": "Full access: Keep this link secret.",
            "link": admin_url,
        },
        {
            "link_type": "Public",
            "link_description": "Read-only campaign page: Share with players.",
            "link": public_url,
        },
    ]
    ui_rows: list[dict[str, Any]] = [
        {
            "kind": "admin",
            "title": "Admin link",
            "badge": "Keep secret",
            "description": manifest_rows[0]["link_description"],
            "url": admin_url,
            "input_id": "created-admin-url",
        },
        {
            "kind": "public",
            "title": "Public campaign page",
            "badge": "",
            "description": manifest_rows[1]["link_description"],
            "url": public_url,
            "input_id": "created-public-url",
        },
    ]
    for player, p_url in players_with_urls:
        desc = f"Private editing link for {player.display_name}."
        manifest_rows.append(
            {
                "link_type": "Player",
                "link_description": desc,
                "link": p_url,
            }
        )
        ui_rows.append(
            {
                "kind": "player",
                "title": player.display_name,
                "badge": "Private",
                "description": desc,
                "url": p_url,
                "input_id": f"created-player-url-{player.id}",
            }
        )

    manifest = {
        "campaign_name": campaign.name,
        "public_id": campaign.public_id,
        "filename_stub": _safe_filename_stub(campaign.name),
        "rows": manifest_rows,
    }
    return {
        "campaign": campaign,
        "campaign_origin": campaign_origin,
        "ui_rows": ui_rows,
        "links_manifest_json": json.dumps(manifest),
    }


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
    admin_url = f"{base_url}/c/{campaign.public_id}/admin/{admin_secret}"
    public_url = f"{base_url}/c/{campaign.public_id}"
    players_with_urls = [(p, f"{base_url}/c/{campaign.public_id}/p/{tok}") for p, tok in created_players]
    return templates.TemplateResponse(
        request,
        "created.html",
        _created_page_context(campaign, admin_url, public_url, players_with_urls, "created"),
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
    are intentionally not reused. The export never carried them, and we
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
    admin_url = f"{base_url}/c/{campaign.public_id}/admin/{admin_secret}"
    public_url = f"{base_url}/c/{campaign.public_id}"
    players_with_urls = [(p, f"{base_url}/c/{campaign.public_id}/p/{tok}") for p, tok in created_players]
    return templates.TemplateResponse(
        request,
        "created.html",
        _created_page_context(campaign, admin_url, public_url, players_with_urls, "imported"),
    )

"""Instance operator UI: list/delete campaigns, toggle new-campaign creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import union_all
from sqlmodel import Session, func, select

from app import settings as settings_module
from app.db import get_session
from app.models import Availability, Campaign, OccurrenceOptOut, Player, Slot
from app.services.campaign_delete import delete_campaign_cascade
from app.services.timeutil import ensure_utc
from app.super_admin_auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    issue_session_token,
    verify_challenge,
    verify_session_token,
)
from app.templates_setup import templates

router = APIRouter(prefix="/internal/super-admin", tags=["super-admin"])


@dataclass(frozen=True)
class SuperAdminCampaignRow:
    """One row for the super-admin campaign table (denormalised for the template)."""

    name: str
    public_id: str
    created_at: datetime
    player_count: int
    last_activity_at: datetime


def _super_admin_campaign_rows(session: Session) -> list[SuperAdminCampaignRow]:
    """Campaign list with player counts and a derived last-activity timestamp.

    There is no ``campaign.updated_at`` in the schema. ``last_activity_at`` is
    the latest UTC instant among: campaign creation, player creation, slot
    creation, availability updates, and occurrence opt-out rows. Pure admin
    settings edits that do not touch those tables will not advance this signal.
    """
    campaigns = session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all()
    if not campaigns:
        return []

    count_rows = session.exec(select(Player.campaign_id, func.count(Player.id)).group_by(Player.campaign_id)).all()
    counts: dict[int, int] = {int(cid): int(n) for cid, n in count_rows if cid is not None}

    p = select(Player.campaign_id.label("cid"), Player.created_at.label("ts"))
    s = select(Slot.campaign_id.label("cid"), Slot.created_at.label("ts"))
    a = (
        select(Player.campaign_id.label("cid"), Availability.updated_at.label("ts"))
        .select_from(Availability)
        .join(Player, Availability.player_id == Player.id)
    )
    o = (
        select(Player.campaign_id.label("cid"), OccurrenceOptOut.created_at.label("ts"))
        .select_from(OccurrenceOptOut)
        .join(Player, OccurrenceOptOut.player_id == Player.id)
    )
    combined = union_all(p, s, a, o).subquery()
    agg = select(combined.c.cid, func.max(combined.c.ts).label("last_ts")).group_by(combined.c.cid)
    activity: dict[int, datetime] = {}
    for row in session.exec(agg):
        activity[int(row.cid)] = row.last_ts

    rows: list[SuperAdminCampaignRow] = []
    for c in campaigns:
        if c.id is None:
            continue
        pc = counts.get(c.id, 0)
        sub = activity.get(c.id)
        created = ensure_utc(c.created_at)
        last = created if sub is None else max(created, ensure_utc(sub))
        rows.append(
            SuperAdminCampaignRow(
                name=c.name,
                public_id=c.public_id,
                created_at=c.created_at,
                player_count=pc,
                last_activity_at=last,
            )
        )
    return rows


def _cookie_flags(request: Request) -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": request.url.scheme == "https",
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }


def _redirect_unless_session(request: Request) -> RedirectResponse | None:
    if not verify_session_token(request.cookies.get(SESSION_COOKIE_NAME)):
        return RedirectResponse(url="/internal/super-admin", status_code=303)
    return None


@router.get("", response_class=HTMLResponse)
def super_admin_page(
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if not verify_session_token(request.cookies.get(SESSION_COOKIE_NAME)):
        return templates.TemplateResponse(request, "super_admin_login.html", {"error": None})
    campaigns = _super_admin_campaign_rows(session)
    return templates.TemplateResponse(
        request,
        "super_admin.html",
        {
            "campaigns": campaigns,
            "new_campaigns_disabled": settings_module.new_campaigns_disabled(),
            "new_campaigns_override": settings_module.new_campaigns_override(),
        },
    )


@router.post("/login", response_class=HTMLResponse, response_model=None)
def super_admin_login(
    request: Request,
    password: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    if verify_session_token(request.cookies.get(SESSION_COOKIE_NAME)):
        return RedirectResponse(url="/internal/super-admin", status_code=303)
    if not verify_challenge(password):
        return templates.TemplateResponse(
            request,
            "super_admin_login.html",
            {"error": "Incorrect password."},
            status_code=401,
        )
    out = RedirectResponse(url="/internal/super-admin", status_code=303)
    out.set_cookie(SESSION_COOKIE_NAME, issue_session_token(), **_cookie_flags(request))
    return out


@router.post("/logout", response_class=RedirectResponse)
def super_admin_logout() -> RedirectResponse:
    out = RedirectResponse(url="/internal/super-admin", status_code=303)
    out.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return out


@router.post("/campaigns/{public_id}/delete", response_class=RedirectResponse)
def super_admin_delete_campaign(
    public_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    guard = _redirect_unless_session(request)
    if guard is not None:
        return guard
    campaign = session.exec(select(Campaign).where(Campaign.public_id == public_id)).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    delete_campaign_cascade(session, campaign)
    return RedirectResponse(url="/internal/super-admin", status_code=303)


@router.post("/new-campaigns-override", response_class=RedirectResponse)
def super_admin_set_new_campaigns_override(
    request: Request,
    mode: str = Form(...),
) -> RedirectResponse:
    guard = _redirect_unless_session(request)
    if guard is not None:
        return guard
    raw = (mode or "").strip().lower()
    if raw == "env":
        settings_module.set_new_campaigns_override(None)
    elif raw in ("allow", "enable"):
        settings_module.set_new_campaigns_override(False)
    elif raw in ("block", "disable"):
        settings_module.set_new_campaigns_override(True)
    else:
        raise HTTPException(status_code=400, detail="Invalid mode")
    return RedirectResponse(url="/internal/super-admin", status_code=303)

"""Instance operator UI: list/delete campaigns, toggle new-campaign creation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app import settings as settings_module
from app.db import get_session
from app.models import Campaign
from app.services.campaign_delete import delete_campaign_cascade
from app.super_admin_auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    issue_session_token,
    verify_challenge,
    verify_session_token,
)
from app.templates_setup import templates

router = APIRouter(prefix="/internal/super-admin", tags=["super-admin"])


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
    campaigns = session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all()
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

"""Admin dashboard: campaign settings, player roster, slot catalog."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_admin
from app.models import Availability, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.security import hash_token, new_token
from app.services.campaign_delete import delete_campaign_cascade
from app.services.campaign_export import build_export_payload, campaign_export_download_filename
from app.services.opt_outs import delete_for_player, delete_for_slot
from app.templates_setup import COMMON_TIMEZONES, templates

router = APIRouter(prefix="/c/{public_id}/admin/{secret}")

_ADMIN_WEEKDAY_CHOICES: list[tuple[int, str]] = [
    (0, "Mon"),
    (1, "Tue"),
    (2, "Wed"),
    (3, "Thu"),
    (4, "Fri"),
    (5, "Sat"),
    (6, "Sun"),
]


def _players_ordered_for_admin(session: Session, campaign_id: int) -> list[Player]:
    """Alphabetical by display name (case-insensitive) for admin roster and mandatory UI."""
    return session.exec(
        select(Player).where(Player.campaign_id == campaign_id).order_by(func.lower(Player.display_name))
    ).all()


_MIN_SESSION_HOURS = 1.0 / 60.0
_MAX_SESSION_HOURS = 48.0

# (value, short label, hint) for the Settings card dropdown. Order is the
# spectrum from strictest to most permissive so organisers can scan it
# top-to-bottom.
_PUBLIC_RECURRENCE_MODE_CHOICES: tuple[tuple[PublicRecurrenceMode, str, str], ...] = (
    (
        PublicRecurrenceMode.weekly,
        "Weekly",
        "Public next-game cards and consensus calendar list every scheduled recurring session.",
    ),
    (
        PublicRecurrenceMode.two_weeks,
        "Every two weeks (~14 days)",
        (
            "Public page and calendar: earliest qualifying session, then each next pick near "
            "fourteen days after the previous kept listing (closest match in a bracket). "
            "Player pages still list every date."
        ),
    ),
    (
        PublicRecurrenceMode.once_per_month,
        "About once a month",
        (
            "Public page and calendar: earliest qualifying session, then each next pick near the "
            "same calendar date one month after the previous kept listing. Player pages still list every date."
        ),
    ),
)

_CONSENSUS_POLICY_CHOICES: tuple[tuple[ConsensusPolicy, str, str], ...] = (
    (
        ConsensusPolicy.strict,
        "Strict — everyone every time",
        "Only schedule a session when every player is available.",
    ),
    (
        ConsensusPolicy.no_two_nears,
        "Allow one missing — never two in a row",
        "Schedule with one holdout when needed, but don't run two short-handed sessions back-to-back.",
    ),
    (
        ConsensusPolicy.no_repeat_holdout,
        "Allow one missing — but rotate who",
        "Schedule with one holdout, but don't let the same player be the holdout two sessions in a row.",
    ),
    (
        ConsensusPolicy.allow_one,
        "Allow one missing — always",
        "Schedule whenever at most one player is missing, no further constraint.",
    ),
)


def _parse_session_duration_hours(raw: str | None) -> float:
    if raw is None or not str(raw).strip():
        raise HTTPException(status_code=400, detail="Session duration (hours) is required")
    try:
        h = float(str(raw).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid duration") from exc
    if h < _MIN_SESSION_HOURS or h > _MAX_SESSION_HOURS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Duration must be between {_MIN_SESSION_HOURS * 60:.0f} minutes and {_MAX_SESSION_HOURS:.0f} hours"
            ),
        )
    return h


def _parse_public_recurrence_mode(raw: str | None) -> PublicRecurrenceMode:
    if raw is None or not str(raw).strip():
        return PublicRecurrenceMode.weekly
    s = str(raw).strip()
    if s == "twice_per_month":
        s = "two_weeks"
    try:
        return PublicRecurrenceMode(s)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown public recurrence mode") from exc


def _redirect_to_admin(public_id: str, secret: str) -> RedirectResponse:
    return RedirectResponse(url=f"/c/{public_id}/admin/{secret}", status_code=303)


def _admin_path(public_id: str, secret: str) -> str:
    return f"/c/{public_id}/admin/{secret}"


@router.get("", response_class=HTMLResponse)
def admin_home(
    public_id: str,
    secret: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = require_admin(session, public_id, secret)
    players = _players_ordered_for_admin(session, campaign.id)
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "campaign": campaign,
            "players": players,
            "slots": slots,
            "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{secret}",
            "admin_path": _admin_path(campaign.public_id, secret),
            "public_url": f"{base_url}/c/{campaign.public_id}",
            "export_json_filename": campaign_export_download_filename(campaign),
            "secret": secret,
            "timezones": COMMON_TIMEZONES,
            "consensus_policy_choices": _CONSENSUS_POLICY_CHOICES,
            "weekdays": _ADMIN_WEEKDAY_CHOICES,
            "public_recurrence_mode_choices": _PUBLIC_RECURRENCE_MODE_CHOICES,
        },
    )


@router.post("/settings", response_class=RedirectResponse)
def update_settings(
    public_id: str,
    secret: str,
    name: str = Form(...),
    timezone: str = Form(...),
    horizon_weeks: int = Form(12),
    consensus_policy: str = Form(...),
    public_recurrence_mode: str | None = Form("weekly"),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    campaign = require_admin(session, public_id, secret)
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Unknown timezone") from exc
    try:
        policy = ConsensusPolicy(consensus_policy.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown consensus policy") from exc
    mode = _parse_public_recurrence_mode(public_recurrence_mode)
    campaign.name = name
    campaign.timezone = timezone
    campaign.horizon_weeks = max(1, min(horizon_weeks, 52))
    campaign.consensus_policy = policy
    campaign.public_recurrence_mode = mode
    session.add(campaign)
    session.commit()
    return _redirect_to_admin(public_id, secret)


@router.post("/mandatory-attendees", response_class=RedirectResponse)
def set_campaign_mandatory_attendees(
    public_id: str,
    secret: str,
    mandatory_player_ids: list[str] = Form(default=[]),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Replace the set of mandatory attendees with the submitted player ids.

    The form sends ``mandatory_player_ids`` once per checked box. None selected
    means no mandatory attendees.
    """
    campaign = require_admin(session, public_id, secret)
    players = _players_ordered_for_admin(session, campaign.id)
    target_ids: set[int] = set()
    for raw in mandatory_player_ids:
        s = (raw or "").strip()
        if not s:
            continue
        try:
            target_ids.add(int(s))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid player id") from exc
    valid_ids = {p.id for p in players if p.id is not None}
    if not target_ids.issubset(valid_ids):
        raise HTTPException(status_code=400, detail="Player not in this campaign")
    for p in players:
        p.is_mandatory = p.id in target_ids
        session.add(p)
    session.commit()
    return _redirect_to_admin(public_id, secret)


@router.post("/players", response_class=HTMLResponse)
def add_player(
    public_id: str,
    secret: str,
    request: Request,
    display_name: str = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = require_admin(session, public_id, secret)
    display_name = display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Display name required")
    existing_count = session.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
    token = new_token()
    player = Player(
        campaign_id=campaign.id,  # type: ignore[arg-type]
        display_name=display_name,
        token_hash=hash_token(token),
        sort_order=len(existing_count),
    )
    session.add(player)
    session.commit()
    session.refresh(player)
    base_url = str(request.base_url).rstrip("/")
    admin_url = f"{base_url}/c/{campaign.public_id}/admin/{secret}"
    players = _players_ordered_for_admin(session, campaign.id)
    return templates.TemplateResponse(
        request,
        "fragments/new_player.html",
        {
            "player": player,
            "player_url": f"{base_url}/c/{campaign.public_id}/p/{token}",
            "secret": secret,
            "campaign": campaign,
            "players": players,
            "admin_url": admin_url,
            "admin_path": _admin_path(campaign.public_id, secret),
        },
    )


@router.post("/players/{player_id}/regenerate", response_class=HTMLResponse)
def regenerate_player_token(
    public_id: str,
    secret: str,
    player_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = require_admin(session, public_id, secret)
    player = session.get(Player, player_id)
    if player is None or player.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Player not found")
    token = new_token()
    player.token_hash = hash_token(token)
    session.add(player)
    session.commit()
    session.refresh(player)
    base_url = str(request.base_url).rstrip("/")
    admin_url = f"{base_url}/c/{campaign.public_id}/admin/{secret}"
    players = _players_ordered_for_admin(session, campaign.id)
    return templates.TemplateResponse(
        request,
        "fragments/new_player.html",
        {
            "player": player,
            "player_url": f"{base_url}/c/{campaign.public_id}/p/{token}",
            "secret": secret,
            "campaign": campaign,
            "players": players,
            "admin_url": admin_url,
            "admin_path": _admin_path(campaign.public_id, secret),
        },
    )


@router.post("/players/{player_id}/delete", response_class=HTMLResponse)
def delete_player(
    public_id: str,
    secret: str,
    player_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign = require_admin(session, public_id, secret)
    player = session.get(Player, player_id)
    if player is None or player.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Player not found")
    removed_name = player.display_name
    avails = session.exec(select(Availability).where(Availability.player_id == player.id)).all()
    for a in avails:
        session.delete(a)
    delete_for_player(session, player_id)
    session.delete(player)
    session.commit()
    players = _players_ordered_for_admin(session, campaign.id)
    base_url = str(request.base_url).rstrip("/")
    admin_url = f"{base_url}/c/{campaign.public_id}/admin/{secret}"
    return templates.TemplateResponse(
        request,
        "fragments/player_delete_response.html",
        {
            "removed_name": removed_name,
            "players": players,
            "admin_url": admin_url,
            "admin_path": _admin_path(campaign.public_id, secret),
        },
    )


@router.post("/slots", response_model=None)
def add_slot(
    public_id: str,
    secret: str,
    request: Request,
    kind: str = Form(...),
    label: str = Form(""),
    weekday: int | None = Form(None),
    start_local: str | None = Form(None),
    duration_hours: str | None = Form(None),
    adhoc_date: str | None = Form(None),
    adhoc_start_time: str | None = Form(None),
    session: Session = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    campaign = require_admin(session, public_id, secret)
    label = label.strip() or None

    if kind == SlotKind.recurring.value:
        if weekday is None or not start_local:
            raise HTTPException(status_code=400, detail="Recurring slot needs weekday and start time")
        if not (0 <= weekday <= 6):
            raise HTTPException(status_code=400, detail="Weekday out of range")
        dur_h = _parse_session_duration_hours(duration_hours)
        slot = Slot(
            campaign_id=campaign.id,  # type: ignore[arg-type]
            kind=SlotKind.recurring,
            label=label,
            weekday=weekday,
            start_local=start_local,
            duration_hours=dur_h,
        )
    elif kind == SlotKind.adhoc.value:
        if not adhoc_date or not adhoc_start_time:
            raise HTTPException(
                status_code=400,
                detail="One-off session needs date and start time",
            )
        dur_h = _parse_session_duration_hours(duration_hours)
        tz = ZoneInfo(campaign.timezone)
        try:
            d = date.fromisoformat(adhoc_date.strip())
            t_s = time.fromisoformat(adhoc_start_time.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Bad date or time") from exc
        starts_local_dt = datetime.combine(d, t_s, tzinfo=tz)
        ends_local_dt = starts_local_dt + timedelta(hours=dur_h)
        slot = Slot(
            campaign_id=campaign.id,  # type: ignore[arg-type]
            kind=SlotKind.adhoc,
            label=label,
            duration_hours=dur_h,
            starts_at_utc=starts_local_dt.astimezone(ZoneInfo("UTC")),
            ends_at_utc=ends_local_dt.astimezone(ZoneInfo("UTC")),
        )
    else:
        raise HTTPException(status_code=400, detail="Unknown slot kind")

    session.add(slot)
    session.commit()

    if request.headers.get("HX-Request"):
        base_url = str(request.base_url).rstrip("/")
        slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
        times_status_message = (
            "Recurring time added." if kind == SlotKind.recurring.value else "One-off session added."
        )
        return templates.TemplateResponse(
            request,
            "fragments/admin_slots_roster_oob.html",
            {
                "campaign": campaign,
                "slots": slots,
                "weekdays": _ADMIN_WEEKDAY_CHOICES,
                "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{secret}",
                "admin_path": _admin_path(campaign.public_id, secret),
                "times_status_message": times_status_message,
            },
        )
    return _redirect_to_admin(public_id, secret)


@router.post("/slots/{slot_id}/delete", response_model=None)
def delete_slot(
    public_id: str,
    secret: str,
    slot_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    campaign = require_admin(session, public_id, secret)
    slot = session.get(Slot, slot_id)
    if slot is None or slot.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Slot not found")
    avails = session.exec(select(Availability).where(Availability.slot_id == slot.id)).all()
    for a in avails:
        session.delete(a)
    delete_for_slot(session, slot_id)
    session.delete(slot)
    session.commit()

    if request.headers.get("HX-Request"):
        base_url = str(request.base_url).rstrip("/")
        slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
        return templates.TemplateResponse(
            request,
            "fragments/admin_slots_roster_oob.html",
            {
                "campaign": campaign,
                "slots": slots,
                "weekdays": _ADMIN_WEEKDAY_CHOICES,
                "admin_url": f"{base_url}/c/{campaign.public_id}/admin/{secret}",
                "admin_path": _admin_path(campaign.public_id, secret),
                "times_status_message": "Time removed.",
            },
        )
    return _redirect_to_admin(public_id, secret)


@router.post("/delete", response_class=RedirectResponse)
def delete_campaign(
    public_id: str,
    secret: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Remove the campaign and all related rows (players, slots, availability, opt-outs)."""
    campaign = require_admin(session, public_id, secret)
    delete_campaign_cascade(session, campaign)
    return RedirectResponse(url="/", status_code=303)


def _export_campaign_json_response(session: Session, public_id: str, secret: str) -> JSONResponse:
    campaign = require_admin(session, public_id, secret)
    fn = campaign_export_download_filename(campaign)
    return JSONResponse(
        build_export_payload(session, campaign),
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/export")
@router.get("/export.json")
def export_campaign_json(
    public_id: str,
    secret: str,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Full JSON backup. ``/export`` is the preferred URL; ``/export.json`` is kept as an alias."""
    return _export_campaign_json_response(session, public_id, secret)

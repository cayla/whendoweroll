"""Per-player availability editor."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_player
from app.models import AvailabilityStatus, Player, Slot, SlotKind
from app.services.availability import (
    load_availability_map,
    roster_can_make_occurrence,
    set_availability,
)
from app.services.occurrence_match import resolve_occurrence
from app.services.opt_outs import (
    add_opt_out,
    delete_opt_outs_for_player_slot,
    remove_opt_out,
)
from app.services.player_view import (
    has_recurring_slot,
    primary_occurrence_start_for_counts,
    roster_availability_context,
    slot_can_make_pairs,
    unified_recurring_opt_out_rows,
)
from app.templates_setup import COMMON_TIMEZONES, templates
from app.view_timezone import effective_display_timezone, set_viewer_timezone_on_response

router = APIRouter(prefix="/c/{public_id}/p/{token}")


def _empty_roster_context() -> tuple[
    list[Player],
    dict[tuple[int, int], AvailabilityStatus],
    set[tuple[int, int, datetime]],
]:
    return [], {}, set()


@router.get("", response_class=HTMLResponse)
def player_home(
    public_id: str,
    token: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign, player = require_player(session, public_id, token)
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    display_tz = effective_display_timezone(request, campaign.timezone)
    cid = campaign.id
    if cid is None:
        all_players, full_map, opt_outs = _empty_roster_context()
        can_make_pairs: dict[int, tuple[int, int]] = {}
    else:
        all_players, full_map, opt_outs = roster_availability_context(session, cid)
        can_make_pairs = slot_can_make_pairs(slots, campaign, full_map, all_players, opt_outs)
    unified_rows = unified_recurring_opt_out_rows(
        campaign,
        player,
        slots,
        session,
        avail_by_slot,
        all_players=all_players,
        full_availability=full_map,
        opt_outs=opt_outs,
    )
    return templates.TemplateResponse(
        request,
        "player.html",
        {
            "campaign": campaign,
            "player": player,
            "slots": slots,
            "availability": avail_by_slot,
            "token": token,
            "unified_rows": unified_rows,
            "has_recurring": has_recurring_slot(slots),
            "display_tz": display_tz,
            "timezones": COMMON_TIMEZONES,
            "slot_can_make_pairs": can_make_pairs,
        },
    )


@router.post("/viewer-timezone", response_class=RedirectResponse)
def set_player_display_timezone(
    public_id: str,
    token: str,
    timezone: str = Form(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    require_player(session, public_id, token)
    try:
        resp = RedirectResponse(url=f"/c/{public_id}/p/{token}", status_code=303)
        set_viewer_timezone_on_response(resp, timezone)
    except ValueError, ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail="Unknown timezone") from None
    return resp


@router.post("/availability/{slot_id}", response_class=HTMLResponse)
def set_my_availability(
    public_id: str,
    token: str,
    slot_id: int,
    request: Request,
    status: str = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign, player = require_player(session, public_id, token)
    display_tz = effective_display_timezone(request, campaign.timezone)

    slot = session.get(Slot, slot_id)
    if slot is None or slot.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Slot not found")

    if status == "yes":
        new_status: AvailabilityStatus | None = AvailabilityStatus.yes
    elif status == "no":
        new_status = AvailabilityStatus.no
    elif status == "clear":
        new_status = None
    else:
        raise HTTPException(status_code=400, detail="Bad status")

    set_availability(
        session,
        player_id=player.id,  # type: ignore[arg-type]
        slot_id=slot_id,
        status=new_status,
    )

    if slot.kind is SlotKind.recurring and new_status is not AvailabilityStatus.yes:
        delete_opt_outs_for_player_slot(session, player.id, slot_id)  # type: ignore[arg-type]

    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    cid = campaign.id
    can_make_pair: tuple[int, int] | None = None
    if cid is not None and slot.id is not None:
        all_players, full_map, opt_outs = roster_availability_context(session, cid)
        start = primary_occurrence_start_for_counts(slot, campaign)
        if start is not None:
            can_make_pair = roster_can_make_occurrence(
                full_map, all_players, opt_outs, slot_id=slot.id, starts_at_utc=start
            )
    resp = templates.TemplateResponse(
        request,
        "fragments/avail_row.html",
        {
            "slot": slot,
            "current": new_status,
            "token": token,
            "campaign": campaign,
            "display_tz": display_tz,
            "can_make_pair": can_make_pair,
        },
    )
    if has_recurring_slot(slots):
        resp.headers["HX-Trigger"] = "refreshExceptions"
    return resp


@router.get("/_recurring-exceptions", response_class=HTMLResponse)
def player_recurring_exceptions_fragment(
    public_id: str,
    token: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign, player = require_player(session, public_id, token)
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    if not has_recurring_slot(slots):
        return HTMLResponse("")
    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    display_tz = effective_display_timezone(request, campaign.timezone)
    cid = campaign.id
    if cid is None:
        all_players, full_map, opt_outs = _empty_roster_context()
    else:
        all_players, full_map, opt_outs = roster_availability_context(session, cid)
    unified_rows = unified_recurring_opt_out_rows(
        campaign,
        player,
        slots,
        session,
        avail_by_slot,
        all_players=all_players,
        full_availability=full_map,
        opt_outs=opt_outs,
    )
    return templates.TemplateResponse(
        request,
        "fragments/player_recurring_exceptions_inner.html",
        {
            "unified_rows": unified_rows,
            "campaign": campaign,
            "player": player,
            "token": token,
            "display_tz": display_tz,
        },
    )


@router.post("/opt-out", response_class=HTMLResponse)
def toggle_occurrence_opt_out(
    public_id: str,
    token: str,
    request: Request,
    slot_id: int = Form(...),
    occurrence_start: str = Form(...),
    busy: str = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign, player = require_player(session, public_id, token)
    display_tz = effective_display_timezone(request, campaign.timezone)
    slot = session.get(Slot, slot_id)
    if slot is None or slot.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Slot not found")

    occ = resolve_occurrence(slot, campaign, occurrence_start)
    if occ is None:
        raise HTTPException(
            status_code=400,
            detail="That date is not a scheduled occurrence for this slot",
        )

    busy_flag = busy.strip().lower() in ("1", "true", "yes", "on")
    if busy_flag:
        add_opt_out(
            session,
            player_id=player.id,  # type: ignore[arg-type]
            slot_id=slot_id,
            starts_at_utc=occ.starts_at_utc,
        )
    else:
        remove_opt_out(
            session,
            player_id=player.id,  # type: ignore[arg-type]
            slot_id=slot_id,
            starts_at_utc=occ.starts_at_utc,
        )

    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    cid = campaign.id
    if cid is None:
        all_players, full_map, opt_outs = _empty_roster_context()
    else:
        all_players, full_map, opt_outs = roster_availability_context(session, cid)
    unified_rows = unified_recurring_opt_out_rows(
        campaign,
        player,
        slots,
        session,
        avail_by_slot,
        all_players=all_players,
        full_availability=full_map,
        opt_outs=opt_outs,
    )
    return templates.TemplateResponse(
        request,
        "fragments/recurring_opt_outs_unified.html",
        {
            "campaign": campaign,
            "player": player,
            "token": token,
            "unified_rows": unified_rows,
            "display_tz": display_tz,
        },
    )

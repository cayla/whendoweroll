"""Per-player availability editor."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_player
from app.models import AvailabilityStatus, Campaign, Player, Slot, SlotKind
from app.services.availability import load_availability_map, set_availability, slot_standing_yes_pair
from app.services.occurrence_match import resolve_occurrence
from app.services.opt_out_bulk import (
    add_opt_outs_in_calendar_range,
    calendar_week_range,
    clear_all_opt_outs_for_standing_yes,
    remove_opt_outs_in_calendar_range,
)
from app.services.opt_outs import (
    add_opt_out,
    delete_opt_outs_for_player_slot,
    remove_opt_out,
)
from app.services.player_view import (
    has_recurring_slot,
    roster_availability_context,
    slot_standing_yes_pairs,
    unified_recurring_opt_out_rows,
)
from app.services.timeutil import ensure_utc
from app.templates_setup import COMMON_TIMEZONES, templates
from app.view_timezone import effective_display_timezone, redirect_with_viewer_timezone

router = APIRouter(prefix="/c/{public_id}/p/{token}")

RosterContext = tuple[
    list[Player],
    dict[tuple[int, int], AvailabilityStatus],
    set[tuple[int, int, datetime]],
]


def _empty_roster_context() -> RosterContext:
    return [], {}, set()


def _bulk_date_defaults(campaign: Campaign) -> tuple[str, str]:
    """Default range spans this week through next week (covers common quick presets)."""
    this_start, _ = calendar_week_range(campaign, offset_weeks=0)
    _, next_end = calendar_week_range(campaign, offset_weeks=1)
    return this_start.isoformat(), next_end.isoformat()


def _recurring_exceptions_context(
    session: Session,
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    *,
    bulk_message: str | None = None,
    bulk_error: str | None = None,
    bulk_start_default: str | None = None,
    bulk_end_default: str | None = None,
    roster: RosterContext | None = None,
) -> dict:
    has_recurring = has_recurring_slot(slots)
    bulk_start, bulk_end = _bulk_date_defaults(campaign)
    if bulk_start_default is not None:
        bulk_start = bulk_start_default
    if bulk_end_default is not None:
        bulk_end = bulk_end_default
    if not has_recurring:
        return {
            "has_recurring": False,
            "unified_rows": [],
            "bulk_start_default": bulk_start,
            "bulk_end_default": bulk_end,
            "bulk_message": bulk_message,
            "bulk_error": bulk_error,
        }
    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    if roster is None:
        cid = campaign.id
        if cid is None:
            all_players, full_map, opt_outs = _empty_roster_context()
        else:
            all_players, full_map, opt_outs = roster_availability_context(session, cid)
    else:
        all_players, full_map, opt_outs = roster
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
    return {
        "has_recurring": True,
        "unified_rows": unified_rows,
        "bulk_start_default": bulk_start,
        "bulk_end_default": bulk_end,
        "bulk_message": bulk_message,
        "bulk_error": bulk_error,
    }


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
        roster = _empty_roster_context()
        can_make_pairs: dict[int, tuple[int, int]] = {}
    else:
        roster = roster_availability_context(session, cid)
        all_players, full_map, _opt_outs = roster
        can_make_pairs = slot_standing_yes_pairs(slots, full_map, all_players)
    exc_ctx = _recurring_exceptions_context(session, campaign, player, slots, roster=roster)
    return templates.TemplateResponse(
        request,
        "player.html",
        {
            "campaign": campaign,
            "player": player,
            "slots": slots,
            "availability": avail_by_slot,
            "token": token,
            "display_tz": display_tz,
            "timezones": COMMON_TIMEZONES,
            "slot_can_make_pairs": can_make_pairs,
            **exc_ctx,
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
        return redirect_with_viewer_timezone(f"/c/{public_id}/p/{token}", timezone)
    except ValueError, ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail="Unknown timezone") from None


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

    if (
        slot.kind is SlotKind.adhoc
        and slot.ends_at_utc is not None
        and ensure_utc(slot.ends_at_utc) <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=400, detail="That one-off session has already ended")

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
        all_players, full_map, _opt_outs = roster_availability_context(session, cid)
        can_make_pair = slot_standing_yes_pair(full_map, all_players, slot.id)
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
    display_tz = effective_display_timezone(request, campaign.timezone)
    exc_ctx = _recurring_exceptions_context(session, campaign, player, slots)
    return templates.TemplateResponse(
        request,
        "fragments/player_recurring_exceptions_inner.html",
        {
            "campaign": campaign,
            "player": player,
            "token": token,
            "display_tz": display_tz,
            **exc_ctx,
        },
    )


def _apply_bulk_exceptions(
    session: Session,
    campaign: Campaign,
    player: Player,
    slots: list[Slot],
    action: str,
    calendar_start_day: str,
    calendar_end_day: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (message, error, start_default, end_default) after a bulk action."""
    bulk_message: str | None = None
    bulk_error: str | None = None
    start_default: str | None = None
    end_default: str | None = None

    if action == "clear_all":
        availability = load_availability_map(session, [player])
        avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
        removed = clear_all_opt_outs_for_standing_yes(
            session,
            player=player,
            slots=slots,
            availability_by_slot=avail_by_slot,
        )
        if removed:
            bulk_message = f"Cleared {removed} conflict{'s' if removed != 1 else ''}."
        else:
            bulk_message = "No conflicts to clear."
        return bulk_message, bulk_error, start_default, end_default

    if action == "mark_this_week":
        start_day, end_day = calendar_week_range(campaign, offset_weeks=0)
    elif action == "mark_next_week":
        start_day, end_day = calendar_week_range(campaign, offset_weeks=1)
    elif action in ("mark_range", "clear_range"):
        try:
            start_day = date.fromisoformat(calendar_start_day.strip())
            end_day = date.fromisoformat(calendar_end_day.strip())
        except ValueError:
            bulk_error = "Enter valid calendar dates."
            return bulk_message, bulk_error, start_default, end_default
        start_default = calendar_start_day.strip()
        end_default = calendar_end_day.strip()
        if start_day > end_day:
            bulk_error = "The last day must be on or after the first day."
            return bulk_message, bulk_error, start_default, end_default
    else:
        bulk_error = "Unknown bulk action."
        return bulk_message, bulk_error, start_default, end_default

    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    range_label = f"{start_day.isoformat()} through {end_day.isoformat()}"

    if action in ("mark_this_week", "mark_next_week", "mark_range"):
        added = add_opt_outs_in_calendar_range(
            session,
            campaign=campaign,
            player=player,
            slots=slots,
            availability_by_slot=avail_by_slot,
            start_day=start_day,
            end_day=end_day,
        )
        if added:
            bulk_message = f"Marked {added} session{'s' if added != 1 else ''} as conflicts ({range_label})."
        else:
            bulk_message = (
                "No new conflicts in that range. "
                "Mark Yes on a recurring time first, or pick dates with upcoming sessions."
            )
    else:
        removed = remove_opt_outs_in_calendar_range(
            session,
            campaign=campaign,
            player=player,
            slots=slots,
            availability_by_slot=avail_by_slot,
            start_day=start_day,
            end_day=end_day,
        )
        if removed:
            bulk_message = f"Cleared {removed} conflict{'s' if removed != 1 else ''} ({range_label})."
        else:
            bulk_message = "No conflicts to clear in that range."

    return bulk_message, bulk_error, start_default, end_default


@router.post("/bulk-exceptions", response_class=HTMLResponse)
def apply_bulk_exceptions(
    public_id: str,
    token: str,
    request: Request,
    action: str = Form(...),
    calendar_start_day: str = Form(""),
    calendar_end_day: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    campaign, player = require_player(session, public_id, token)
    display_tz = effective_display_timezone(request, campaign.timezone)
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()

    bulk_message, bulk_error, start_default, end_default = _apply_bulk_exceptions(
        session,
        campaign,
        player,
        slots,
        action.strip(),
        calendar_start_day,
        calendar_end_day,
    )

    exc_ctx = _recurring_exceptions_context(
        session,
        campaign,
        player,
        slots,
        bulk_message=bulk_message,
        bulk_error=bulk_error,
        bulk_start_default=start_default,
        bulk_end_default=end_default,
    )

    return templates.TemplateResponse(
        request,
        "fragments/player_exceptions_below_toolbar.html",
        {
            "campaign": campaign,
            "player": player,
            "token": token,
            "display_tz": display_tz,
            **exc_ctx,
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
    exc_ctx = _recurring_exceptions_context(session, campaign, player, slots)
    return templates.TemplateResponse(
        request,
        "fragments/player_exceptions_below_toolbar.html",
        {
            "campaign": campaign,
            "player": player,
            "token": token,
            "display_tz": display_tz,
            **exc_ctx,
        },
    )

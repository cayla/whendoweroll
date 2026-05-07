"""Per-player availability editor + personal iCal feed."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_player
from app.models import AvailabilityStatus, OccurrenceOptOut, Player, Slot, SlotKind
from app.services.availability import load_availability_map, roster_can_make_occurrence, set_availability
from app.services.ical import build_ics
from app.services.occurrence_match import resolve_occurrence
from app.services.opt_outs import (
    add_opt_out,
    delete_opt_outs_for_player_slot,
    load_opt_out_set,
    remove_opt_out,
)
from app.services.slots import expand_all, upcoming_occurrences_for_slot
from app.services.timeutil import normalize_occurrence_start
from app.templates_setup import COMMON_TIMEZONES, templates
from app.view_timezone import effective_display_timezone, set_viewer_timezone_on_response

router = APIRouter(prefix="/c/{public_id}/p/{token}")


def _unified_recurring_opt_out_rows(
    campaign,
    player,
    slots: list[Slot],
    session: Session,
    availability_by_slot: dict[int, AvailabilityStatus],
    *,
    all_players: list[Player],
    full_availability: dict[tuple[int, int], AvailabilityStatus],
    opt_outs: set[tuple[int, int, datetime]],
) -> list[dict]:
    """Recurring occurrences in the horizon where this player said *yes*, sorted by start."""
    campaign_tz = ZoneInfo(campaign.timezone)
    pid = player.id
    if pid is None:
        return []

    iso_keys: set[tuple[int, str]] = set()
    for row in session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id == pid)).all():
        iso_keys.add((row.slot_id, normalize_occurrence_start(row.starts_at_utc).isoformat()))

    horizon = min(campaign.horizon_weeks, 26)
    rows: list[dict] = []
    for slot in slots:
        if slot.kind is not SlotKind.recurring:
            continue
        if availability_by_slot.get(slot.id) is not AvailabilityStatus.yes:
            continue
        sid = slot.id
        if sid is None:
            continue
        occs = upcoming_occurrences_for_slot(slot, tz=campaign_tz, horizon_weeks=horizon)
        for o in occs:
            can_make, roster_n = roster_can_make_occurrence(
                full_availability,
                all_players,
                opt_outs,
                slot_id=sid,
                starts_at_utc=o.starts_at_utc,
            )
            rows.append(
                {
                    "slot": slot,
                    "occ": o,
                    "start_iso": normalize_occurrence_start(o.starts_at_utc).isoformat(),
                    "busy": (sid, normalize_occurrence_start(o.starts_at_utc).isoformat()) in iso_keys,
                    "can_make": can_make,
                    "roster_n": roster_n,
                }
            )
    rows.sort(key=lambda r: r["occ"].starts_at_utc)
    return rows


def _has_recurring_slot(slots: list[Slot]) -> bool:
    return any(s.kind is SlotKind.recurring for s in slots)


def _roster_availability_context(
    session: Session, campaign_id: int
) -> tuple[list[Player], dict[tuple[int, int], AvailabilityStatus], set[tuple[int, int, datetime]]]:
    all_players = session.exec(
        select(Player).where(Player.campaign_id == campaign_id).order_by(Player.sort_order)
    ).all()
    full_map = load_availability_map(session, all_players)
    player_ids = [p.id for p in all_players if p.id is not None]
    opt_outs = load_opt_out_set(session, player_ids)
    return all_players, full_map, opt_outs


def _primary_occurrence_start_for_counts(slot: Slot, campaign) -> datetime | None:
    """UTC start used for roster counts on the main slot table (matches primary row label)."""
    if slot.kind is SlotKind.recurring:
        z = ZoneInfo(campaign.timezone)
        horizon = min(campaign.horizon_weeks, 26)
        occs = upcoming_occurrences_for_slot(slot, tz=z, horizon_weeks=horizon)
        if not occs:
            return None
        return occs[0].starts_at_utc
    if slot.kind is SlotKind.adhoc:
        return slot.starts_at_utc
    return None


def _slot_can_make_pairs(
    slots: list[Slot],
    campaign,
    full_map: dict[tuple[int, int], AvailabilityStatus],
    all_players: list[Player],
    opt_outs: set[tuple[int, int, datetime]],
) -> dict[int, tuple[int, int]]:
    """``slot_id -> (can_make, roster_n)`` for the window shown on that row."""
    out: dict[int, tuple[int, int]] = {}
    for slot in slots:
        sid = slot.id
        if sid is None:
            continue
        start = _primary_occurrence_start_for_counts(slot, campaign)
        if start is None:
            continue
        out[sid] = roster_can_make_occurrence(
            full_map, all_players, opt_outs, slot_id=sid, starts_at_utc=start
        )
    return out


def _player_calendar_events(campaign, player, slots: list[Slot], session: Session) -> list[tuple[str, datetime, datetime, str]]:
    tz = ZoneInfo(campaign.timezone)
    occurrences = expand_all(slots, tz=tz, horizon_weeks=campaign.horizon_weeks)
    availability = load_availability_map(session, [player])
    pid = player.id
    if pid is None:
        return []
    opt_outs = load_opt_out_set(session, [pid])
    events: list[tuple[str, datetime, datetime, str]] = []
    for occ in occurrences:
        status = availability.get((player.id, occ.slot_id))  # type: ignore[arg-type]
        if status is not AvailabilityStatus.yes:
            continue
        key = (player.id, occ.slot_id, normalize_occurrence_start(occ.starts_at_utc))
        if key in opt_outs:
            continue
        uid = f"{campaign.public_id}-p{player.id}-s{occ.slot_id}-{int(occ.starts_at_utc.timestamp())}@whendoweroll.com"
        events.append(
            (
                uid,
                occ.starts_at_utc,
                occ.ends_at_utc,
                f"{campaign.name} — {occ.label} ({player.display_name} available)",
            )
        )
    return events


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
        all_players: list[Player] = []
        full_map: dict[tuple[int, int], AvailabilityStatus] = {}
        opt_outs: set[tuple[int, int, datetime]] = set()
        slot_can_make_pairs: dict[int, tuple[int, int]] = {}
    else:
        all_players, full_map, opt_outs = _roster_availability_context(session, cid)
        slot_can_make_pairs = _slot_can_make_pairs(slots, campaign, full_map, all_players, opt_outs)
    unified_rows = _unified_recurring_opt_out_rows(
        campaign,
        player,
        slots,
        session,
        avail_by_slot,
        all_players=all_players,
        full_availability=full_map,
        opt_outs=opt_outs,
    )
    base_url = str(request.base_url).rstrip("/")
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
            "has_recurring": _has_recurring_slot(slots),
            "calendar_url": f"{base_url}/c/{campaign.public_id}/p/{token}/calendar.ics",
            "display_tz": display_tz,
            "timezones": COMMON_TIMEZONES,
            "slot_can_make_pairs": slot_can_make_pairs,
        },
    )


@router.post("/viewer-timezone", response_class=HTMLResponse)
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
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(status_code=400, detail="Unknown timezone") from None
    return resp


@router.get("/calendar.ics")
def player_calendar_ics(
    public_id: str,
    token: str,
    session: Session = Depends(get_session),
) -> Response:
    campaign, player = require_player(session, public_id, token)
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    events = _player_calendar_events(campaign, player, slots, session)
    body = build_ics(events)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="my-dnd-availability.ics"'},
    )


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
        all_players, full_map, opt_outs = _roster_availability_context(session, cid)
        start = _primary_occurrence_start_for_counts(slot, campaign)
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
    if _has_recurring_slot(slots):
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
    if not _has_recurring_slot(slots):
        return HTMLResponse("")
    availability = load_availability_map(session, [player])
    avail_by_slot = {sid: st for (_pid, sid), st in availability.items()}
    display_tz = effective_display_timezone(request, campaign.timezone)
    cid = campaign.id
    if cid is None:
        all_players, full_map, opt_outs = [], {}, set()
    else:
        all_players, full_map, opt_outs = _roster_availability_context(session, cid)
    unified_rows = _unified_recurring_opt_out_rows(
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
        raise HTTPException(status_code=400, detail="That date is not a scheduled occurrence for this slot")

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
        all_players, full_map, opt_outs = [], {}, set()
    else:
        all_players, full_map, opt_outs = _roster_availability_context(session, cid)
    unified_rows = _unified_recurring_opt_out_rows(
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

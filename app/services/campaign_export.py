"""JSON snapshot of a campaign (no capability secrets)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import Availability, Campaign, OccurrenceOptOut, Player, PublicRecurrenceMode, Slot


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def build_export_payload(session: Session, campaign: Campaign) -> dict:
    players = session.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    pids = [p.id for p in players if p.id is not None]

    availability_rows: list[dict] = []
    if pids:
        availability_rows = [
            {"player_id": row.player_id, "slot_id": row.slot_id, "status": row.status.value}
            for row in session.exec(select(Availability).where(Availability.player_id.in_(pids))).all()  # type: ignore[attr-defined]
        ]

    opt_out_rows: list[dict] = []
    if pids:
        opt_out_rows = [
            {
                "player_id": row.player_id,
                "slot_id": row.slot_id,
                "starts_at_utc": _iso(row.starts_at_utc),
            }
            for row in session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id.in_(pids))).all()  # type: ignore[attr-defined]
        ]

    return {
        "export_version": 3,
        "exported_at": _iso(datetime.now(UTC)),
        "campaign": {
            "public_id": campaign.public_id,
            "name": campaign.name,
            "timezone": campaign.timezone,
            "horizon_weeks": campaign.horizon_weeks,
            "consensus_policy": campaign.consensus_policy.value,
            "created_at": _iso(campaign.created_at),
        },
        "players": [
            {
                "id": p.id,
                "display_name": p.display_name,
                "sort_order": p.sort_order,
                "is_mandatory": bool(p.is_mandatory),
            }
            for p in players
        ],
        "slots": [
            {
                "id": s.id,
                "kind": s.kind.value,
                "label": s.label,
                "weekday": s.weekday,
                "start_local": s.start_local,
                "duration_hours": s.duration_hours,
                "starts_at_utc": _iso(s.starts_at_utc),
                "ends_at_utc": _iso(s.ends_at_utc),
                "public_recurrence_mode": (
                    s.public_recurrence_mode.value
                    if isinstance(s.public_recurrence_mode, PublicRecurrenceMode)
                    else str(s.public_recurrence_mode)
                ),
            }
            for s in slots
        ],
        "availability": availability_rows,
        "occurrence_opt_outs": opt_out_rows,
        "_note": (
            "Admin and player URL tokens are never included. Re-import this file "
            "from the home page to restore into a fresh campaign with new links."
        ),
    }

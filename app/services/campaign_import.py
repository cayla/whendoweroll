"""Restore a campaign from a previously-exported JSON snapshot.

The exporter never includes capability secrets, so the only way to "restore"
a backup is to materialize it into a *fresh* campaign with a new admin link
and brand-new per-player links. That matches what users would have to do
manually anyway and keeps every URL in the system unguessable.

Old player/slot ids in the export are remapped to the freshly-assigned ids
during insert; availability and per-occurrence opt-outs are then rewritten
against the new ids. References to ids that don't appear in the file are
treated as a corrupt backup and rejected (better to fail loudly than to
silently drop a player's answers).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session

from app.models import (
    Availability,
    AvailabilityStatus,
    Campaign,
    ConsensusPolicy,
    OccurrenceOptOut,
    Player,
    PublicRecurrenceMode,
    Slot,
    SlotKind,
)
from app.security import hash_token, new_token

SUPPORTED_VERSIONS = {1, 2, 3}


class CampaignImportError(ValueError):
    """Raised when the uploaded file is not a usable export."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise CampaignImportError(msg)


def _parse_iso_utc(value: Any, *, field: str) -> datetime:
    _require(isinstance(value, str) and value, f"{field} must be an ISO-8601 string")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CampaignImportError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if dt.tzinfo is None:
        raise CampaignImportError(f"{field} must include a timezone offset")
    return dt


def _parse_campaign(payload: dict) -> dict:
    _require(isinstance(payload.get("campaign"), dict), "Missing 'campaign' object")
    c = payload["campaign"]
    name = str(c.get("name", "")).strip()
    _require(bool(name), "Campaign name is required")
    _require(len(name) <= 200, "Campaign name is too long")
    tz = str(c.get("timezone", "")).strip()
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise CampaignImportError(f"Unknown timezone: {tz!r}") from exc
    horizon_raw = c.get("horizon_weeks", 12)
    try:
        horizon_weeks = int(horizon_raw)
    except (TypeError, ValueError) as exc:
        raise CampaignImportError("horizon_weeks must be an integer") from exc
    horizon_weeks = max(1, min(horizon_weeks, 52))
    policy_raw = c.get("consensus_policy")
    if policy_raw is None:
        policy = ConsensusPolicy.no_two_nears  # v1/v2 backups predate this field
    else:
        try:
            policy = ConsensusPolicy(str(policy_raw))
        except ValueError as exc:
            raise CampaignImportError(f"Unknown consensus policy: {policy_raw!r}") from exc
    pub_raw = c.get("public_recurrence_mode")
    if pub_raw is None or (isinstance(pub_raw, str) and not pub_raw.strip()):
        public_recurrence_mode: PublicRecurrenceMode | None = None
    else:
        public_recurrence_mode = _parse_public_recurrence_mode_import(
            pub_raw,
            field="campaign.public_recurrence_mode",
        )
    gap_raw = c.get("public_min_gap_days", 0)
    if gap_raw is None or (isinstance(gap_raw, str) and not str(gap_raw).strip()):
        public_min_gap_days = 0
    else:
        try:
            public_min_gap_days = int(gap_raw)
        except (TypeError, ValueError) as exc:
            raise CampaignImportError("campaign.public_min_gap_days must be an integer") from exc
    public_min_gap_days = max(0, min(public_min_gap_days, 30))
    return {
        "name": name,
        "timezone": tz,
        "horizon_weeks": horizon_weeks,
        "consensus_policy": policy,
        "public_recurrence_mode": public_recurrence_mode,
        "public_min_gap_days": public_min_gap_days,
    }


def _infer_public_recurrence_from_legacy_slots(slots_raw: list[Any]) -> PublicRecurrenceMode:
    """When ``campaign.public_recurrence_mode`` is absent, derive from per-slot export fields."""
    modes: set[PublicRecurrenceMode] = set()
    for i, raw in enumerate(slots_raw):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("kind", "")) != SlotKind.recurring.value:
            continue
        legacy_n = raw.get("every_n_weeks")
        if raw.get("public_recurrence_mode") is None and legacy_n in (2, "2"):
            modes.add(PublicRecurrenceMode.twice_per_month)
            continue
        modes.add(
            _parse_public_recurrence_mode_import(
                raw.get("public_recurrence_mode"),
                field=f"slots[{i}].public_recurrence_mode",
            )
        )
    if PublicRecurrenceMode.once_per_month in modes:
        return PublicRecurrenceMode.once_per_month
    if PublicRecurrenceMode.twice_per_month in modes:
        return PublicRecurrenceMode.twice_per_month
    return PublicRecurrenceMode.weekly


def _parse_public_recurrence_mode_import(raw: Any, *, field: str) -> PublicRecurrenceMode:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return PublicRecurrenceMode.weekly
    try:
        return PublicRecurrenceMode(str(raw).strip())
    except ValueError as exc:
        raise CampaignImportError(
            f"{field} must be 'weekly', 'twice_per_month', or 'once_per_month'",
        ) from exc


def _parse_player(raw: Any, *, index: int) -> dict:
    _require(isinstance(raw, dict), f"players[{index}] must be an object")
    name = str(raw.get("display_name", "")).strip()
    _require(bool(name), f"players[{index}].display_name is required")
    _require(len(name) <= 200, f"players[{index}].display_name is too long")
    sort_order_raw = raw.get("sort_order", index)
    try:
        sort_order = int(sort_order_raw)
    except (TypeError, ValueError) as exc:
        raise CampaignImportError(f"players[{index}].sort_order must be an integer") from exc
    return {
        "old_id": raw.get("id"),
        "display_name": name,
        "sort_order": sort_order,
        "is_mandatory": bool(raw.get("is_mandatory", False)),
    }


def _parse_slot(raw: Any, *, index: int) -> dict:
    _require(isinstance(raw, dict), f"slots[{index}] must be an object")
    kind_raw = str(raw.get("kind", ""))
    try:
        kind = SlotKind(kind_raw)
    except ValueError as exc:
        raise CampaignImportError(f"slots[{index}].kind must be 'recurring' or 'adhoc'") from exc

    label = raw.get("label")
    if label is not None:
        label = str(label).strip() or None

    duration_raw = raw.get("duration_hours")
    try:
        duration = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError) as exc:
        raise CampaignImportError(f"slots[{index}].duration_hours must be numeric") from exc

    if kind == SlotKind.recurring:
        weekday_raw = raw.get("weekday")
        try:
            weekday = int(weekday_raw)
        except (TypeError, ValueError) as exc:
            raise CampaignImportError(f"slots[{index}].weekday must be 0..6") from exc
        _require(0 <= weekday <= 6, f"slots[{index}].weekday must be 0..6")
        start_local = str(raw.get("start_local", "")).strip()
        _require(bool(start_local), f"slots[{index}].start_local is required for recurring slots")
        _require(duration is not None and duration > 0, f"slots[{index}].duration_hours must be > 0")
        return {
            "old_id": raw.get("id"),
            "kind": kind,
            "label": label,
            "weekday": weekday,
            "start_local": start_local,
            "duration_hours": duration,
            "starts_at_utc": None,
            "ends_at_utc": None,
        }

    starts_at = _parse_iso_utc(raw.get("starts_at_utc"), field=f"slots[{index}].starts_at_utc")
    ends_at = _parse_iso_utc(raw.get("ends_at_utc"), field=f"slots[{index}].ends_at_utc")
    _require(ends_at > starts_at, f"slots[{index}].ends_at_utc must be after starts_at_utc")
    return {
        "old_id": raw.get("id"),
        "kind": kind,
        "label": label,
        "weekday": None,
        "start_local": None,
        "duration_hours": duration,
        "starts_at_utc": starts_at,
        "ends_at_utc": ends_at,
    }


def _validate_payload(payload: Any) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    _require(isinstance(payload, dict), "Top-level JSON must be an object")
    version = payload.get("export_version")
    _require(version in SUPPORTED_VERSIONS, f"Unsupported export_version: {version!r}")
    campaign_fields = _parse_campaign(payload)

    players_raw = payload.get("players", []) or []
    _require(isinstance(players_raw, list), "'players' must be a list")
    players = [_parse_player(p, index=i) for i, p in enumerate(players_raw)]

    slots_raw = payload.get("slots", []) or []
    _require(isinstance(slots_raw, list), "'slots' must be a list")
    slots = [_parse_slot(s, index=i) for i, s in enumerate(slots_raw)]
    if campaign_fields["public_recurrence_mode"] is None:
        campaign_fields["public_recurrence_mode"] = _infer_public_recurrence_from_legacy_slots(slots_raw)

    avail_raw = payload.get("availability", []) or []
    _require(isinstance(avail_raw, list), "'availability' must be a list")
    availability: list[dict] = []
    for i, row in enumerate(avail_raw):
        _require(isinstance(row, dict), f"availability[{i}] must be an object")
        try:
            status = AvailabilityStatus(str(row.get("status", "")))
        except ValueError as exc:
            raise CampaignImportError(f"availability[{i}].status must be 'yes' or 'no'") from exc
        availability.append({"player_id": row.get("player_id"), "slot_id": row.get("slot_id"), "status": status})

    opt_outs_raw = payload.get("occurrence_opt_outs", []) or []
    _require(isinstance(opt_outs_raw, list), "'occurrence_opt_outs' must be a list")
    opt_outs: list[dict] = []
    for i, row in enumerate(opt_outs_raw):
        _require(isinstance(row, dict), f"occurrence_opt_outs[{i}] must be an object")
        starts_at = _parse_iso_utc(row.get("starts_at_utc"), field=f"occurrence_opt_outs[{i}].starts_at_utc")
        opt_outs.append({"player_id": row.get("player_id"), "slot_id": row.get("slot_id"), "starts_at_utc": starts_at})

    return campaign_fields, players, slots, availability, opt_outs


def import_campaign(session: Session, payload: Any) -> tuple[Campaign, str, list[tuple[Player, str]]]:
    """Validate ``payload`` and materialize a brand-new campaign from it.

    Returns the campaign, its plaintext admin secret, and the list of
    ``(player, plaintext_token)`` pairs for the freshly-created roster, in
    sort order. Raises :class:`CampaignImportError` for any structural problem.
    """

    campaign_fields, players, slots, availability, opt_outs = _validate_payload(payload)

    public_id = uuid.uuid4().hex
    admin_secret = new_token()
    campaign = Campaign(
        public_id=public_id,
        name=campaign_fields["name"],
        timezone=campaign_fields["timezone"],
        admin_secret_hash=hash_token(admin_secret),
        horizon_weeks=campaign_fields["horizon_weeks"],
        consensus_policy=campaign_fields["consensus_policy"],
        public_recurrence_mode=campaign_fields["public_recurrence_mode"],
        public_min_gap_days=campaign_fields["public_min_gap_days"],
    )
    session.add(campaign)
    session.flush()  # need campaign.id

    player_id_map: dict[Any, int] = {}
    created_players: list[tuple[Player, str]] = []
    for spec in sorted(players, key=lambda p: p["sort_order"]):
        token = new_token()
        player = Player(
            campaign_id=campaign.id,  # type: ignore[arg-type]
            display_name=spec["display_name"],
            token_hash=hash_token(token),
            sort_order=spec["sort_order"],
            is_mandatory=spec["is_mandatory"],
        )
        session.add(player)
        session.flush()
        if spec["old_id"] is not None:
            player_id_map[spec["old_id"]] = player.id  # type: ignore[assignment]
        created_players.append((player, token))

    slot_id_map: dict[Any, int] = {}
    for spec in slots:
        slot = Slot(
            campaign_id=campaign.id,  # type: ignore[arg-type]
            kind=spec["kind"],
            label=spec["label"],
            weekday=spec["weekday"],
            start_local=spec["start_local"],
            duration_hours=spec["duration_hours"],
            starts_at_utc=spec["starts_at_utc"],
            ends_at_utc=spec["ends_at_utc"],
        )
        session.add(slot)
        session.flush()
        if spec["old_id"] is not None:
            slot_id_map[spec["old_id"]] = slot.id  # type: ignore[assignment]

    for row in availability:
        old_pid, old_sid = row["player_id"], row["slot_id"]
        if old_pid not in player_id_map:
            raise CampaignImportError("availability references unknown player id")
        if old_sid not in slot_id_map:
            raise CampaignImportError("availability references unknown slot id")
        new_player_id = player_id_map[old_pid]
        new_slot_id = slot_id_map[old_sid]
        session.add(Availability(player_id=new_player_id, slot_id=new_slot_id, status=row["status"]))

    for row in opt_outs:
        old_pid, old_sid = row["player_id"], row["slot_id"]
        if old_pid not in player_id_map:
            raise CampaignImportError("occurrence_opt_outs references unknown player id")
        if old_sid not in slot_id_map:
            raise CampaignImportError("occurrence_opt_outs references unknown slot id")
        new_player_id = player_id_map[old_pid]
        new_slot_id = slot_id_map[old_sid]
        session.add(
            OccurrenceOptOut(
                player_id=new_player_id,
                slot_id=new_slot_id,
                starts_at_utc=row["starts_at_utc"],
            )
        )

    session.commit()
    session.refresh(campaign)
    return campaign, admin_secret, created_players

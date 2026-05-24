"""Shared data loading for the public page and consensus ICS feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models import AvailabilityStatus, Campaign, Player, Slot
from app.services.availability import load_availability_map
from app.services.opt_outs import load_opt_out_set
from app.services.public_occurrence_filter import filter_occurrences_for_public_display
from app.services.slots import Occurrence, expand_all


@dataclass(frozen=True)
class PublicConsensusData:
    players: list[Player]
    slots: list[Slot]
    occurrences_full: list[Occurrence]
    occurrences_public: list[Occurrence]
    availability: dict[tuple[int, int], AvailabilityStatus]
    opt_outs: set[tuple[int, int, datetime]]


def load_public_consensus_data(session: Session, campaign: Campaign) -> PublicConsensusData:
    """Players, slots, expanded occurrences, availability, and tempo-thinned public list."""
    players = session.exec(select(Player).where(Player.campaign_id == campaign.id).order_by(Player.sort_order)).all()
    slots = session.exec(select(Slot).where(Slot.campaign_id == campaign.id)).all()
    tz = ZoneInfo(campaign.timezone)
    occurrences_full = expand_all(slots, tz=tz, horizon_weeks=campaign.horizon_weeks)
    availability = load_availability_map(session, players)
    player_ids = [p.id for p in players if p.id is not None]
    opt_outs = load_opt_out_set(session, player_ids)
    occurrences_public = filter_occurrences_for_public_display(
        occurrences_full,
        slots,
        tz=tz,
        players=players,
        availability=availability,
        policy=campaign.consensus_policy,
        opt_outs=opt_outs,
        public_recurrence_mode=campaign.public_recurrence_mode,
    )
    return PublicConsensusData(
        players=players,
        slots=slots,
        occurrences_full=occurrences_full,
        occurrences_public=occurrences_public,
        availability=availability,
        opt_outs=opt_outs,
    )

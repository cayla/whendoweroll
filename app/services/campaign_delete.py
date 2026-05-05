"""Delete a campaign and all related rows."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Availability, Campaign, Player, Slot
from app.services.opt_outs import delete_for_player, delete_for_slot


def delete_campaign_cascade(session: Session, campaign: Campaign) -> None:
    """Remove the campaign and all related rows (players, slots, availability, opt-outs)."""
    cid = campaign.id
    if cid is None:
        raise ValueError("Campaign has no id")

    slots = session.exec(select(Slot).where(Slot.campaign_id == cid)).all()
    for slot in slots:
        if slot.id is None:
            continue
        avails = session.exec(select(Availability).where(Availability.slot_id == slot.id)).all()
        for a in avails:
            session.delete(a)
        delete_for_slot(session, slot.id)
        session.delete(slot)

    players = session.exec(select(Player).where(Player.campaign_id == cid)).all()
    for player in players:
        if player.id is None:
            continue
        avails = session.exec(select(Availability).where(Availability.player_id == player.id)).all()
        for a in avails:
            session.delete(a)
        delete_for_player(session, player.id)
        session.delete(player)

    session.delete(campaign)
    session.commit()

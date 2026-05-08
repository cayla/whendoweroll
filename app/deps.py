"""Reusable lookups that resolve capability URLs to DB rows.

These keep route handlers boring: each one returns the campaign / player after
checking the secret hashes, or raises 404. Returning 404 (rather than 403) for
bad secrets is intentional — we don't want to confirm that a campaign exists
to someone fishing for valid public ids.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Campaign, Player
from app.security import hash_token, tokens_match


def get_campaign_or_404(session: Session, public_id: str) -> Campaign:
    campaign = session.exec(select(Campaign).where(Campaign.public_id == public_id)).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def require_admin(session: Session, public_id: str, secret: str) -> Campaign:
    campaign = get_campaign_or_404(session, public_id)
    if not tokens_match(secret, campaign.admin_secret_hash):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def require_player(session: Session, public_id: str, token: str) -> tuple[Campaign, Player]:
    campaign = get_campaign_or_404(session, public_id)
    player = session.exec(
        select(Player).where(Player.campaign_id == campaign.id, Player.token_hash == hash_token(token))
    ).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign, player

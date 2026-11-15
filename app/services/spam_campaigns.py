"""Detect SEO/outreach spam campaigns that abuse campaign create as a contact form."""

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, func, select

from app.models import Campaign, Player, Slot

# Pitch paragraphs stuffed into player names; real display names are short.
_LONG_NAME_CHARS = 80
_PREVIEW_CHARS = 400


@dataclass(frozen=True)
class SpamCandidate:
    """One likely-spam campaign for the super-admin cleanup UI."""

    name: str
    public_id: str
    created_at: datetime
    player_count: int
    pitch_preview: str


def _pitch_preview(names: list[str]) -> str:
    joined = "\n".join(names)
    if len(joined) <= _PREVIEW_CHARS:
        return joined
    return joined[:_PREVIEW_CHARS].rstrip() + "…"


def list_spam_candidates(session: Session) -> list[SpamCandidate]:
    """Campaigns with no slots and at least one long player display_name.

    Zero slots separated all known spam from real campaigns in production.
    The length check avoids deleting a brand-new legit campaign that has not
    added schedules yet.
    """
    slotted = select(Slot.campaign_id).where(col(Slot.campaign_id).is_not(None)).distinct()
    long_name_campaigns = (
        select(Player.campaign_id).where(func.length(Player.display_name) > _LONG_NAME_CHARS).distinct()
    )
    campaigns = session.exec(
        select(Campaign)
        .where(col(Campaign.id).not_in(slotted))
        .where(col(Campaign.id).in_(long_name_campaigns))
        .order_by(Campaign.created_at.desc())
    ).all()
    if not campaigns:
        return []

    ids = [c.id for c in campaigns if c.id is not None]
    players_by_campaign: dict[int, list[Player]] = {cid: [] for cid in ids}
    if ids:
        for player in session.exec(select(Player).where(col(Player.campaign_id).in_(ids)).order_by(Player.sort_order)):
            players_by_campaign.setdefault(player.campaign_id, []).append(player)

    out: list[SpamCandidate] = []
    for c in campaigns:
        if c.id is None:
            continue
        players = players_by_campaign.get(c.id, [])
        names = [p.display_name for p in players]
        out.append(
            SpamCandidate(
                name=c.name,
                public_id=c.public_id,
                created_at=c.created_at,
                player_count=len(players),
                pitch_preview=_pitch_preview(names),
            )
        )
    return out

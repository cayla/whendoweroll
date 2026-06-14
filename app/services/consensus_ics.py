"""Build the per-campaign consensus ``.ics`` feed to match the public summary cards."""

from __future__ import annotations

from app.models import Campaign
from app.services.consensus import find_next_meets
from app.services.ical import IcsEvent, placeholder_consensus_event
from app.services.public_consensus_data import PublicConsensusData

# Public page copy: "The calendar will only lock in the next two sessions at most!"
PUBLIC_LOCKED_SESSION_LIMIT = 2


def _event_uid(public_id: str, slot_id: int, starts_at_utc) -> str:
    return f"{public_id}-s{slot_id}-{int(starts_at_utc.timestamp())}@whendoweroll.com"


def build_consensus_ics_events(
    campaign: Campaign,
    data: PublicConsensusData,
) -> list[IcsEvent]:
    """Return the same locked sessions shown on the public summary cards."""
    results = find_next_meets(
        data.occurrences_public,
        data.players,
        data.availability,
        policy=campaign.consensus_policy,
        opt_outs=data.opt_outs,
        limit=PUBLIC_LOCKED_SESSION_LIMIT,
        proximity_occurrences=data.occurrences_full if campaign.prefer_full_party else None,
    )
    name_by_id = {p.id: p.display_name for p in data.players if p.id is not None}
    events: list[IcsEvent] = []
    for res in results:
        occ = res.occurrence
        if res.missing_player_ids:
            missing_names = ", ".join(name_by_id.get(pid, "?") for pid in res.missing_player_ids)
            summary = f"[missing: {missing_names}] {campaign.name} — {occ.label}"
        else:
            summary = f"{campaign.name} — everyone available ({occ.label})"
        events.append(
            IcsEvent(
                uid=_event_uid(campaign.public_id, occ.slot_id, occ.starts_at_utc),
                start=occ.starts_at_utc,
                end=occ.ends_at_utc,
                summary=summary,
            )
        )
    if not events:
        return [placeholder_consensus_event(campaign.public_id, campaign.name)]
    return events

"""Build the per-campaign consensus ``.ics`` feed to match the public summary cards."""

from __future__ import annotations

from datetime import datetime

from app.models import Campaign
from app.services.consensus import ConsensusResult, find_next_meets
from app.services.ical import IcsEvent, placeholder_consensus_event
from app.services.public_consensus_data import PublicConsensusData
from app.services.slots import Occurrence
from app.services.timeutil import normalize_occurrence_start

# Public page copy: "The calendar will only lock in the next two sessions at most!"
PUBLIC_LOCKED_SESSION_LIMIT = 2


def _occurrence_key(occ: Occurrence) -> tuple[int, datetime]:
    return (occ.slot_id, normalize_occurrence_start(occ.starts_at_utc))


def _event_uid(public_id: str, occ: Occurrence) -> str:
    return f"{public_id}-s{occ.slot_id}-{int(occ.starts_at_utc.timestamp())}@whendoweroll.com"


def _result_to_event(
    campaign: Campaign,
    result: ConsensusResult,
    name_by_id: dict[int, str],
) -> IcsEvent:
    occ = result.occurrence
    if result.missing_player_ids:
        missing_names = ", ".join(name_by_id.get(pid, "?") for pid in result.missing_player_ids)
        summary = f"[missing: {missing_names}] {campaign.name} — {occ.label}"
    else:
        summary = f"{campaign.name} — everyone available ({occ.label})"
    return IcsEvent(
        uid=_event_uid(campaign.public_id, occ),
        start=occ.starts_at_utc,
        end=occ.ends_at_utc,
        summary=summary,
    )


def _cancelled_tombstones_in_locked_span(
    *,
    campaign: Campaign,
    locked: list[ConsensusResult],
    occurrences_full: list[Occurrence],
    active_keys: set[tuple[int, datetime]],
) -> list[IcsEvent]:
    """Emit ``STATUS:CANCELLED`` events for stale feed rows between locked sessions.

    Subscribed calendar clients often keep orphaned events when a window drops
    out of the feed. Re-emitting the same ``UID`` as cancelled lets Apple
    Calendar and others remove sessions that no longer match the public cards.
    """
    if not locked:
        return []
    span_start = locked[0].occurrence.starts_at_utc
    span_end = locked[-1].occurrence.starts_at_utc
    tombstones: list[IcsEvent] = []
    for occ in occurrences_full:
        start = occ.starts_at_utc
        if start < span_start or start > span_end:
            continue
        if _occurrence_key(occ) in active_keys:
            continue
        tombstones.append(
            IcsEvent(
                uid=_event_uid(campaign.public_id, occ),
                start=start,
                end=occ.ends_at_utc,
                summary=f"{campaign.name} — removed from schedule",
                cancelled=True,
            )
        )
    return tombstones


def build_consensus_ics_events(
    campaign: Campaign,
    data: PublicConsensusData,
) -> list[IcsEvent]:
    """Return active locked sessions plus cancellation tombstones in their span."""
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
    active_keys = {_occurrence_key(r.occurrence) for r in results}
    events = [_result_to_event(campaign, res, name_by_id) for res in results]
    events.extend(
        _cancelled_tombstones_in_locked_span(
            campaign=campaign,
            locked=results,
            occurrences_full=data.occurrences_full,
            active_keys=active_keys,
        )
    )
    if not events:
        return [placeholder_consensus_event(campaign.public_id, campaign.name)]
    return events

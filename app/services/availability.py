"""Read/write helpers for the availability table."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import Availability, AvailabilityStatus, Player
from app.services.timeutil import normalize_occurrence_start


def roster_can_make_occurrence(
    availability: dict[tuple[int, int], AvailabilityStatus],
    players: Iterable[Player],
    opt_outs: set[tuple[int, int, datetime]],
    *,
    slot_id: int,
    starts_at_utc: datetime,
) -> tuple[int, int]:
    """How many roster members can attend this occurrence vs roster size.

    Counts players with standing *yes* on the slot who have not opted out of
    this concrete start. ``(can_make, roster_n)``.
    """
    roster = [p for p in players if p.id is not None]
    n = len(roster)
    key_start = normalize_occurrence_start(starts_at_utc)
    can = 0
    for p in roster:
        if availability.get((p.id, slot_id)) is not AvailabilityStatus.yes:
            continue
        if (p.id, slot_id, key_start) in opt_outs:
            continue
        can += 1
    return can, n


def load_availability_map(
    session: Session,
    players: Iterable[Player],
) -> dict[tuple[int, int], AvailabilityStatus]:
    player_ids = [p.id for p in players if p.id is not None]
    if not player_ids:
        return {}
    rows = session.exec(
        select(Availability).where(Availability.player_id.in_(player_ids))  # type: ignore[attr-defined]
    ).all()
    return {(row.player_id, row.slot_id): row.status for row in rows}


def set_availability(
    session: Session,
    *,
    player_id: int,
    slot_id: int,
    status: AvailabilityStatus | None,
) -> AvailabilityStatus | None:
    """Upsert the row, or delete it when ``status`` is ``None`` (= unset)."""
    existing = session.exec(
        select(Availability).where(
            Availability.player_id == player_id,
            Availability.slot_id == slot_id,
        )
    ).first()
    if status is None:
        if existing:
            session.delete(existing)
        session.commit()
        return None
    if existing:
        existing.status = status
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        session.add(
            Availability(
                player_id=player_id,
                slot_id=slot_id,
                status=status,
            )
        )
    session.commit()
    return status

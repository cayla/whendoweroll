"""Read/write helpers for the availability table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlmodel import Session, select

from app.models import Availability, AvailabilityStatus, Player


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
        existing.updated_at = datetime.now(timezone.utc)
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

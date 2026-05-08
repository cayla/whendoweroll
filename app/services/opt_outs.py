"""Per-occurrence opt-outs for recurring (or any) slots.

A player who said *yes* to ``Friday 18:00`` can still mark ``May 29`` as
unavailable for that one concrete occurrence without changing their standing
answer for every other Friday.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlmodel import Session, select

from app.models import OccurrenceOptOut
from app.services.timeutil import normalize_occurrence_start


def load_opt_out_set(session: Session, player_ids: Iterable[int]) -> set[tuple[int, int, datetime]]:
    ids = list(player_ids)
    if not ids:
        return set()
    rows = session.exec(
        select(OccurrenceOptOut).where(OccurrenceOptOut.player_id.in_(ids))  # type: ignore[attr-defined]
    ).all()
    return {(row.player_id, row.slot_id, normalize_occurrence_start(row.starts_at_utc)) for row in rows}


def add_opt_out(session: Session, *, player_id: int, slot_id: int, starts_at_utc: datetime) -> None:
    key_start = normalize_occurrence_start(starts_at_utc)
    existing_rows = session.exec(
        select(OccurrenceOptOut).where(
            OccurrenceOptOut.player_id == player_id,
            OccurrenceOptOut.slot_id == slot_id,
        )
    ).all()
    for row in existing_rows:
        if normalize_occurrence_start(row.starts_at_utc) == key_start:
            return
    session.add(
        OccurrenceOptOut(
            player_id=player_id,
            slot_id=slot_id,
            starts_at_utc=key_start,
        )
    )
    session.commit()


def remove_opt_out(session: Session, *, player_id: int, slot_id: int, starts_at_utc: datetime) -> None:
    key_start = normalize_occurrence_start(starts_at_utc)
    existing_rows = session.exec(
        select(OccurrenceOptOut).where(
            OccurrenceOptOut.player_id == player_id,
            OccurrenceOptOut.slot_id == slot_id,
        )
    ).all()
    for row in existing_rows:
        if normalize_occurrence_start(row.starts_at_utc) == key_start:
            session.delete(row)
            session.commit()
            return


def delete_for_player(session: Session, player_id: int) -> None:
    rows = session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.player_id == player_id)).all()
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()


def delete_for_slot(session: Session, slot_id: int) -> None:
    rows = session.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.slot_id == slot_id)).all()
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()


def delete_opt_outs_for_player_slot(session: Session, player_id: int, slot_id: int) -> None:
    """Remove all per-occurrence opt-outs when the player revokes standing *yes*."""
    rows = session.exec(
        select(OccurrenceOptOut).where(
            OccurrenceOptOut.player_id == player_id,
            OccurrenceOptOut.slot_id == slot_id,
        )
    ).all()
    for row in rows:
        session.delete(row)
    if rows:
        session.commit()

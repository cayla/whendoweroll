"""Database models.

A single ``slot`` table holds both recurring rules and ad-hoc one-offs,
distinguished by ``kind``. The relevant columns are nullable depending on
kind, validated at the application layer when slots are created.

Time conventions:
  - Recurring slots: ``weekday`` (0 = Monday, 6 = Sunday), ``start_local``
    as ``HH:MM`` in the campaign timezone, and ``duration_hours`` (fractional
    hours, e.g. ``3.5``). Occurrence end is start plus that duration (may
    cross midnight).
  - Ad-hoc slots: ``starts_at_utc`` / ``ends_at_utc`` in UTC, plus
    ``duration_hours`` mirroring the admin form. The UI collects campaign-local
    **date**, **start time**, and **duration (hours)**.
  - ``OccurrenceOptOut``: for a recurring slot, a player can opt out of one
    concrete occurrence (identified by that occurrence's UTC start) while
    keeping their standing yes/no on the logical slot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SlotKind(str, Enum):
    recurring = "recurring"
    adhoc = "adhoc"


class AvailabilityStatus(str, Enum):
    yes = "yes"
    no = "no"


class Campaign(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(index=True, unique=True)
    name: str
    timezone: str  # IANA, e.g. "America/New_York"
    admin_secret_hash: str
    horizon_weeks: int = 12
    created_at: datetime = Field(default_factory=_utcnow)


class Player(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    display_name: str
    token_hash: str = Field(index=True, unique=True)
    sort_order: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class Slot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    kind: SlotKind
    label: Optional[str] = None

    weekday: Optional[int] = None  # 0=Mon..6=Sun, recurring only
    start_local: Optional[str] = None  # "HH:MM", recurring only
    duration_hours: Optional[float] = None  # recurring + adhoc; fractional OK

    starts_at_utc: Optional[datetime] = None  # adhoc only
    ends_at_utc: Optional[datetime] = None  # adhoc only

    created_at: datetime = Field(default_factory=_utcnow)


class Availability(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    slot_id: int = Field(foreign_key="slot.id", index=True)
    status: AvailabilityStatus
    updated_at: datetime = Field(default_factory=_utcnow)


class OccurrenceOptOut(SQLModel, table=True):
    """One row = player opts out of this single concrete occurrence (same slot_id + start)."""

    __tablename__ = "occurrence_opt_out"
    __table_args__ = (
        UniqueConstraint("player_id", "slot_id", "starts_at_utc", name="uq_opt_out_player_slot_start"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    slot_id: int = Field(foreign_key="slot.id", index=True)
    starts_at_utc: datetime  # UTC instant when this occurrence begins
    created_at: datetime = Field(default_factory=_utcnow)

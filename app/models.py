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
  - **Public tempo** (``Campaign.public_recurrence_mode``): how often the group
    wants sessions to surface on the **public** next-game cards and consensus
    ``.ics`` only. Applies across all recurring slot options together. Player
    pages always list every occurrence. ``weekly`` (default),
    ``two_weeks`` (about a fourteen-day beat), and ``once_per_month`` all use the
    same public **tempo chain**: earliest qualifying window first, then each
    next listing is chosen near an anchor **7 days**, **14 days**, or **one
    calendar month** after the previous kept start (closest qualifying match in
    a lookahead bracket).
  - ``OccurrenceOptOut``: for a recurring slot, a player can opt out of one
    concrete occurrence (identified by that occurrence's UTC start) while
    keeping their standing yes/no on the logical slot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SlotKind(StrEnum):
    recurring = "recurring"
    adhoc = "adhoc"


class PublicRecurrenceMode(StrEnum):
    """How the campaign thins recurring dates on the public page and consensus ICS.

    ``two_weeks`` is the fourteen-day tempo (not “two dates per calendar month”).
    """

    weekly = "weekly"
    two_weeks = "two_weeks"
    once_per_month = "once_per_month"


class AvailabilityStatus(StrEnum):
    yes = "yes"
    no = "no"


class ConsensusPolicy(StrEnum):
    """Rule for what counts as a "we'd actually play" window.

    Drives both the two cards on the public page and the campaign's ICS
    feed: the calendar is meant to be tight enough to rely on as the
    authoritative play schedule. Mandatory-attendee rules apply on top of
    every policy; a missing mandatory always disqualifies a window.
    """

    strict = "strict"  # full consensus only (zero missing)
    allow_one = "allow_one"  # up to 1 missing, no guardrail
    no_two_nears = "no_two_nears"  # up to 1 missing, but never two near-consensus in a row
    no_repeat_holdout = "no_repeat_holdout"  # up to 1 missing, never the same person two in a row


class Campaign(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    public_id: str = Field(index=True, unique=True)
    name: str
    timezone: str  # IANA, e.g. "America/New_York"
    admin_secret_hash: str
    horizon_weeks: int = 12
    consensus_policy: ConsensusPolicy = Field(
        default=ConsensusPolicy.no_two_nears,
        description=(
            "How the public cards and ICS feed decide which upcoming "
            "windows count as a real session. See ConsensusPolicy."
        ),
    )
    public_recurrence_mode: PublicRecurrenceMode = Field(
        default=PublicRecurrenceMode.weekly,
        description=(
            "Thins which recurring occurrences feed public cards and ICS; "
            "player views always use full weekly expansion."
        ),
    )
    created_at: datetime = Field(default_factory=_utcnow)


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    display_name: str
    token_hash: str = Field(index=True, unique=True)
    sort_order: int = 0
    is_mandatory: bool = Field(
        default=False,
        description=(
            "If true, public consensus never counts a window where this "
            "player is absent. Multiple players may be mandatory; every "
            "mandatory attendee must be present (and not opted out) for an "
            "occurrence to qualify."
        ),
    )
    created_at: datetime = Field(default_factory=_utcnow)


class Slot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    kind: SlotKind
    label: str | None = None

    weekday: int | None = None  # 0=Mon..6=Sun, recurring only
    start_local: str | None = None  # "HH:MM", recurring only
    duration_hours: float | None = None  # recurring + adhoc; fractional OK

    starts_at_utc: datetime | None = None  # adhoc only
    ends_at_utc: datetime | None = None  # adhoc only

    created_at: datetime = Field(default_factory=_utcnow)


class Availability(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    slot_id: int = Field(foreign_key="slot.id", index=True)
    status: AvailabilityStatus
    updated_at: datetime = Field(default_factory=_utcnow)


class OccurrenceOptOut(SQLModel, table=True):
    """One row = player opts out of this single concrete occurrence (same slot_id + start)."""

    __tablename__ = "occurrence_opt_out"
    __table_args__ = (UniqueConstraint("player_id", "slot_id", "starts_at_utc", name="uq_opt_out_player_slot_start"),)

    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    slot_id: int = Field(foreign_key="slot.id", index=True)
    starts_at_utc: datetime  # UTC instant when this occurrence begins
    created_at: datetime = Field(default_factory=_utcnow)

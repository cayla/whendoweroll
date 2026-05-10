"""Thin recurring occurrences for the public page and consensus ICS only.

Every tempo uses the same **momentum chain** on recurring rows:

1. **First kept row** — earliest start that passes ``occurrence_qualifies_under_policy``
   (same per-window bar as the public consensus / near-consensus cards for the
   campaign policy). If nothing qualifies, fall back to the earliest row so the
   chain can still advance.

2. **Each next row** — anchor from the previous **kept** start (campaign-local
   calendar math; local wall clock preserved), then among later starts inside a
   lookahead bracket, take the policy-eligible row **closest in time** to that
   anchor (ties: closer to the nominal step, then a light slot-rotation
   tie-break). If the bracket is empty, use the chronologically next row.

Anchors:

  - ``weekly``: previous kept + **7** calendar days.
  - ``twice_per_month``: previous kept + **14** calendar days.
  - ``once_per_month``: previous kept + **1** calendar month (same day when
    possible; shorter months clamp, e.g. Jan 31 → Feb 28).

Bracket upper bound: second anchor step (``+14d`` / ``+2 months``) from the
previous kept start — same shape as the historical weekly rhythm window.

Player-facing routes use full ``expand_all`` output unchanged. Ad-hoc sessions
are not tempo-thinned.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import AvailabilityStatus, ConsensusPolicy, Player, PublicRecurrenceMode, Slot, SlotKind
from app.services.consensus import occurrence_qualifies_under_policy
from app.services.slots import Occurrence


def _add_local_calendar_days(dt_utc: datetime, days: int, tz: ZoneInfo) -> datetime:
    """``dt_utc`` plus ``days`` calendar days in ``tz``, keeping local wall-clock time."""
    loc = dt_utc.astimezone(tz)
    new_d = loc.date() + timedelta(days=days)
    new_loc = datetime.combine(new_d, loc.time(), tzinfo=tz)
    return new_loc.astimezone(UTC)


def _add_local_calendar_months(dt_utc: datetime, months: int, tz: ZoneInfo) -> datetime:
    """``dt_utc`` plus ``months`` whole calendar months in ``tz``, keeping local time-of-day."""
    loc = dt_utc.astimezone(tz)
    y, m, d = loc.year, loc.month, loc.day
    m0 = m - 1 + months
    y += m0 // 12
    m = m0 % 12 + 1
    last_dom = calendar.monthrange(y, m)[1]
    d = min(d, last_dom)
    new_loc = datetime(y, m, d, loc.hour, loc.minute, loc.second, loc.microsecond, tzinfo=tz)
    return new_loc.astimezone(UTC)


def _local_calendar_days_after_last(o: Occurrence, last_occ: Occurrence, tz: ZoneInfo) -> int:
    return (o.starts_at_utc.astimezone(tz).date() - last_occ.starts_at_utc.astimezone(tz).date()).days


def _local_calendar_month_delta(last_occ: Occurrence, o: Occurrence, tz: ZoneInfo) -> int:
    la = last_occ.starts_at_utc.astimezone(tz).date()
    ob = o.starts_at_utc.astimezone(tz).date()
    return (ob.year - la.year) * 12 + (ob.month - la.month)


def _pick_rhythm_occurrence(
    window: list[Occurrence],
    *,
    last_occ: Occurrence,
    ideal_utc: datetime,
    period_days: int,
    tz: ZoneInfo,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
) -> Occurrence:
    """Prefer policy-eligible rows near ``ideal``; exact ``+period`` calendar days when viable."""

    def dist_ideal(o: Occurrence) -> float:
        return abs((o.starts_at_utc - ideal_utc).total_seconds())

    def dist_period(o: Occurrence) -> int:
        return abs(_local_calendar_days_after_last(o, last_occ, tz) - period_days)

    viable = [o for o in window if occurrence_qualifies_under_policy(o, players, availability, policy, opt_outs)]
    pool = viable if viable else window

    exact = [o for o in pool if _local_calendar_days_after_last(o, last_occ, tz) == period_days]
    if exact:
        return min(
            exact,
            key=lambda o: (
                dist_ideal(o),
                int(o.slot_id == last_occ.slot_id),
                o.starts_at_utc,
            ),
        )

    return min(
        pool,
        key=lambda o: (
            dist_ideal(o),
            dist_period(o),
            int(o.slot_id == last_occ.slot_id),
            o.starts_at_utc,
        ),
    )


def _pick_monthly_tempo_occurrence(
    window: list[Occurrence],
    *,
    last_occ: Occurrence,
    ideal_utc: datetime,
    tz: ZoneInfo,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
) -> Occurrence:
    """Like day-based rhythm, but the nominal step is +1 calendar month from ``last_occ``."""

    def dist_ideal(o: Occurrence) -> float:
        return abs((o.starts_at_utc - ideal_utc).total_seconds())

    def dist_months(o: Occurrence) -> int:
        return abs(_local_calendar_month_delta(last_occ, o, tz) - 1)

    # Prefer candidates in a **later** calendar month than ``last_occ`` so same-month
    # noise cannot beat the "next month" anchor (e.g. Jan 31 vs ideal Feb 3).
    forward = [o for o in window if _local_calendar_month_delta(last_occ, o, tz) >= 1]
    scoped = forward if forward else window

    viable = [o for o in scoped if occurrence_qualifies_under_policy(o, players, availability, policy, opt_outs)]
    pool = viable if viable else scoped

    exact = [o for o in pool if _local_calendar_month_delta(last_occ, o, tz) == 1]
    if exact:
        return min(
            exact,
            key=lambda o: (
                dist_ideal(o),
                int(o.slot_id == last_occ.slot_id),
                o.starts_at_utc,
            ),
        )

    return min(
        pool,
        key=lambda o: (
            dist_ideal(o),
            dist_months(o),
            int(o.slot_id == last_occ.slot_id),
            o.starts_at_utc,
        ),
    )


def _apply_public_tempo_chain(
    recurring: Sequence[Occurrence],
    *,
    tz: ZoneInfo,
    mode: PublicRecurrenceMode,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
) -> list[Occurrence]:
    pool = sorted(recurring, key=lambda o: o.starts_at_utc)
    if not pool:
        return []
    viable_first = [o for o in pool if occurrence_qualifies_under_policy(o, players, availability, policy, opt_outs)]
    kept: list[Occurrence] = [min(viable_first if viable_first else pool, key=lambda o: o.starts_at_utc)]
    rest = [o for o in pool[1:] if o.starts_at_utc > kept[-1].starts_at_utc]
    while rest:
        last = kept[-1]
        last_ts = last.starts_at_utc
        future = [o for o in rest if o.starts_at_utc > last_ts]
        if not future:
            break
        if mode is PublicRecurrenceMode.once_per_month:
            ideal = _add_local_calendar_months(last_ts, 1, tz)
            months_span = 2
            window: list[Occurrence] = []
            while months_span <= 12:
                win_end = _add_local_calendar_months(last_ts, months_span, tz)
                cand = [o for o in future if o.starts_at_utc <= win_end]
                if not cand:
                    window = [future[0]]
                    break
                if any(_local_calendar_month_delta(last, o, tz) >= 1 for o in cand):
                    window = cand
                    break
                window = cand
                if cand == future:
                    break
                months_span += 1
            if not window:
                window = [future[0]]
            pick = _pick_monthly_tempo_occurrence(
                window,
                last_occ=last,
                ideal_utc=ideal,
                tz=tz,
                players=players,
                availability=availability,
                policy=policy,
                opt_outs=opt_outs,
            )
        else:
            period = 7 if mode is PublicRecurrenceMode.weekly else 14
            ideal = _add_local_calendar_days(last_ts, period, tz)
            win_end = _add_local_calendar_days(last_ts, 2 * period, tz)
            window = [o for o in future if o.starts_at_utc <= win_end]
            if not window:
                window = [future[0]]
            pick = _pick_rhythm_occurrence(
                window,
                last_occ=last,
                ideal_utc=ideal,
                period_days=period,
                tz=tz,
                players=players,
                availability=availability,
                policy=policy,
                opt_outs=opt_outs,
            )
        kept.append(pick)
        rest = [o for o in future if o.starts_at_utc > pick.starts_at_utc]
    return kept


def filter_occurrences_for_public_display(
    occurrences: Sequence[Occurrence],
    slots: Sequence[Slot],
    *,
    tz: ZoneInfo,
    players: Sequence[Player],
    availability: Mapping[tuple[int, int], AvailabilityStatus],
    policy: ConsensusPolicy,
    opt_outs: set[tuple[int, int, datetime]],
    public_recurrence_mode: PublicRecurrenceMode,
) -> list[Occurrence]:
    """Thin recurring rows for public / ICS using the campaign tempo chain."""
    by_id = {s.id: s for s in slots if s.id is not None}
    mode = public_recurrence_mode
    if not isinstance(mode, PublicRecurrenceMode):
        try:
            mode = PublicRecurrenceMode(str(mode))
        except ValueError:
            mode = PublicRecurrenceMode.weekly

    recurring_all: list[Occurrence] = []
    adhoc_out: list[Occurrence] = []

    for occ in sorted(occurrences, key=lambda o: o.starts_at_utc):
        slot = by_id.get(occ.slot_id)
        if slot is None or slot.kind is not SlotKind.recurring:
            adhoc_out.append(occ)
            continue
        recurring_all.append(occ)

    spaced_recurring = _apply_public_tempo_chain(
        recurring_all,
        tz=tz,
        mode=mode,
        players=players,
        availability=availability,
        policy=policy,
        opt_outs=opt_outs,
    )
    return sorted(spaced_recurring + adhoc_out, key=lambda o: o.starts_at_utc)

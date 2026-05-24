"""Admin times table: recurring Mon→Sun by start time, then one-offs by UTC start."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.models import Campaign, Slot, SlotKind
from app.routes import admin as admin_routes
from app.security import hash_token
from app.services.timeutil import ensure_utc


def test_slots_ordered_for_admin_weekday_then_time_then_adhoc(engine):
    with Session(engine) as s:
        c = Campaign(
            public_id="a" * 32,
            name="Order",
            timezone="UTC",
            admin_secret_hash=hash_token("adm"),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id
        assert cid is not None

        t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        t1 = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
        # Insert out of desired display order (Wed, Mon pm, Mon am, Fri, adhoc late, adhoc early).
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.recurring,
                weekday=2,
                start_local="18:00",
                duration_hours=2.0,
            )
        )
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.recurring,
                weekday=0,
                start_local="14:00",
                duration_hours=2.0,
            )
        )
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.recurring,
                weekday=0,
                start_local="10:00",
                duration_hours=2.0,
            )
        )
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.recurring,
                weekday=4,
                start_local="09:00",
                duration_hours=2.0,
            )
        )
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.adhoc,
                duration_hours=2.0,
                starts_at_utc=t1,
                ends_at_utc=t1 + timedelta(hours=2),
            )
        )
        s.add(
            Slot(
                campaign_id=cid,
                kind=SlotKind.adhoc,
                duration_hours=2.0,
                starts_at_utc=t0,
                ends_at_utc=t0 + timedelta(hours=2),
            )
        )
        s.commit()

        ordered = admin_routes._slots_ordered_for_admin(s, cid)  # noqa: SLF001
        assert [sl.weekday for sl in ordered[:4]] == [0, 0, 2, 4]
        assert [sl.start_local for sl in ordered[:4]] == ["10:00", "14:00", "18:00", "09:00"]
        assert [sl.kind for sl in ordered[4:]] == [SlotKind.adhoc, SlotKind.adhoc]
        assert ensure_utc(ordered[4].starts_at_utc) == t0
        assert ensure_utc(ordered[5].starts_at_utc) == t1

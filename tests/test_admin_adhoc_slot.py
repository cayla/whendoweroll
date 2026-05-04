"""Admin one-off slot: date + start time + duration (hours) in campaign timezone."""

from __future__ import annotations

import re
from datetime import date

from sqlmodel import Session, select
from zoneinfo import ZoneInfo

from app.display_time import ensure_utc
from app.models import Slot, SlotKind


def _new_campaign(client):
    r = client.post(
        "/",
        data={
            "name": "Oneoff",
            "timezone": "America/New_York",
            "player_names": "",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2)


def test_admin_oneoff_same_calendar_day(client, engine):
    public_id, secret = _new_campaign(client)
    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "adhoc",
            "label": "bash",
            "adhoc_date": "2026-07-04",
            "adhoc_start_time": "14:00",
            "duration_hours": "4.5",
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        slot = s.exec(select(Slot).where(Slot.kind == SlotKind.adhoc)).first()
    assert slot is not None
    assert slot.label == "bash"
    assert slot.duration_hours == 4.5
    ny = ZoneInfo("America/New_York")
    a = ensure_utc(slot.starts_at_utc).astimezone(ny)
    b = ensure_utc(slot.ends_at_utc).astimezone(ny)
    assert a.date() == date(2026, 7, 4)
    assert (a.hour, a.minute) == (14, 0)
    assert b.date() == date(2026, 7, 4)
    assert (b.hour, b.minute) == (18, 30)


def test_admin_oneoff_duration_crosses_midnight(client, engine):
    public_id, secret = _new_campaign(client)
    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "adhoc",
            "label": "late",
            "adhoc_date": "2026-07-04",
            "adhoc_start_time": "22:00",
            "duration_hours": "4",
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        slot = s.exec(select(Slot).where(Slot.kind == SlotKind.adhoc)).first()
    assert slot is not None
    assert slot.duration_hours == 4.0
    ny = ZoneInfo("America/New_York")
    a = ensure_utc(slot.starts_at_utc).astimezone(ny)
    b = ensure_utc(slot.ends_at_utc).astimezone(ny)
    assert a.date() == date(2026, 7, 4)
    assert (a.hour, a.minute) == (22, 0)
    assert b.date() == date(2026, 7, 5)
    assert (b.hour, b.minute) == (2, 0)

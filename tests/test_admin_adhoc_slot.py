"""Admin one-off slot: date + start time + duration (hours) in campaign timezone."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models import Slot, SlotKind
from app.services.timeutil import ensure_utc
from tests.helpers import create_campaign_via_form


def test_admin_oneoff_same_calendar_day(client, engine):
    created = create_campaign_via_form(
        client, name="Oneoff", timezone="America/New_York", player_names="", horizon_weeks=4
    )
    public_id, secret = created.public_id, created.admin_secret
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
    created = create_campaign_via_form(
        client, name="Oneoff", timezone="America/New_York", player_names="", horizon_weeks=4
    )
    public_id, secret = created.public_id, created.admin_secret
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


def test_admin_oneoff_rejects_past_start(client):
    created = create_campaign_via_form(
        client, name="Oneoff", timezone="America/New_York", player_names="", horizon_weeks=4
    )
    public_id, secret = created.public_id, created.admin_secret
    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "adhoc",
            "adhoc_date": "2001-01-01",
            "adhoc_start_time": "10:00",
            "duration_hours": "2",
        },
    )
    assert r.status_code == 400


def test_admin_recurring_times_display_as_12_hour(client):
    created = create_campaign_via_form(
        client, name="Oneoff", timezone="America/New_York", player_names="", horizon_weeks=4
    )
    public_id, secret = created.public_id, created.admin_secret
    r = client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={
            "kind": "recurring",
            "weekday": "1",
            "start_local": "14:05",
            "duration_hours": "3",
        },
    )

    assert r.status_code == 200
    assert "Tue 2:05 PM" in r.text
    assert "Tue 14:05" not in r.text

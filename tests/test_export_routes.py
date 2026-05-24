"""Admin export endpoints require the capability secret."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import Availability, AvailabilityStatus, Campaign, Player, Slot, SlotKind
from app.services.campaign_export import campaign_export_download_filename
from tests.helpers import create_campaign_via_form


def _create(client, names: list[str], *, horizon_weeks: int = 12) -> tuple[str, str, str]:
    created = create_campaign_via_form(
        client, name="ICS", timezone="UTC", player_names=names, horizon_weeks=horizon_weeks
    )
    return created.public_id, created.admin_secret, created.response_text


def _seed_adhoc_slot_with_availability(
    engine,
    *,
    public_id: str,
    days_ahead: int,
    statuses: dict[str, AvailabilityStatus],
) -> None:
    """Add an ad-hoc slot ``days_ahead`` from now and stamp each named player's
    response. Players not in ``statuses`` are left unset (= missing).
    """
    start = datetime.now(UTC) + timedelta(days=days_ahead)
    end = start + timedelta(hours=3)
    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        slot = Slot(
            campaign_id=campaign.id,
            kind=SlotKind.adhoc,
            label=f"Day +{days_ahead}",
            duration_hours=3.0,
            starts_at_utc=start,
            ends_at_utc=end,
        )
        s.add(slot)
        s.commit()
        s.refresh(slot)
        players = s.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
        by_name = {p.display_name: p for p in players}
        for name, status in statuses.items():
            s.add(Availability(player_id=by_name[name].id, slot_id=slot.id, status=status))
        s.commit()


def test_export_json_requires_admin_secret(client):
    created = create_campaign_via_form(client, name="Export Test", timezone="UTC", player_names="A", horizon_weeks=2)
    public_id, secret = created.public_id, created.admin_secret
    ok = client.get(f"/c/{public_id}/admin/{secret}/export")
    assert ok.status_code == 200
    cd = ok.headers.get("content-disposition", "")
    assert re.search(
        r'attachment;\s*filename="whendoweroll-export-test-\d{8}\.json"',
        cd,
        re.IGNORECASE,
    ), cd
    data = json.loads(ok.text)
    assert data["campaign"]["public_id"] == public_id
    assert "availability" in data
    assert "occurrence_opt_outs" in data
    bad = client.get(f"/c/{public_id}/admin/wrong-secret/export")
    assert bad.status_code == 404

    legacy = client.get(f"/c/{public_id}/admin/{secret}/export.json")
    assert legacy.status_code == 200
    assert json.loads(legacy.text)["campaign"]["public_id"] == public_id


def test_consensus_ics_is_public_no_secret_required(client):
    public_id, _secret, _ = _create(client, [])
    ok = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/calendar")
    assert b"VCALENDAR" in ok.content
    body = ok.content.decode("utf-8")
    assert f"UID:{public_id}-placeholder@whendoweroll.com" in body
    assert "STATUS:CANCELLED" in body
    assert "waiting for consensus" in body


def test_consensus_ics_admin_path_removed(client):
    """The old admin-secret URL is gone — only the public path serves the feed."""
    public_id, secret, _ = _create(client, [])
    r = client.get(f"/c/{public_id}/admin/{secret}/calendar-consensus.ics")
    assert r.status_code == 404


def test_consensus_ics_unknown_campaign_returns_404(client):
    r = client.get("/c/deadbeef/calendar-consensus.ics")
    assert r.status_code == 404


def test_consensus_ics_marks_near_consensus_with_missing_prefix(client, engine):
    public_id, _secret, _ = _create(client, ["Alice", "Bob"])
    _seed_adhoc_slot_with_availability(
        engine,
        public_id=public_id,
        days_ahead=3,
        statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.no},
    )
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    summary = next(line for line in body.splitlines() if line.startswith("SUMMARY:"))
    assert summary.startswith("SUMMARY:[missing: Bob]")
    assert "everyone available" not in summary


def test_consensus_ics_with_real_events_has_no_placeholder(client, engine):
    public_id, _secret, _ = _create(client, ["Alice", "Bob"])
    _seed_adhoc_slot_with_availability(
        engine,
        public_id=public_id,
        days_ahead=5,
        statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.yes},
    )
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert "-placeholder@" not in body


def test_consensus_ics_full_consensus_has_no_missing_prefix(client, engine):
    public_id, _secret, _ = _create(client, ["Alice", "Bob"])
    _seed_adhoc_slot_with_availability(
        engine,
        public_id=public_id,
        days_ahead=5,
        statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.yes},
    )
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    summary = next(line for line in body.splitlines() if line.startswith("SUMMARY:"))
    assert "[missing:" not in summary
    assert "everyone available" in summary


def test_consensus_ics_skips_occurrences_with_too_many_missing(client, engine):
    """Two missing players exceeds the all-but-one bound — the slot stays out of the feed."""
    public_id, _secret, _ = _create(client, ["Alice", "Bob", "Carol"])
    _seed_adhoc_slot_with_availability(
        engine,
        public_id=public_id,
        days_ahead=4,
        statuses={"Alice": AvailabilityStatus.yes},
    )
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert "everyone available" not in body
    assert f"UID:{public_id}-placeholder@whendoweroll.com" in body


def test_consensus_ics_link_appears_on_admin_public_and_player_pages(client):
    public_id, secret, page_html = _create(client, ["Alice"])
    expected_link = f"/c/{public_id}/calendar-consensus.ics"

    admin = client.get(f"/c/{public_id}/admin/{secret}")
    assert admin.status_code == 200
    assert expected_link in admin.text

    public = client.get(f"/c/{public_id}")
    assert public.status_code == 200
    assert expected_link in public.text

    m = re.search(rf"/c/{public_id}/p/([\w\-]+)", page_html)
    assert m, "expected a player URL on the created-campaign page"
    token = m.group(1)
    player_page = client.get(f"/c/{public_id}/p/{token}")
    assert player_page.status_code == 200
    assert expected_link in player_page.text
    for html in (admin.text, public.text, player_page.text):
        assert "Subscribe to Calendar" in html
        assert "Alternately, download the .ics file" in html
        assert "Download Calendar (ics)" not in html


def test_player_calendar_ics_route_removed(client):
    public_id, _secret, page_html = _create(client, ["Alice"])
    m = re.search(rf"/c/{public_id}/p/([\w\-]+)", page_html)
    assert m
    token = m.group(1)
    r = client.get(f"/c/{public_id}/p/{token}/calendar.ics")
    assert r.status_code == 404


def test_campaign_export_download_filename_uses_utc_date_and_slug():
    c = Campaign(public_id="abc", name="My Friday Game", timezone="UTC", admin_secret_hash="x")
    fixed = datetime(2026, 5, 10, 23, tzinfo=UTC)
    assert campaign_export_download_filename(c, as_of=fixed) == "whendoweroll-my-friday-game-20260510.json"


def test_campaign_export_download_filename_blank_name():
    c = Campaign(public_id="abc", name="   ", timezone="UTC", admin_secret_hash="x")
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    assert campaign_export_download_filename(c, as_of=fixed) == "whendoweroll-campaign-20260101.json"

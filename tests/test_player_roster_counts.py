"""Player UI: slot-table roster line + (x/y can make it) on exception rows."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import AvailabilityStatus, Campaign, Player, Slot, SlotKind
from app.services.availability import roster_can_make_occurrence
from app.services.timeutil import normalize_occurrence_start


def test_roster_can_make_skips_opt_outs():
    a = Player(id=1, campaign_id=1, display_name="A", token_hash="ta", sort_order=0)
    b = Player(id=2, campaign_id=1, display_name="B", token_hash="tb", sort_order=1)
    av = {(1, 5): AvailabilityStatus.yes, (2, 5): AvailabilityStatus.yes}
    start = datetime(2030, 6, 7, 22, 0, tzinfo=UTC)
    key = normalize_occurrence_start(start)
    opt = {(1, 5, key)}
    can, denom = roster_can_make_occurrence(av, [a, b], opt, slot_id=5, starts_at_utc=start)
    assert (can, denom) == (1, 2)


def test_roster_denominator_excludes_standing_never():
    a = Player(id=1, campaign_id=1, display_name="A", token_hash="ta", sort_order=0)
    b = Player(id=2, campaign_id=1, display_name="B", token_hash="tb", sort_order=1)
    c = Player(id=3, campaign_id=1, display_name="C", token_hash="tc", sort_order=2)
    av = {
        (1, 5): AvailabilityStatus.yes,
        (2, 5): AvailabilityStatus.yes,
        (3, 5): AvailabilityStatus.no,
    }
    start = datetime(2030, 6, 7, 22, 0, tzinfo=UTC)
    can, denom = roster_can_make_occurrence(av, [a, b, c], set(), slot_id=5, starts_at_utc=start)
    assert (can, denom) == (2, 2)


def test_roster_all_never_is_zero_of_zero():
    a = Player(id=1, campaign_id=1, display_name="A", token_hash="ta", sort_order=0)
    b = Player(id=2, campaign_id=1, display_name="B", token_hash="tb", sort_order=1)
    av = {(1, 5): AvailabilityStatus.no, (2, 5): AvailabilityStatus.no}
    start = datetime(2030, 6, 7, 22, 0, tzinfo=UTC)
    can, denom = roster_can_make_occurrence(av, [a, b], set(), slot_id=5, starts_at_utc=start)
    assert (can, denom) == (0, 0)


def test_player_slot_row_shows_can_make_pair(client):
    r = client.post(
        "/",
        data={
            "name": "Counts",
            "timezone": "America/New_York",
            "player_names": "Alice\nBob",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    raw = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    tokens = list(dict.fromkeys(raw))
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "yes"})
    page = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert page.status_code == 200
    assert "(1/2 indicated yes for this time)" in page.text

    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    page2 = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert "(2/2 indicated yes for this time)" in page2.text
    assert "(2/2 can make it)" in page2.text


def test_three_players_all_yes_shows_three_of_three(client):
    public_id, _, tokens = _three_player_campaign_with_slot(client)
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "yes"})
    client.post(f"/c/{public_id}/p/{tokens[2]}/availability/1", data={"status": "yes"})
    page = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert page.status_code == 200
    assert "(2/3 indicated yes for this time)" in page.text
    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    page2 = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert "(3/3 indicated yes for this time)" in page2.text
    assert "(3/3 can make it)" in page2.text


def _three_player_campaign_with_slot(client) -> tuple[str, str, list[str]]:
    r = client.post(
        "/",
        data={
            "name": "Trio",
            "timezone": "America/New_York",
            "player_names": "Alice\nBob\nCayla",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    raw = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    tokens = list(dict.fromkeys(raw))
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    return public_id, secret, tokens


def test_player_cannot_change_availability_on_ended_oneoff(client, engine):
    r = client.post(
        "/",
        data={
            "name": "PastOneoff",
            "timezone": "America/New_York",
            "player_names": "Solo",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, _secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    token = re.search(r"/c/" + public_id + r"/p/([\w\-]+)", r.text).group(1)

    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == public_id)).first()
        assert campaign is not None
        cid = campaign.id
        past_start = datetime(2019, 6, 1, 16, 0, tzinfo=UTC)
        slot = Slot(
            campaign_id=cid,
            kind=SlotKind.adhoc,
            duration_hours=1.0,
            starts_at_utc=past_start,
            ends_at_utc=past_start + timedelta(hours=1),
        )
        s.add(slot)
        s.commit()
        s.refresh(slot)
        sid = slot.id
    assert sid is not None

    resp = client.post(
        f"/c/{public_id}/p/{token}/availability/{sid}",
        data={"status": "yes"},
    )
    assert resp.status_code == 400


def test_public_windows_table_hides_all_never_shows_buckets(client):
    r = client.post(
        "/",
        data={
            "name": "NeverDenom",
            "timezone": "America/New_York",
            "player_names": "A\nB\nC",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    raw = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    tokens = list(dict.fromkeys(raw))
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    for t in tokens:
        client.post(f"/c/{public_id}/p/{t}/availability/1", data={"status": "no"})
    pub = client.get(f"/c/{public_id}")
    assert pub.status_code == 200
    assert "public-windows-table" not in pub.text
    assert "No upcoming windows listed" in pub.text

    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "yes"})
    pub2 = client.get(f"/c/{public_id}")
    assert pub2.status_code == 200
    assert "public-windows-table" in pub2.text
    assert "Can make" in pub2.text
    assert "No answer" in pub2.text
    assert "public-window-row-near" in pub2.text

    client.post(f"/c/{public_id}/p/{tokens[2]}/availability/1", data={"status": "yes"})
    pub3 = client.get(f"/c/{public_id}")
    assert pub3.status_code == 200
    assert "public-window-row-full" in pub3.text

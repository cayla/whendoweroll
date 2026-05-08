"""Player UI: slot-table roster line + (x/y can make it) on exception rows."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.models import AvailabilityStatus, Player
from app.services.availability import roster_can_make_occurrence
from app.services.timeutil import normalize_occurrence_start


def test_roster_can_make_skips_opt_outs():
    a = Player(id=1, campaign_id=1, display_name="A", token_hash="ta", sort_order=0)
    b = Player(id=2, campaign_id=1, display_name="B", token_hash="tb", sort_order=1)
    av = {(1, 5): AvailabilityStatus.yes, (2, 5): AvailabilityStatus.yes}
    start = datetime(2030, 6, 7, 22, 0, tzinfo=UTC)
    key = normalize_occurrence_start(start)
    opt = {(1, 5, key)}
    can, n = roster_can_make_occurrence(av, [a, b], opt, slot_id=5, starts_at_utc=start)
    assert (can, n) == (1, 2)


def test_player_slot_row_shows_can_make_pair(client):
    r = client.post(
        "/",
        data={
            "name": "Counts",
            "timezone": "America/New_York",
            "player_names": "Tav\nKarlach",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    tokens = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "yes"})
    page = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert page.status_code == 200
    assert "(1/2 indicated this time generally works)" in page.text

    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    page2 = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert "(2/2 indicated this time generally works)" in page2.text
    assert "(2/2 can make it)" in page2.text


def test_three_players_all_yes_shows_three_of_three(client):
    public_id, _, tokens = _three_player_campaign_with_slot(client)
    client.post(f"/c/{public_id}/p/{tokens[1]}/availability/1", data={"status": "yes"})
    client.post(f"/c/{public_id}/p/{tokens[2]}/availability/1", data={"status": "yes"})
    page = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert page.status_code == 200
    assert "(2/3 indicated this time generally works)" in page.text
    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})
    page2 = client.get(f"/c/{public_id}/p/{tokens[0]}")
    assert "(3/3 indicated this time generally works)" in page2.text
    assert "(3/3 can make it)" in page2.text


def _three_player_campaign_with_slot(client) -> tuple[str, str, list[str]]:
    r = client.post(
        "/",
        data={
            "name": "Trio",
            "timezone": "America/New_York",
            "player_names": "A\nB\nC",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    tokens = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    client.post(
        f"/c/{public_id}/admin/{secret}/slots",
        data={"kind": "recurring", "weekday": "4", "start_local": "18:00", "duration_hours": "3"},
    )
    return public_id, secret, tokens

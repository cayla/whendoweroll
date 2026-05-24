"""Recurring exception rows only appear when the player said yes to that slot."""

from __future__ import annotations

from tests.helpers import create_campaign_with_recurring_slot


def _rogue_with_friday_slot(client):
    return create_campaign_with_recurring_slot(
        client,
        name="Vis",
        timezone="America/New_York",
        player_names="Rogue",
        horizon_weeks=4,
        label="Friday",
    )


def test_no_per_date_rows_until_standing_yes_then_cleared_on_no(client):
    created = _rogue_with_friday_slot(client)
    public_id = created.public_id
    player_token = created.player_tokens[0]

    p0 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p0.status_code == 200
    assert b"Can't make it" not in p0.content

    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})
    p1 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p1.status_code == 200
    assert b"Can't make it" in p1.content

    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "no"})
    p2 = client.get(f"/c/{public_id}/p/{player_token}")
    assert p2.status_code == 200
    assert b"Can't make it" not in p2.content


def test_availability_post_htmx_refreshes_exceptions_contract(client):
    """Row swap + HX-Trigger + GET fragment (Safari/Firefox-friendly; no multi-root OOB)."""
    created = _rogue_with_friday_slot(client)
    public_id = created.public_id
    player_token = created.player_tokens[0]

    post = client.post(
        f"/c/{public_id}/p/{player_token}/availability/1",
        data={"status": "yes"},
        headers={"HX-Request": "true"},
    )
    assert post.status_code == 200
    assert post.headers.get("HX-Trigger") == "refreshExceptions"
    assert b'id="slot-row-1"' in post.content
    frag = client.get(f"/c/{public_id}/p/{player_token}/_recurring-exceptions")
    assert frag.status_code == 200
    assert b"Can't make it" in frag.content

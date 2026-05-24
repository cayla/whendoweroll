"""Admin campaign deletion removes all URLs for that campaign."""

from __future__ import annotations

from tests.helpers import create_campaign_via_form


def test_delete_campaign_returns_303_to_home_and_invalidates_urls(client):
    created = create_campaign_via_form(
        client, name="Gone Soon", timezone="America/New_York", player_names="A\nB", horizon_weeks=4
    )
    public_id, secret, tokens = created.public_id, created.admin_secret, created.player_tokens
    assert len(tokens) == 2
    r = client.post(f"/c/{public_id}/admin/{secret}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/"

    assert client.get(f"/c/{public_id}/admin/{secret}").status_code == 404
    assert client.get(f"/c/{public_id}").status_code == 404
    assert client.get(f"/c/{public_id}/p/{tokens[0]}").status_code == 404

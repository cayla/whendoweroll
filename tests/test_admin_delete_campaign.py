"""Admin campaign deletion removes all URLs for that campaign."""

from __future__ import annotations

import re


def _create_campaign(client):
    r = client.post(
        "/",
        data={
            "name": "Gone Soon",
            "timezone": "America/New_York",
            "player_names": "A\nB",
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    public_id, secret = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text).groups()
    tokens = re.findall(r"/c/" + public_id + r"/p/([\w\-]+)", r.text)
    assert len(tokens) == 2
    return public_id, secret, tokens


def test_delete_campaign_returns_303_to_home_and_invalidates_urls(client):
    public_id, secret, tokens = _create_campaign(client)
    r = client.post(f"/c/{public_id}/admin/{secret}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/"

    assert client.get(f"/c/{public_id}/admin/{secret}").status_code == 404
    assert client.get(f"/c/{public_id}").status_code == 404
    assert client.get(f"/c/{public_id}/p/{tokens[0]}").status_code == 404

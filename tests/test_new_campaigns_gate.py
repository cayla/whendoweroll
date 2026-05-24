"""Environment gate for creating campaigns on the home page."""

from __future__ import annotations

from tests.helpers import post_create_campaign


def test_post_allowed_by_default(client):
    r = post_create_campaign(client, name="Gate Test", timezone="UTC", player_names="", horizon_weeks=2)
    assert r.status_code == 200
    assert "admin" in r.text


def test_post_blocked_when_env_set(client, monkeypatch):
    monkeypatch.setenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "1")
    r = post_create_campaign(client, name="Nope", timezone="UTC", player_names="", horizon_weeks=2)
    assert r.status_code == 403
    assert "disabled" in r.text.lower()


def test_get_shows_banner_when_env_set(client, monkeypatch):
    monkeypatch.setenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "true")
    r = client.get("/")
    assert r.status_code == 200
    assert "disabled" in r.text.lower()
    assert 'name="name"' not in r.text

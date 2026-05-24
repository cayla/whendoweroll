"""Super admin UI: login, list/delete campaigns, new-campaign override."""

from __future__ import annotations

from app import settings as settings_module
from app.super_admin_auth import SESSION_COOKIE_NAME
from tests.helpers import create_campaign_via_form, post_create_campaign


def _login(client):
    r = client.post(
        "/internal/super-admin/login",
        data={"password": "test-super-pass"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert SESSION_COOKIE_NAME in r.cookies


def test_super_admin_login_bad_password(client):
    r = client.post(
        "/internal/super-admin/login",
        data={"password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Incorrect" in r.text


def test_super_admin_list_and_delete_campaign(client):
    created = create_campaign_via_form(client, name="Listed", timezone="UTC", player_names="", horizon_weeks=2)

    _login(client)
    r = client.get("/internal/super-admin")
    assert r.status_code == 200
    assert "Listed" in r.text
    assert created.public_id in r.text
    assert " AM" in r.text or " PM" in r.text

    d = client.post(
        f"/internal/super-admin/campaigns/{created.public_id}/delete",
        follow_redirects=False,
    )
    assert d.status_code == 303
    assert client.get(f"/c/{created.public_id}").status_code == 404


def test_super_admin_delete_requires_session(client):
    created = create_campaign_via_form(client, name="Guarded", timezone="UTC", player_names="", horizon_weeks=2)

    r = client.post(f"/internal/super-admin/campaigns/{created.public_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/c/{created.public_id}").status_code == 200


def test_super_admin_new_campaigns_override(client, monkeypatch):
    monkeypatch.delenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", raising=False)
    _login(client)

    client.post(
        "/internal/super-admin/new-campaigns-override",
        data={"mode": "block"},
        follow_redirects=True,
    )
    assert settings_module.new_campaigns_disabled() is True
    blocked = post_create_campaign(client, name="Nope", timezone="UTC", player_names="", horizon_weeks=2)
    assert blocked.status_code == 403

    client.post(
        "/internal/super-admin/new-campaigns-override",
        data={"mode": "allow"},
        follow_redirects=True,
    )
    assert settings_module.new_campaigns_disabled() is False
    ok = post_create_campaign(client, name="Yes", timezone="UTC", player_names="", horizon_weeks=2)
    assert ok.status_code == 200

    monkeypatch.setenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "1")
    client.post(
        "/internal/super-admin/new-campaigns-override",
        data={"mode": "env"},
        follow_redirects=True,
    )
    assert settings_module.new_campaigns_override() is None
    assert settings_module.new_campaigns_disabled() is True

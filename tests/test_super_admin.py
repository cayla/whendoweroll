"""Super admin UI: login, list/delete campaigns, new-campaign override, spam cleanup."""

from __future__ import annotations

from app import settings as settings_module
from app.super_admin_auth import SESSION_COOKIE_NAME
from tests.helpers import add_recurring_slot, create_campaign_via_form, post_create_campaign

_SPAM_PITCH = (
    "Hello whendoweroll.com, I was reviewing your website and noticed a few SEO "
    "and website performance issues that may be affecting your Google rankings."
)
assert len(_SPAM_PITCH) > 80


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


def test_super_admin_spam_section_lists_pitch_campaigns_only(client):
    spam = create_campaign_via_form(
        client,
        name="Wilson Web",
        timezone="UTC",
        player_names=[_SPAM_PITCH, "Best regards,"],
        horizon_weeks=2,
    )
    short_empty = create_campaign_via_form(
        client,
        name="Fresh Legit",
        timezone="UTC",
        player_names=["Alice", "Bob"],
        horizon_weeks=2,
    )
    slotted = create_campaign_via_form(
        client,
        name="Real Table",
        timezone="UTC",
        player_names=[_SPAM_PITCH],
        horizon_weeks=2,
    )
    add_recurring_slot(client, public_id=slotted.public_id, admin_secret=slotted.admin_secret)

    _login(client)
    r = client.get("/internal/super-admin")
    assert r.status_code == 200
    assert "Likely spam" in r.text
    assert "Wilson Web" in r.text
    assert spam.public_id in r.text
    assert _SPAM_PITCH[:40] in r.text
    spam_block = r.text.split("Likely spam", 1)[1].split(">Campaigns<", 1)[0]
    assert short_empty.public_id not in spam_block
    assert slotted.public_id not in spam_block
    assert "Fresh Legit" not in spam_block
    assert "Real Table" not in spam_block


def test_super_admin_cleanup_spam_deletes_candidates_only(client):
    spam = create_campaign_via_form(
        client,
        name="Ken Karp",
        timezone="UTC",
        player_names=[_SPAM_PITCH],
        horizon_weeks=2,
    )
    short_empty = create_campaign_via_form(
        client,
        name="Keep Me",
        timezone="UTC",
        player_names=["Sam"],
        horizon_weeks=2,
    )
    slotted = create_campaign_via_form(
        client,
        name="Keep Slotted",
        timezone="UTC",
        player_names=["Jamie"],
        horizon_weeks=2,
    )
    add_recurring_slot(client, public_id=slotted.public_id, admin_secret=slotted.admin_secret)

    _login(client)
    d = client.post("/internal/super-admin/cleanup-spam", follow_redirects=False)
    assert d.status_code == 303

    assert client.get(f"/c/{spam.public_id}").status_code == 404
    assert client.get(f"/c/{short_empty.public_id}").status_code == 200
    assert client.get(f"/c/{slotted.public_id}").status_code == 200

    r = client.get("/internal/super-admin")
    assert "Likely spam" not in r.text
    assert "Keep Me" in r.text
    assert "Keep Slotted" in r.text


def test_super_admin_cleanup_spam_requires_session(client):
    spam = create_campaign_via_form(
        client,
        name="Blocked Spam",
        timezone="UTC",
        player_names=[_SPAM_PITCH],
        horizon_weeks=2,
    )
    r = client.post("/internal/super-admin/cleanup-spam", follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/c/{spam.public_id}").status_code == 200

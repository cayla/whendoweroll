"""Admin roster CRUD: add/regenerate/delete players and delete slots."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Availability, Campaign, Player, Slot
from app.security import hash_token
from tests.helpers import (
    admin_url,
    create_campaign_via_form,
    create_campaign_with_recurring_slot,
    player_token_from_html,
)


def test_admin_home_ok_with_secret(client):
    created = create_campaign_via_form(client, name="Admin Home", player_names="Alice")
    r = client.get(admin_url(created.public_id, created.admin_secret))
    assert r.status_code == 200
    assert "Admin Home" in r.text
    assert "Alice" in r.text


def test_add_player_creates_row_and_returns_private_link(client, engine):
    created = create_campaign_via_form(client, name="Roster", timezone="UTC", player_names="", horizon_weeks=4)
    r = client.post(
        admin_url(created.public_id, created.admin_secret, "/players"),
        data={"display_name": "Newcomer"},
    )
    assert r.status_code == 200
    assert "Newcomer" in r.text
    assert "private link" in r.text.lower()
    token = player_token_from_html(r.text, created.public_id)
    assert client.get(f"/c/{created.public_id}/p/{token}").status_code == 200

    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == created.public_id)).one()
        players = s.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
    assert len(players) == 1
    assert players[0].display_name == "Newcomer"


def test_add_player_empty_name_returns_400(client):
    created = create_campaign_via_form(client, player_names="")
    r = client.post(
        admin_url(created.public_id, created.admin_secret, "/players"),
        data={"display_name": "   "},
    )
    assert r.status_code == 400


def test_regenerate_player_token_invalidates_old_link(client, engine):
    created = create_campaign_via_form(client, player_names="Alice")
    old_token = created.player_tokens[0]
    assert client.get(f"/c/{created.public_id}/p/{old_token}").status_code == 200

    with Session(engine) as s:
        player = s.exec(select(Player)).one()
        player_id = player.id
    assert player_id is not None

    r = client.post(
        admin_url(created.public_id, created.admin_secret, f"/players/{player_id}/regenerate"),
    )
    assert r.status_code == 200
    new_token = player_token_from_html(r.text, created.public_id)
    assert new_token != old_token
    assert client.get(f"/c/{created.public_id}/p/{old_token}").status_code == 404
    assert client.get(f"/c/{created.public_id}/p/{new_token}").status_code == 200

    with Session(engine) as s:
        player = s.get(Player, player_id)
        assert player is not None
        assert player.token_hash == hash_token(new_token)


def test_regenerate_player_wrong_campaign_returns_404(client, engine):
    a = create_campaign_via_form(client, name="A", player_names="Alice")
    b = create_campaign_via_form(client, name="B", player_names="Bob")
    with Session(engine) as s:
        campaign_a = s.exec(select(Campaign).where(Campaign.public_id == a.public_id)).one()
        alice = s.exec(select(Player).where(Player.campaign_id == campaign_a.id, Player.display_name == "Alice")).one()
        alice_id = alice.id
    assert alice_id is not None

    r = client.post(admin_url(b.public_id, b.admin_secret, f"/players/{alice_id}/regenerate"))
    assert r.status_code == 404
    assert client.get(f"/c/{a.public_id}/p/{a.player_tokens[0]}").status_code == 200


def test_delete_player_removes_data_and_invalidates_link(client, engine):
    created = create_campaign_with_recurring_slot(client, name="Trim", player_names=["Alice", "Bob"], horizon_weeks=4)
    public_id, secret, tokens = created.public_id, created.admin_secret, created.player_tokens
    client.post(f"/c/{public_id}/p/{tokens[0]}/availability/1", data={"status": "yes"})

    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        alice = s.exec(select(Player).where(Player.campaign_id == campaign.id, Player.display_name == "Alice")).one()
        alice_id = alice.id
    assert alice_id is not None

    r = client.post(admin_url(public_id, secret, f"/players/{alice_id}/delete"))
    assert r.status_code == 200
    assert "Alice was removed" in r.text
    assert client.get(f"/c/{public_id}/p/{tokens[0]}").status_code == 404

    with Session(engine) as s:
        assert s.get(Player, alice_id) is None
        avails = s.exec(select(Availability).where(Availability.player_id == alice_id)).all()
        assert avails == []
        remaining = s.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
    assert len(remaining) == 1
    assert remaining[0].display_name == "Bob"


def test_delete_player_wrong_campaign_returns_404(client, engine):
    a = create_campaign_via_form(client, name="A", player_names="Alice")
    b = create_campaign_via_form(client, name="B", player_names="Bob")
    with Session(engine) as s:
        campaign_a = s.exec(select(Campaign).where(Campaign.public_id == a.public_id)).one()
        alice = s.exec(select(Player).where(Player.campaign_id == campaign_a.id, Player.display_name == "Alice")).one()
        alice_id = alice.id
    assert alice_id is not None

    r = client.post(admin_url(b.public_id, b.admin_secret, f"/players/{alice_id}/delete"))
    assert r.status_code == 404
    assert client.get(f"/c/{a.public_id}/p/{a.player_tokens[0]}").status_code == 200


def test_delete_slot_removes_slot_and_availability(client, engine):
    created = create_campaign_with_recurring_slot(client, player_names=["Alice"])
    public_id, secret, token = created.public_id, created.admin_secret, created.player_tokens[0]
    client.post(f"/c/{public_id}/p/{token}/availability/1", data={"status": "yes"})

    with Session(engine) as s:
        slot = s.exec(select(Slot)).one()
        slot_id = slot.id
    assert slot_id is not None

    r = client.post(
        admin_url(public_id, secret, f"/slots/{slot_id}/delete"),
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Time removed." in r.text
    assert "admin-slots-roster" in r.text

    with Session(engine) as s:
        assert s.get(Slot, slot_id) is None
        avails = s.exec(select(Availability).where(Availability.slot_id == slot_id)).all()
        assert avails == []


def test_delete_slot_without_htmx_redirects_to_admin(client, engine):
    created = create_campaign_with_recurring_slot(client, player_names=[])
    public_id, secret = created.public_id, created.admin_secret
    with Session(engine) as s:
        slot_id = s.exec(select(Slot)).one().id
    assert slot_id is not None

    r = client.post(
        admin_url(public_id, secret, f"/slots/{slot_id}/delete"),
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == admin_url(public_id, secret)


def test_delete_slot_wrong_campaign_returns_404(client, engine):
    a = create_campaign_with_recurring_slot(client, name="A", player_names=[])
    b = create_campaign_with_recurring_slot(client, name="B", player_names=[])
    with Session(engine) as s:
        campaign_a = s.exec(select(Campaign).where(Campaign.public_id == a.public_id)).one()
        slot_a = s.exec(select(Slot).where(Slot.campaign_id == campaign_a.id)).one()
        slot_a_id = slot_a.id
    assert slot_a_id is not None

    r = client.post(admin_url(b.public_id, b.admin_secret, f"/slots/{slot_a_id}/delete"))
    assert r.status_code == 404

    with Session(engine) as s:
        assert s.get(Slot, slot_a_id) is not None

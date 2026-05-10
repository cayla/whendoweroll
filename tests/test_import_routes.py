"""Importing a previously-exported campaign creates a fresh one.

Round-trip integrity:
- ``POST /import`` accepts the JSON downloaded from
  ``GET /c/{public_id}/admin/{secret}/export.json``.
- The new campaign gets a fresh ``public_id``, fresh admin secret, and fresh
  per-player tokens (none of those are stored in the backup).
- Roster, slots, availability, opt-outs, and the consensus policy are all
  carried across.
"""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import (
    Availability,
    AvailabilityStatus,
    Campaign,
    ConsensusPolicy,
    OccurrenceOptOut,
    Player,
    PublicRecurrenceMode,
    Slot,
    SlotKind,
)


def _create_campaign(client, names: list[str]):
    r = client.post(
        "/",
        data={
            "name": "Import Test",
            "timezone": "UTC",
            "player_names": "\n".join(names),
            "horizon_weeks": "4",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2)


def _seed(engine, *, public_id: str) -> dict:
    """Add a recurring slot, an ad-hoc slot, an availability, and an opt-out.

    Returns a small fixture dict with the exact starting times so the test
    can assert that they survive the round-trip.
    """
    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        campaign.consensus_policy = ConsensusPolicy.allow_one
        campaign.horizon_weeks = 7
        campaign.public_recurrence_mode = PublicRecurrenceMode.twice_per_month
        s.add(campaign)
        recurring = Slot(
            campaign_id=campaign.id,
            kind=SlotKind.recurring,
            label="Friday game",
            weekday=4,
            start_local="18:00",
            duration_hours=3.5,
        )
        s.add(recurring)

        starts = datetime.now(UTC).replace(microsecond=0) + timedelta(days=10)
        ends = starts + timedelta(hours=2)
        adhoc = Slot(
            campaign_id=campaign.id,
            kind=SlotKind.adhoc,
            label="One-off",
            duration_hours=2.0,
            starts_at_utc=starts,
            ends_at_utc=ends,
        )
        s.add(adhoc)

        players = s.exec(select(Player).where(Player.campaign_id == campaign.id).order_by(Player.sort_order)).all()
        alice, bob = players[0], players[1]
        alice.is_mandatory = True
        s.add(alice)
        s.commit()
        s.refresh(recurring)
        s.refresh(adhoc)

        s.add(Availability(player_id=alice.id, slot_id=recurring.id, status=AvailabilityStatus.yes))
        s.add(Availability(player_id=bob.id, slot_id=recurring.id, status=AvailabilityStatus.no))
        opt_out_at = starts + timedelta(days=7)
        s.add(
            OccurrenceOptOut(
                player_id=alice.id,
                slot_id=recurring.id,
                starts_at_utc=opt_out_at,
            )
        )
        s.commit()

        return {
            "adhoc_starts_at_utc": starts,
            "opt_out_starts_at_utc": opt_out_at,
        }


def _post_import(client, payload: dict):
    """Multipart upload of ``payload`` as a JSON file."""
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/import",
        files={"backup": ("export.json", io.BytesIO(body), "application/json")},
    )


def test_export_then_import_roundtrips_full_campaign(client, engine):
    public_id, secret = _create_campaign(client, ["Alice", "Bob"])
    fixture = _seed(engine, public_id=public_id)

    export = client.get(f"/c/{public_id}/admin/{secret}/export.json")
    assert export.status_code == 200
    payload = export.json()
    assert payload["export_version"] == 3
    assert payload["campaign"]["consensus_policy"] == ConsensusPolicy.allow_one.value
    assert payload["campaign"]["public_recurrence_mode"] == PublicRecurrenceMode.twice_per_month.value
    assert payload["campaign"]["public_min_gap_days"] == 0
    recurring_export = next(s for s in payload["slots"] if s["kind"] == "recurring")
    assert "public_recurrence_mode" not in recurring_export

    imported = _post_import(client, payload)
    assert imported.status_code == 200

    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", imported.text)
    assert m
    new_public_id, new_secret = m.group(1), m.group(2)
    assert new_public_id != public_id
    assert new_secret != secret

    with Session(engine) as s:
        new_campaign = s.exec(select(Campaign).where(Campaign.public_id == new_public_id)).one()
        assert new_campaign.name == "Import Test"
        assert new_campaign.timezone == "UTC"
        assert new_campaign.horizon_weeks == 7
        assert new_campaign.consensus_policy == ConsensusPolicy.allow_one
        assert new_campaign.public_recurrence_mode == PublicRecurrenceMode.twice_per_month
        assert new_campaign.public_min_gap_days == 0

        roster = s.exec(select(Player).where(Player.campaign_id == new_campaign.id).order_by(Player.sort_order)).all()
        assert [p.display_name for p in roster] == ["Alice", "Bob"]
        assert [p.is_mandatory for p in roster] == [True, False]

        slots = s.exec(select(Slot).where(Slot.campaign_id == new_campaign.id)).all()
        recurring = next(sl for sl in slots if sl.kind == SlotKind.recurring)
        adhoc = next(sl for sl in slots if sl.kind == SlotKind.adhoc)
        assert recurring.weekday == 4
        assert recurring.start_local == "18:00"
        assert recurring.duration_hours == 3.5
        assert recurring.label == "Friday game"
        assert adhoc.starts_at_utc.replace(tzinfo=UTC) == fixture["adhoc_starts_at_utc"]
        assert adhoc.duration_hours == 2.0

        avails = s.exec(
            select(Availability).where(Availability.slot_id == recurring.id).order_by(Availability.id)
        ).all()
        statuses = {next(p.display_name for p in roster if p.id == a.player_id): a.status for a in avails}
        assert statuses == {"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.no}

        opts = s.exec(select(OccurrenceOptOut).where(OccurrenceOptOut.slot_id == recurring.id)).all()
        assert len(opts) == 1
        assert opts[0].starts_at_utc.replace(tzinfo=UTC) == fixture["opt_out_starts_at_utc"]
        assert opts[0].player_id == next(p.id for p in roster if p.display_name == "Alice")


def test_import_links_in_response_open_admin_dashboard(client):
    public_id, secret = _create_campaign(client, ["Solo"])
    payload = client.get(f"/c/{public_id}/admin/{secret}/export.json").json()

    imported = _post_import(client, payload)
    assert imported.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", imported.text)
    assert m
    new_public_id, new_secret = m.group(1), m.group(2)

    admin = client.get(f"/c/{new_public_id}/admin/{new_secret}")
    assert admin.status_code == 200
    assert "Import Test" in admin.text


def test_import_v2_payload_without_consensus_policy_uses_default(client, engine):
    public_id, secret = _create_campaign(client, ["A"])
    payload = client.get(f"/c/{public_id}/admin/{secret}/export.json").json()
    payload["export_version"] = 2
    payload["campaign"].pop("consensus_policy", None)

    imported = _post_import(client, payload)
    assert imported.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/", imported.text)
    assert m
    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == m.group(1))).one()
        assert campaign.consensus_policy == ConsensusPolicy.no_two_nears


def test_import_rejects_invalid_json(client):
    r = client.post(
        "/import",
        files={"backup": ("export.json", io.BytesIO(b"not-json"), "application/json")},
    )
    assert r.status_code == 400
    assert "JSON" in r.text


def test_import_rejects_unsupported_version(client):
    r = _post_import(
        client,
        {
            "export_version": 99,
            "campaign": {"name": "X", "timezone": "UTC"},
            "players": [],
            "slots": [],
            "availability": [],
            "occurrence_opt_outs": [],
        },
    )
    assert r.status_code == 400
    assert "export_version" in r.text


def test_import_rejects_unknown_timezone(client):
    r = _post_import(
        client,
        {
            "export_version": 3,
            "campaign": {"name": "X", "timezone": "Atlantis/Lost"},
        },
    )
    assert r.status_code == 400


def test_import_rejects_dangling_availability_reference(client):
    r = _post_import(
        client,
        {
            "export_version": 3,
            "campaign": {"name": "X", "timezone": "UTC"},
            "players": [{"id": 1, "display_name": "A", "sort_order": 0}],
            "slots": [
                {
                    "id": 10,
                    "kind": "recurring",
                    "weekday": 0,
                    "start_local": "18:00",
                    "duration_hours": 2,
                }
            ],
            "availability": [{"player_id": 1, "slot_id": 999, "status": "yes"}],
            "occurrence_opt_outs": [],
        },
    )
    assert r.status_code == 400
    assert "unknown" in r.text.lower()


def test_import_blocked_when_new_campaigns_disabled(client, monkeypatch):
    public_id, secret = _create_campaign(client, [])
    payload = client.get(f"/c/{public_id}/admin/{secret}/export.json").json()
    monkeypatch.setenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "1")
    r = _post_import(client, payload)
    assert r.status_code == 403
    assert "disabled" in r.text.lower()


def test_landing_page_shows_import_form_by_default(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'action="/import"' in r.text
    assert 'name="backup"' in r.text


def test_landing_page_hides_import_form_when_disabled(client, monkeypatch):
    monkeypatch.setenv("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "1")
    r = client.get("/")
    assert r.status_code == 200
    assert 'action="/import"' not in r.text

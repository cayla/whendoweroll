"""End-to-end coverage for the per-campaign consensus policy.

Tests the wiring from the admin Settings form through to the public ICS feed:
saving a policy round-trips, and the calendar tightens or loosens to match.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import Availability, AvailabilityStatus, Campaign, ConsensusPolicy, Player, Slot, SlotKind


def _create_campaign(client, names: list[str]) -> tuple[str, str]:
    r = client.post(
        "/",
        data={
            "name": "Policy Test",
            "timezone": "UTC",
            "player_names": "\n".join(names),
            "horizon_weeks": "12",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m
    return m.group(1), m.group(2)


def _seed_adhoc_slot(
    engine,
    *,
    public_id: str,
    days_ahead: int,
    statuses: dict[str, AvailabilityStatus],
) -> None:
    start = datetime.now(UTC) + timedelta(days=days_ahead)
    end = start + timedelta(hours=3)
    with Session(engine) as s:
        campaign = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        slot = Slot(
            campaign_id=campaign.id,
            kind=SlotKind.adhoc,
            label=f"Day +{days_ahead}",
            duration_hours=3.0,
            starts_at_utc=start,
            ends_at_utc=end,
        )
        s.add(slot)
        s.commit()
        s.refresh(slot)
        players = s.exec(select(Player).where(Player.campaign_id == campaign.id)).all()
        by_name = {p.display_name: p for p in players}
        for name, status in statuses.items():
            s.add(Availability(player_id=by_name[name].id, slot_id=slot.id, status=status))
        s.commit()


def test_new_campaign_defaults_to_no_two_nears(client, engine):
    public_id, _secret = _create_campaign(client, ["Alice", "Bob"])
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.consensus_policy is ConsensusPolicy.no_two_nears


def test_settings_form_round_trips_consensus_policy(client, engine):
    public_id, secret = _create_campaign(client, ["Alice", "Bob"])
    r = client.post(
        f"/c/{public_id}/admin/{secret}/settings",
        data={
            "name": "Policy Test",
            "timezone": "UTC",
            "horizon_weeks": "12",
            "consensus_policy": ConsensusPolicy.strict.value,
        },
    )
    assert r.status_code in (200, 303)
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
    assert c.consensus_policy is ConsensusPolicy.strict


def test_settings_rejects_unknown_consensus_policy(client):
    public_id, secret = _create_campaign(client, ["Alice", "Bob"])
    r = client.post(
        f"/c/{public_id}/admin/{secret}/settings",
        data={
            "name": "Policy Test",
            "timezone": "UTC",
            "horizon_weeks": "12",
            "consensus_policy": "bogus",
        },
    )
    assert r.status_code == 400


def _set_policy(engine, public_id: str, policy: ConsensusPolicy) -> None:
    with Session(engine) as s:
        c = s.exec(select(Campaign).where(Campaign.public_id == public_id)).one()
        c.consensus_policy = policy
        s.add(c)
        s.commit()


def test_ics_under_strict_drops_near_consensus_windows(client, engine):
    """A campaign on the ``strict`` policy should never emit a near-consensus
    event, even though one missing player would normally qualify.
    """
    public_id, _secret = _create_campaign(client, ["Alice", "Bob"])
    _seed_adhoc_slot(
        engine,
        public_id=public_id,
        days_ahead=3,
        statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.no},
    )
    _set_policy(engine, public_id, ConsensusPolicy.strict)
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    assert "BEGIN:VEVENT" not in r.content.decode("utf-8")


def test_ics_under_allow_one_keeps_back_to_back_nears(client, engine):
    public_id, _secret = _create_campaign(client, ["Alice", "Bob"])
    for d in (3, 5):
        _seed_adhoc_slot(
            engine,
            public_id=public_id,
            days_ahead=d,
            statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.no},
        )
    _set_policy(engine, public_id, ConsensusPolicy.allow_one)
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    assert r.content.decode("utf-8").count("BEGIN:VEVENT") == 2


def test_ics_under_no_two_nears_skips_back_to_back_near_consensus(client, engine):
    """Two consecutive near-consensus windows: under the default policy the
    feed must drop the second one to keep the calendar honest.
    """
    public_id, _secret = _create_campaign(client, ["Alice", "Bob"])
    for d in (3, 5):
        _seed_adhoc_slot(
            engine,
            public_id=public_id,
            days_ahead=d,
            statuses={"Alice": AvailabilityStatus.yes, "Bob": AvailabilityStatus.no},
        )
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert body.count("BEGIN:VEVENT") == 1
    assert "[missing: Bob]" in body


def test_ics_under_no_repeat_holdout_drops_only_same_person_repeats(client, engine):
    """Same holdout twice: drop the second. Different holdouts: keep both."""
    public_id, _secret = _create_campaign(client, ["Alice", "Bob", "Carol"])
    _seed_adhoc_slot(
        engine,
        public_id=public_id,
        days_ahead=3,
        statuses={
            "Alice": AvailabilityStatus.yes,
            "Bob": AvailabilityStatus.yes,
            # Carol unset = missing
        },
    )
    _seed_adhoc_slot(
        engine,
        public_id=public_id,
        days_ahead=5,
        statuses={
            "Alice": AvailabilityStatus.yes,
            "Bob": AvailabilityStatus.yes,
            # Carol unset = missing again -> would be a repeat holdout
        },
    )
    _seed_adhoc_slot(
        engine,
        public_id=public_id,
        days_ahead=7,
        statuses={
            "Alice": AvailabilityStatus.yes,
            "Carol": AvailabilityStatus.yes,
            # Bob unset = missing -> different holdout, OK after Carol-as-holdout
        },
    )
    _set_policy(engine, public_id, ConsensusPolicy.no_repeat_holdout)
    r = client.get(f"/c/{public_id}/calendar-consensus.ics")
    body = r.content.decode("utf-8")
    assert body.count("BEGIN:VEVENT") == 2
    # First Carol-out window survived; second was dropped; Bob-out window kept.
    assert "[missing: Carol]" in body
    assert "[missing: Bob]" in body

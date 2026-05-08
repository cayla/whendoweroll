"""Mandatory attendees must be available for find_next_meet / list consensus."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import AvailabilityStatus, Player
from app.services.consensus import find_next_meet, list_consensus_occurrences
from app.services.slots import Occurrence


def _occ(sid: int, hours: int) -> Occurrence:
    start = datetime.now(UTC) + timedelta(hours=hours)
    return Occurrence(
        slot_id=sid,
        label="slot",
        starts_at_utc=start,
        ends_at_utc=start + timedelta(hours=2),
    )


def test_everyone_requires_mandatory_yes_even_if_others_yes():
    occs = [_occ(1, 24)]
    ma = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    pl = Player(id=2, campaign_id=1, display_name="P2", token_hash="h2", is_mandatory=False)
    availability = {(2, 1): AvailabilityStatus.yes}  # mandatory attendee unset
    assert find_next_meet(occs, [ma, pl], availability, max_missing=0) is None


def test_everyone_ok_when_mandatory_yes():
    occs = [_occ(1, 24)]
    ma = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    pl = Player(id=2, campaign_id=1, display_name="P2", token_hash="h2", is_mandatory=False)
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
    }
    r = find_next_meet(occs, [ma, pl], availability, max_missing=0)
    assert r is not None
    assert r.missing_count == 0


def test_all_but_one_mandatory_no_kills_window_even_if_only_one_missing():
    occs = [_occ(1, 24)]
    ma = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    p2 = Player(id=2, campaign_id=1, display_name="B", token_hash="h2", is_mandatory=False)
    p3 = Player(id=3, campaign_id=1, display_name="C", token_hash="h3", is_mandatory=False)
    # Only the mandatory attendee is "missing" (said no). len(missing)==1 would
    # normally qualify for max_missing=1, but the mandatory rule overrides.
    availability = {
        (1, 1): AvailabilityStatus.no,
        (2, 1): AvailabilityStatus.yes,
        (3, 1): AvailabilityStatus.yes,
    }
    assert find_next_meet(occs, [ma, p2, p3], availability, max_missing=1) is None


def test_all_but_one_mandatory_yes_one_other_missing():
    occs = [_occ(1, 24)]
    ma = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    p2 = Player(id=2, campaign_id=1, display_name="B", token_hash="h2", is_mandatory=False)
    p3 = Player(id=3, campaign_id=1, display_name="C", token_hash="h3", is_mandatory=False)
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (2, 1): AvailabilityStatus.yes,
        # P3 unset -> one missing, mandatory present.
    }
    r = find_next_meet(occs, [ma, p2, p3], availability, max_missing=1)
    assert r is not None
    assert 3 in r.missing_player_ids


def test_list_consensus_skips_mandatory_absent_rows():
    occs = [_occ(1, 24), _occ(2, 48)]
    ma = Player(id=1, campaign_id=1, display_name="GM", token_hash="h1", is_mandatory=True)
    p2 = Player(id=2, campaign_id=1, display_name="B", token_hash="h2", is_mandatory=False)
    # Slot 1: mandatory no -> skip. Slot 2: all yes -> include.
    availability = {
        (1, 1): AvailabilityStatus.no,
        (2, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
    }
    rows = list_consensus_occurrences(occs, [ma, p2], availability, max_missing=0, limit=10)
    assert len(rows) == 1
    assert rows[0].occurrence.slot_id == 2


def test_multiple_mandatory_attendees_all_required():
    """Two co-GMs: both must be yes for the occurrence to qualify."""
    occs = [_occ(1, 24), _occ(2, 48)]
    gm_a = Player(id=1, campaign_id=1, display_name="GM-A", token_hash="h1", is_mandatory=True)
    gm_b = Player(id=2, campaign_id=1, display_name="GM-B", token_hash="h2", is_mandatory=True)
    pl = Player(id=3, campaign_id=1, display_name="P", token_hash="h3", is_mandatory=False)
    # Slot 1: GM-A yes, GM-B unset -> mandatory missing -> skip.
    # Slot 2: both GMs yes, P unset -> 1 missing (P).
    availability = {
        (1, 1): AvailabilityStatus.yes,
        (3, 1): AvailabilityStatus.yes,
        (1, 2): AvailabilityStatus.yes,
        (2, 2): AvailabilityStatus.yes,
    }
    r = find_next_meet(occs, [gm_a, gm_b, pl], availability, max_missing=1)
    assert r is not None
    assert r.occurrence.slot_id == 2
    assert 3 in r.missing_player_ids

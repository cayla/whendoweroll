"""Bulk exception changes on the player page."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.helpers import create_campaign_with_recurring_slot

_CAMPAIGN_TZ = ZoneInfo("America/New_York")


def _today() -> date:
    return datetime.now(_CAMPAIGN_TZ).date()


def _bulk_default_range() -> tuple[date, date]:
    """Matches server default: this week Monday through next week Sunday."""
    today = _today()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=13)


def _campaign_with_friday_slot(client) -> tuple[str, str]:
    created = create_campaign_with_recurring_slot(
        client,
        name="Bulk",
        timezone="America/New_York",
        player_names="Rogue",
        horizon_weeks=8,
        label="Friday",
    )
    assert created.player_tokens
    return created.public_id, created.player_tokens[0]


def test_bulk_widget_collapsed_by_default(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    page = client.get(f"/c/{public_id}/p/{player_token}")
    assert page.status_code == 200
    assert b"Bulk date changes" in page.content
    assert b"data-bulk-dropdown" in page.content
    assert b"player-exceptions-sticky-head" in page.content
    menu = page.content.split(b"data-bulk-dropdown-menu", 1)[1][:120]
    assert b"hidden" in menu


def test_bulk_mark_range_without_standing_yes_does_nothing(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    start = _today()
    end = start + timedelta(days=56)
    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={
            "action": "mark_range",
            "calendar_start_day": start.isoformat(),
            "calendar_end_day": end.isoformat(),
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"No new conflicts" in resp.content
    assert b"Remove conflict" not in resp.content


def test_bulk_mark_range_marks_conflicts_after_standing_yes(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})

    start = _today()
    end = start + timedelta(days=56)
    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={
            "action": "mark_range",
            "calendar_start_day": start.isoformat(),
            "calendar_end_day": end.isoformat(),
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"Marked" in resp.content
    assert b"conflict" in resp.content
    assert b"Remove conflict" in resp.content


def test_bulk_clear_range_after_this_and_next_week_quick_marks(client):
    """Clear range spans this week through next week, not only the last quick preset."""
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})
    client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "mark_this_week"},
    )
    client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "mark_next_week"},
    )
    mid = client.get(f"/c/{public_id}/p/{player_token}")
    assert b"Remove conflict" in mid.content

    start, end = _bulk_default_range()
    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={
            "action": "clear_range",
            "calendar_start_day": start.isoformat(),
            "calendar_end_day": end.isoformat(),
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"Cleared" in resp.content
    assert b"Can't make it" in resp.content
    assert b"Remove conflict" not in resp.content


def test_bulk_clear_all_removes_every_conflict(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})
    client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "mark_this_week"},
    )
    client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "mark_next_week"},
    )
    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "clear_all"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"Cleared" in resp.content
    assert b"Remove conflict" not in resp.content


def test_bulk_mark_this_week(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})

    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "mark_this_week"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    content = resp.content
    has_result = b"Marked" in content or b"No new conflicts" in content
    assert has_result


def test_bulk_rejects_inverted_range(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})

    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={
            "action": "mark_range",
            "calendar_start_day": "2026-06-01",
            "calendar_end_day": "2026-05-01",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"last day must be on or after the first day" in resp.content


def test_bulk_unknown_action_returns_error(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})

    resp = client.post(
        f"/c/{public_id}/p/{player_token}/bulk-exceptions",
        data={"action": "nope"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"Unknown bulk action" in resp.content


def test_single_opt_out_refreshes_full_exceptions_block(client):
    public_id, player_token = _campaign_with_friday_slot(client)
    client.post(f"/c/{public_id}/p/{player_token}/availability/1", data={"status": "yes"})
    frag = client.get(f"/c/{public_id}/p/{player_token}/_recurring-exceptions")
    m2 = re.search(
        rb'name="occurrence_start" value="([^"]+)".*?name="busy" value="1"',
        frag.content,
        re.DOTALL,
    )
    assert m2
    resp = client.post(
        f"/c/{public_id}/p/{player_token}/opt-out",
        data={"slot_id": "1", "occurrence_start": m2.group(1).decode(), "busy": "1"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert b"Remove conflict" in resp.content
    assert b"player-exceptions-toolbar" not in resp.content

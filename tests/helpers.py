"""Shared helpers for route/integration tests."""

from __future__ import annotations

import re
from typing import NamedTuple

from httpx import Response


class CreatedCampaign(NamedTuple):
    public_id: str
    admin_secret: str
    player_tokens: list[str]
    response_text: str


def post_create_campaign(
    client,
    *,
    name: str = "Test",
    timezone: str = "America/New_York",
    player_names: str | list[str] = "Alice\nBob",
    horizon_weeks: int = 12,
) -> Response:
    """POST ``/`` to create a campaign; returns the raw response."""
    if isinstance(player_names, list):
        player_names = "\n".join(player_names)
    return client.post(
        "/",
        data={
            "name": name,
            "timezone": timezone,
            "player_names": player_names,
            "horizon_weeks": str(horizon_weeks),
        },
    )


def parse_created_campaign(response_text: str) -> CreatedCampaign:
    """Extract capability URLs from a successful created-campaign page."""
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", response_text)
    assert m, "admin URL not found in response"
    public_id, admin_secret = m.group(1), m.group(2)
    raw_tokens = re.findall(rf"/c/{public_id}/p/([\w\-]+)", response_text)
    player_tokens = list(dict.fromkeys(raw_tokens))
    return CreatedCampaign(public_id, admin_secret, player_tokens, response_text)


def create_campaign_via_form(
    client,
    *,
    name: str = "Test",
    timezone: str = "America/New_York",
    player_names: str | list[str] = "Alice\nBob",
    horizon_weeks: int = 12,
) -> CreatedCampaign:
    """POST ``/`` and parse capability URLs (asserts HTTP 200)."""
    r = post_create_campaign(
        client,
        name=name,
        timezone=timezone,
        player_names=player_names,
        horizon_weeks=horizon_weeks,
    )
    assert r.status_code == 200, r.text
    return parse_created_campaign(r.text)


def add_recurring_slot(
    client,
    *,
    public_id: str,
    admin_secret: str,
    weekday: str = "4",
    start_local: str = "18:00",
    duration_hours: str = "3",
    label: str | None = None,
) -> None:
    """Add a recurring slot via the admin form (asserts success)."""
    data: dict[str, str] = {
        "kind": "recurring",
        "weekday": weekday,
        "start_local": start_local,
        "duration_hours": duration_hours,
    }
    if label is not None:
        data["label"] = label
    r = client.post(f"/c/{public_id}/admin/{admin_secret}/slots", data=data)
    assert r.status_code in (200, 303), r.text


def create_campaign_with_recurring_slot(
    client,
    *,
    name: str = "Test",
    timezone: str = "America/New_York",
    player_names: str | list[str] = "Alice\nBob",
    horizon_weeks: int = 12,
    weekday: str = "4",
    start_local: str = "18:00",
    duration_hours: str = "3",
    label: str | None = None,
) -> CreatedCampaign:
    """Create a campaign and add one recurring slot."""
    created = create_campaign_via_form(
        client,
        name=name,
        timezone=timezone,
        player_names=player_names,
        horizon_weeks=horizon_weeks,
    )
    add_recurring_slot(
        client,
        public_id=created.public_id,
        admin_secret=created.admin_secret,
        weekday=weekday,
        start_local=start_local,
        duration_hours=duration_hours,
        label=label,
    )
    return created

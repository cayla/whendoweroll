"""Shared helpers for route/integration tests."""

from __future__ import annotations

import re
from typing import NamedTuple


class CreatedCampaign(NamedTuple):
    public_id: str
    admin_secret: str
    player_tokens: list[str]
    response_text: str


def create_campaign_via_form(
    client,
    *,
    name: str = "Test",
    timezone: str = "America/New_York",
    player_names: str | list[str] = "Alice\nBob",
    horizon_weeks: int = 12,
) -> CreatedCampaign:
    """POST ``/`` and parse capability URLs from the created-campaign page."""
    if isinstance(player_names, list):
        player_names = "\n".join(player_names)
    r = client.post(
        "/",
        data={
            "name": name,
            "timezone": timezone,
            "player_names": player_names,
            "horizon_weeks": str(horizon_weeks),
        },
    )
    assert r.status_code == 200, r.text
    m = re.search(r"/c/([0-9a-f]+)/admin/([\w\-]+)", r.text)
    assert m, "admin URL not found in response"
    public_id, admin_secret = m.group(1), m.group(2)
    raw_tokens = re.findall(rf"/c/{public_id}/p/([\w\-]+)", r.text)
    player_tokens = list(dict.fromkeys(raw_tokens))
    return CreatedCampaign(public_id, admin_secret, player_tokens, r.text)

"""Shared cap for exception table rows and bulk mark."""

from __future__ import annotations

from app.models import Campaign
from app.services.player_view import exception_horizon_weeks


def test_exception_horizon_weeks_uses_campaign_when_under_cap():
    campaign = Campaign(name="x", timezone="UTC", horizon_weeks=8)
    assert exception_horizon_weeks(campaign) == 8


def test_exception_horizon_weeks_caps_at_26_weeks():
    campaign = Campaign(name="x", timezone="UTC", horizon_weeks=52)
    assert exception_horizon_weeks(campaign) == 26

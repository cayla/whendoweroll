"""Process-level settings from environment variables."""

from __future__ import annotations

import os


def new_campaigns_disabled() -> bool:
    """When true, ``POST /`` is rejected and the home form is read-only."""
    v = os.environ.get("DND_SCHEDULER_DISABLE_NEW_CAMPAIGNS", "").strip().lower()
    return v in ("1", "true", "yes", "on")

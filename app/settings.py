"""Process-level settings from environment variables."""

from __future__ import annotations

import os

# When not None, overrides ``WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS`` for this process.
_new_campaigns_override: bool | None = None


def new_campaigns_disabled() -> bool:
    """When true, ``POST /`` is rejected and the home form is read-only."""
    if _new_campaigns_override is not None:
        return _new_campaigns_override
    v = os.environ.get("WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def new_campaigns_override() -> bool | None:
    """None means follow environment; True/False forces disabled/enabled creation."""
    return _new_campaigns_override


def set_new_campaigns_override(value: bool | None) -> None:
    """Set runtime override (super admin). ``None`` clears override."""
    global _new_campaigns_override
    _new_campaigns_override = value


def reset_runtime_settings() -> None:
    """Clear process-level overrides (e.g. between tests)."""
    global _new_campaigns_override
    _new_campaigns_override = None

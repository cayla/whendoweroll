"""Cache-busting token for local CSS/JS static assets."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.paths import STATIC_DIR

_cached_version: str | None = None


def static_asset_version(static_dir: Path | None = None) -> str:
    """Short hash of ``static/css`` and ``static/js`` file contents.

    ``WHENDOWEROLL_STATIC_VERSION`` overrides the hash (useful for forced busts).
    """
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    override = os.environ.get("WHENDOWEROLL_STATIC_VERSION", "").strip()
    if override:
        _cached_version = override
        return _cached_version

    root = static_dir or STATIC_DIR
    digest = hashlib.sha256()
    for sub in ("css", "js"):
        folder = root / sub
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix().encode()
            digest.update(rel)
            digest.update(path.read_bytes())

    _cached_version = digest.hexdigest()[:12]
    return _cached_version


def reset_static_asset_version() -> None:
    """Clear memoized version (tests)."""
    global _cached_version
    _cached_version = None

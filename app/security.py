"""Capability-token helpers.

URLs in this app *are* the credential. We never store raw tokens, only their
SHA-256 hash, so a leaked database doesn't hand out admin/player access.
Lookups remain O(1) because SHA-256 is deterministic.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# 24 bytes -> 32 url-safe characters; ample entropy and short enough to share.
TOKEN_BYTES = 24


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, stored_hash: str) -> bool:
    # constant-time compare so we don't leak hash prefixes via timing.
    return hmac.compare_digest(hash_token(token), stored_hash)

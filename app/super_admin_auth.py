"""Operator super-admin UI: challenge password and signed session cookie."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

_PASSWORD: str | None = None
_SERIALIZER: URLSafeTimedSerializer | None = None
_BOOTSTRAPPED = False

SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
SESSION_COOKIE_NAME = "whendoweroll_sa_session"


def reset_super_admin_auth() -> None:
    """Clear bootstrap state (e.g. app shutdown in tests)."""
    global _PASSWORD, _SERIALIZER, _BOOTSTRAPPED
    _PASSWORD = None
    _SERIALIZER = None
    _BOOTSTRAPPED = False


def bootstrap() -> None:
    """Load or generate password and cookie signing secret; log password once per process start."""
    global _PASSWORD, _SERIALIZER, _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    env_pwd = (os.environ.get("WHENDOWEROLL_SUPER_ADMIN_PASSWORD") or "").strip()
    _PASSWORD = env_pwd or secrets.token_urlsafe(18)
    cookie_secret = (os.environ.get("WHENDOWEROLL_SUPER_ADMIN_COOKIE_SECRET") or "").strip() or secrets.token_urlsafe(
        32
    )
    _SERIALIZER = URLSafeTimedSerializer(cookie_secret, salt="whendoweroll-super-admin")

    # Uvicorn often shows WARNING for app loggers but not INFO; use WARNING so Docker/Fly logs
    # always include the one-time password when no env var is set.
    if not env_pwd:
        logger.warning(
            "Super admin: WHENDOWEROLL_SUPER_ADMIN_PASSWORD not set. "
            "Open /internal/super-admin and sign in with this one-time password: %s",
            _PASSWORD,
        )
    else:
        logger.info("Super admin UI: /internal/super-admin (password from WHENDOWEROLL_SUPER_ADMIN_PASSWORD)")


def challenge_password() -> str:
    if _PASSWORD is None:
        raise RuntimeError("super admin auth not bootstrapped")
    return _PASSWORD


def verify_challenge(attempt: str) -> bool:
    if _PASSWORD is None:
        return False
    a = hashlib.sha256(_PASSWORD.encode("utf-8")).digest()
    b = hashlib.sha256((attempt or "").strip().encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def issue_session_token() -> str:
    if _SERIALIZER is None:
        raise RuntimeError("super admin auth not bootstrapped")
    return _SERIALIZER.dumps({"ok": True})


def verify_session_token(token: str | None) -> bool:
    if not token or _SERIALIZER is None:
        return False
    try:
        _SERIALIZER.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except BadSignature, SignatureExpired:
        return False

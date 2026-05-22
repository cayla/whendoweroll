"""Cache-Control headers for ``/static`` so browsers and CDNs behave predictably."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_VERSIONED_CACHE = "public, max-age=31536000, immutable"
_UNVERSIONED_CACHE = "no-cache, must-revalidate"
_UNVERSIONED_CDN_CACHE = "max-age=0"


class StaticCacheControlMiddleware(BaseHTTPMiddleware):
    """Versioned static URLs may cache long; bare paths should revalidate."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/static/") and response.status_code == 200:
            if request.query_params.get("v"):
                response.headers["Cache-Control"] = _VERSIONED_CACHE
                response.headers["CDN-Cache-Control"] = _VERSIONED_CACHE
            else:
                response.headers["Cache-Control"] = _UNVERSIONED_CACHE
                response.headers["CDN-Cache-Control"] = _UNVERSIONED_CDN_CACHE
        return response

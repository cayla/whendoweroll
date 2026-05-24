"""Display timezone cookie: effective zone + invalid cookie fallback."""

from __future__ import annotations

from starlette.requests import Request

from app.view_timezone import COOKIE_NAME, effective_display_timezone
from tests.helpers import create_campaign_via_form


def test_effective_display_timezone_reads_cookie():
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.0", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "headers": [(b"cookie", f"{COOKIE_NAME}=UTC".encode())],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "state": {},
    }
    req = Request(scope)
    assert effective_display_timezone(req, "America/New_York") == "UTC"


def test_effective_display_timezone_invalid_falls_back():
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.0", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "headers": [(b"cookie", f"{COOKIE_NAME}=Not/ARealZone".encode())],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "state": {},
    }
    req = Request(scope)
    assert effective_display_timezone(req, "America/New_York") == "America/New_York"


def test_public_page_reflects_cookie(client):
    created = create_campaign_via_form(
        client, name="TZ Test", timezone="America/New_York", player_names="", horizon_weeks=2
    )
    client.cookies.set(COOKIE_NAME, "UTC")
    page = client.get(f"/c/{created.public_id}")
    assert page.status_code == 200
    assert "UTC" in page.text

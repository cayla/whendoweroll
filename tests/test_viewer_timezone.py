"""Display timezone cookie: effective zone + invalid cookie fallback."""

from __future__ import annotations

import re

from starlette.requests import Request

from app.view_timezone import COOKIE_NAME, effective_display_timezone


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
    r = client.post(
        "/",
        data={
            "name": "TZ Test",
            "timezone": "America/New_York",
            "player_names": "",
            "horizon_weeks": "2",
        },
    )
    assert r.status_code == 200
    m = re.search(r"/c/([0-9a-f]+)", r.text)
    assert m
    public_id = m.group(1)
    client.cookies.set(COOKIE_NAME, "UTC")
    page = client.get(f"/c/{public_id}")
    assert page.status_code == 200
    assert "UTC" in page.text

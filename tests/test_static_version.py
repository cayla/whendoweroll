"""Static asset cache busting."""

from __future__ import annotations

import re

from app.static_version import reset_static_asset_version, static_asset_version


def test_static_asset_version_is_stable_for_same_tree():
    reset_static_asset_version()
    a = static_asset_version()
    reset_static_asset_version()
    b = static_asset_version()
    assert a == b
    assert len(a) == 12


def test_home_page_static_urls_include_version_query(client):
    page = client.get("/")
    assert page.status_code == 200
    match = re.search(rb"/static/css/app\.css\?v=([0-9a-f]{12})", page.content)
    assert match is not None
    reset_static_asset_version()
    assert match.group(1).decode() == static_asset_version()


def test_versioned_static_allows_long_cache(client):
    version = static_asset_version()
    resp = client.get(f"/static/css/app.css?v={version}")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]


def test_unversioned_static_must_revalidate(client):
    resp = client.get("/static/css/app.css")
    assert resp.status_code == 200
    assert "must-revalidate" in resp.headers["cache-control"]
    assert resp.headers.get("cdn-cache-control") == "max-age=0"

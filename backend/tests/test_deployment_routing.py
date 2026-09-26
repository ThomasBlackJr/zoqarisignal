"""Check the deployed routing contract against every actual FastAPI operation.

This models the documented Vercel service selection/request.path semantics; it
is not a substitute for a smoke test on Vercel's edge after deployment.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from starlette.routing import Match

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "vercel.json").read_text())


def routed(url):
    parts = urlsplit(url)
    rule = next(r for r in CONFIG["rewrites"] if re.fullmatch(r["source"], parts.path))
    service = rule["destination"]["service"]
    path = parts.path
    for route in CONFIG["services"][service].get("routes", []):
        matched = re.fullmatch(route["src"], parts.path)
        if matched:
            for transform in route.get("transforms", []):
                assert transform["type"] == "request.path" and transform["op"] == "set"
                path = re.sub(r"\$(\d+)", lambda m: matched.group(int(m[1])), transform["args"])
    return service, urlunsplit(("", "", path, parts.query, ""))


def test_all_backend_operations_have_one_public_api_mapping(app):
    paths = app.openapi()["paths"]
    assert "/account" in paths and "/preferences" in paths
    for path, methods in paths.items():
        example = re.sub(r"\{[^}]+\}", "fixture-id", path)
        service, internal = routed("/api" + example + "?q=two%20words&offset=0")
        assert service == "backend"
        assert internal == example + "?q=two%20words&offset=0"
        for method in methods:
            scope = {"type": "http", "method": method.upper(), "path": example, "root_path": ""}
            assert any(route.matches(scope)[0] is Match.FULL for route in app.routes), (method, path)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/login",
        "/register",
        "/dashboard",
        "/employees",
        "/employees/managers",
        "/rubrics",
        "/upload",
        "/team",
        "/account",
        "/calls",
        "/_next/static/chunk.js",
        "/brand/z-mark.png",
        "/brand/wordmark.png",
        "/brand/favicon.png",
        "/brand/apple-touch-icon.png",
        "/apiary",
    ],
)
def test_pages_and_assets_stay_with_next(path):
    assert routed(path) == ("frontend", path)


def test_account_preferences_and_representative_resources(signed_in):
    for path in [
        "/account",
        "/preferences",
        "/employees",
        "/manager-teams",
        "/rubrics",
        "/calls",
        "/batches",
        "/flag-rules",
        "/flag-notifications",
        "/billing",
        "/team",
        "/dashboard",
        "/briefing",
        "/admin/events",
        "/employee-imports/template.csv",
    ]:
        service, internal = routed("/api" + path)
        assert service == "backend"
        assert signed_in.get(internal).status_code == 200, path


def test_auth_csrf_upload_and_webhook_remain_backend_owned(client, wav_bytes):
    service, login = routed("/api/auth/login")
    assert service == "backend"
    response = client.post(login, json={"email": "admin@example.test", "password": "test-password-only"})
    assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
    _, preferences = routed("/api/preferences")
    assert client.put(preferences, json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    _, calls = routed("/api/calls")
    uploaded = client.post(calls, files={"file": ("routing.wav", wav_bytes, "audio/wav")})
    assert uploaded.status_code == 201
    _, audio = routed(f"/api/calls/{uploaded.json()['id']}/audio")
    response = client.get(audio, headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and len(response.content) == 10
    _, webhook = routed("/api/billing/webhook")
    # Configured billing/signature verification is independently tested; no CSRF header is needed here.
    assert webhook == "/billing/webhook"
    assert client.post(webhook, content=b"{}", headers={"X-Drive-Request": ""}).status_code == 503


def test_shipped_brand_assets_exist():
    for name in ("z-mark.png", "wordmark.png", "favicon.png", "apple-touch-icon.png"):
        assert (ROOT / "frontend" / "public" / "brand" / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

"""The app must stay private: login wall on everything, no-index everywhere, lockout, live refuses no password."""
import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("XAHOO_ADMIN_PASSWORD", "pw-test-1")
    monkeypatch.setenv("XAHOO_SECRET", "k")
    monkeypatch.setenv("XAHOO_MODE", "replay")
    monkeypatch.setenv("XAHOO_REPLAY_DAYS", "1")
    import xahoo.api as api
    api = importlib.reload(api)
    monkeypatch.setattr(api, "load_state", lambda: None)
    with TestClient(api.app) as c:
        yield c, api


def test_everything_private_until_login(client):
    c, _ = client
    for path in ("/", "/index.html", "/app.js"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
    assert c.get("/api/signals").status_code == 401
    r = c.get("/login")
    assert r.status_code == 200 and "noindex" in r.text
    for path in ("/login", "/robots.txt", "/api/signals", "/"):
        h = c.get(path, follow_redirects=False).headers
        assert "noindex" in h["x-robots-tag"] and h["referrer-policy"] == "no-referrer" and h["x-frame-options"] == "DENY"
    assert c.get("/robots.txt").text.strip().endswith("Disallow: /")


def test_login_session_and_lockout(client):
    c, _ = client
    assert c.post("/api/login", json={"password": "pw-test-1"}).status_code == 200
    assert c.get("/api/health").status_code == 200
    assert c.get("/", follow_redirects=False).status_code == 200
    c.post("/api/logout")
    c.cookies.clear()
    assert c.get("/api/health").status_code == 401
    codes = [c.post("/api/login", json={"password": "x"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_live_requires_password(monkeypatch):
    monkeypatch.delenv("XAHOO_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("XAHOO_MODE", "live")
    monkeypatch.delenv("XAHOO_DEV", raising=False)
    import xahoo.api as api
    api = importlib.reload(api)
    monkeypatch.setattr(api, "load_state", lambda: None)
    with pytest.raises(RuntimeError):
        with TestClient(api.app):
            pass
    monkeypatch.setenv("XAHOO_MODE", "replay")
    importlib.reload(api)

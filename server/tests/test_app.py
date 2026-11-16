"""Privacy: everything needs the login; search engines are told to stay out."""
import pytest
from fastapi.testclient import TestClient

from xahoo.config import MODELS, WEB

pytestmark = pytest.mark.skipif(not (MODELS / "manifest.json").exists() or not (WEB / "index.html").exists(),
                                reason="needs models/ and a built web/dist")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    import xahoo.app as app
    from xahoo.security import LoginLimiter, Sessions
    monkeypatch.setattr(app, "PASSWORD", "pw-test-1")
    monkeypatch.setattr(app, "SESSIONS", Sessions(b"k", "pw-test-1"))
    monkeypatch.setattr(app, "LIMITER", LoginLimiter())
    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setattr(app, "MODE", "live")

    async def no_feed(engine):
        return None
    monkeypatch.setattr(app, "live_feed", no_feed)
    with TestClient(app.app) as c:
        yield c


def test_private_until_login(client):
    for path in ("/", "/index.html", "/api/snapshot", "/api/health", "/api/tick", "/api/forecasts"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (303, 401), path
    js = [p.name for p in (WEB / "assets").iterdir() if p.suffix == ".js"][0]
    assert client.get(f"/assets/{js}", follow_redirects=False).status_code == 303
    r = client.get("/login")
    assert r.status_code == 200 and "noindex" in r.text
    assert client.get("/robots.txt").text.strip().endswith("Disallow: /")
    h = client.get("/login").headers
    assert "noindex" in h["x-robots-tag"] and h["x-frame-options"] == "DENY" and "wss://testserver" in h["content-security-policy"]


def test_login_then_data_and_lockout(client):
    assert client.post("/api/login", json={"password": "pw-test-1"}).status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200
    snap = client.get("/api/snapshot").json()
    assert len(snap["markets"]) == 10 and snap["horizons"] == ["1m", "5m", "15m", "1h", "4h", "1d"]
    assert client.get("/api/candles?sym=BTCUSDT&tf=1").status_code == 200
    assert client.get("/api/candles?sym=NOPE&tf=1").status_code == 404
    t = client.get("/api/tick").json()                     # HTTP fallback when a WebSocket is blocked
    assert t["type"] == "tick" and "forecast_ts" in t and len(t["m"]) == 10
    assert client.get("/api/forecasts").json()["type"] == "forecast"
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
    client.post("/api/logout")
    client.cookies.clear()
    assert client.get("/api/snapshot").status_code == 401
    codes = [client.post("/api/login", json={"password": "x"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429

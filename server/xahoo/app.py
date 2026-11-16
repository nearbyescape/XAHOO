"""XAHOO server: private web app + live WebSocket.

  XAHOO_MODE=live    Binance futures stream (default)
  XAHOO_MODE=replay  archived data played at XAHOO_REPLAY_SPEED from XAHOO_REPLAY_START (development)

Everything except the login page needs the owner's session cookie. Search engines are blocked by robots.txt,
X-Robots-Tag and meta tags.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import os
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import binance
from .config import DATA, DEV, MODE, MODELS, PASSWORD, SECRET, SYMS, TOTP_SECRET, WEB
from .engine import Engine
from .model import Models
from .security import PRIVACY_HEADERS, ROBOTS_TXT, LoginLimiter, Sessions, totp_ok
from .store import Store

log = logging.getLogger("xahoo")
COOKIE = "xahoo_session"
SESSIONS = Sessions(SECRET, PASSWORD)
LIMITER = LoginLimiter()
PUBLIC = {"/login", "/login.js", "/api/login", "/api/login/info", "/robots.txt", "/manifest.webmanifest"}
PUBLIC_PREFIX = ("/icons/", "/fonts/")          # the app bundle itself (/assets) needs the login


class Hub:
    """Fan-out of engine messages to connected screens."""

    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, msg: dict) -> None:           # may be called from a worker thread
        if self.loop is None:
            return
        data = json.dumps(msg, default=_json)
        self.loop.call_soon_threadsafe(self._fan, data)

    def _fan(self, data: str) -> None:
        for q in list(self.clients):
            if q.qsize() > 200:                     # a stuck client: drop it rather than grow without bound
                self.clients.discard(q)
                continue
            q.put_nowait(data)


def _json(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def _clean(o):
    """NaN/inf are not valid JSON: replace with null."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


HUB = Hub()
ENGINE: Engine | None = None


# ---------------------------------------------------------------- feeds
async def live_feed(engine: Engine) -> None:
    rest = binance.Rest()
    engine.status["feed"] = "backfilling"
    for sym in SYMS:
        mk = engine.m[sym]
        try:
            bars = await rest.klines(sym, 10_580)
            if len(bars):
                mk.bars = bars.iloc[:-1]                         # the last row is the still-forming bar
                engine.closed[sym] = int(mk.bars.index[-1].timestamp())
            mk.metrics = await rest.metrics(sym)
            mk.funding = await rest.funding(sym)
            log.info("backfilled %s: %d bars, %d metric rows", sym, len(mk.bars), len(mk.metrics))
        except Exception:  # noqa: BLE001
            log.exception("backfill failed for %s", sym)
    if engine.closed:
        engine.last_minute = min(engine.closed.values())
    engine.status["feed"] = "live"
    asyncio.create_task(binance.stream(SYMS, engine.on_event))
    asyncio.create_task(_metrics_loop(engine, rest))
    asyncio.create_task(_gap_loop(engine, rest))
    asyncio.create_task(_book_loop(engine, rest))
    await _minute_loop(engine)


async def _book_loop(engine: Engine, rest: binance.Rest, every: float = 15.0) -> None:
    """Order-book snapshot for each market every ~15 s (weight 20 each: ~800 of Binance's 2,400 per minute)."""
    while True:
        for sym in SYMS:
            t0 = time.time()
            try:
                engine.set_book(sym, await rest.depth(sym, 1000))
            except Exception as e:  # noqa: BLE001
                log.warning("depth %s: %s", sym, type(e).__name__)
            await asyncio.sleep(max(0.0, every / len(SYMS) - (time.time() - t0)))


async def gap_fill(engine: Engine, rest: binance.Rest, sym: str) -> int:
    """Add closed bars the stream missed (start-up, reconnects); redo the full backfill if history is short."""
    mk = engine.m[sym]
    short = len(mk.bars) < 3000
    bars = await rest.klines(sym, 10_580 if short else 90)
    if not len(bars):
        return 0
    bars = bars.iloc[:-1]                                        # the last row is still forming
    new = bars.loc[bars.index.difference(mk.bars.index)]
    if len(new):
        mk.bars = pd.concat([mk.bars, new]).sort_index().iloc[-(10_600):]
        engine.closed[sym] = max(engine.closed.get(sym, 0), int(mk.bars.index[-1].timestamp()))
        if short:
            mk.metrics = await rest.metrics(sym)
            mk.funding = await rest.funding(sym)
    return len(new)


async def _gap_loop(engine: Engine, rest: binance.Rest) -> None:
    await asyncio.sleep(10)                                      # let the stream connect first
    while True:
        for sym in SYMS:
            try:
                n = await gap_fill(engine, rest, sym)
                if n:
                    log.info("gap fill %s: %d bars", sym, n)
            except Exception as e:  # noqa: BLE001
                log.warning("gap fill %s: %s", sym, type(e).__name__)
        await asyncio.sleep(180)


async def _minute_loop(engine: Engine) -> None:
    while True:
        await asyncio.sleep(0.25)
        m = engine.minute_ready()
        if m is None:
            now = time.time()
            prev_minute = int(now // 60) * 60 - 60
            if now % 60 > 4 and (engine.last_minute or 0) < prev_minute and engine.closed:
                engine.force_close(prev_minute)                  # quiet market: no close message arrived
                m = engine.minute_ready()
        if m is not None:
            try:
                await asyncio.to_thread(engine.forecast, m)
            except Exception:  # noqa: BLE001
                log.exception("forecast failed")
                engine.last_minute = m


async def _metrics_loop(engine: Engine, rest: binance.Rest) -> None:
    n = 0
    while True:
        await asyncio.sleep(300 - time.time() % 300 + 20)        # shortly after each 5-minute mark
        n += 1
        for sym in SYMS:
            mk = engine.m[sym]
            try:
                new = await rest.metrics(sym, points=6)
                if len(new):
                    met = pd.concat([mk.metrics, new])
                    mk.metrics = met[~met.index.duplicated(keep="last")].sort_index().iloc[-2400:]
                if n % 12 == 0:
                    mk.funding = await rest.funding(sym)
            except Exception as e:  # noqa: BLE001
                log.warning("metrics refresh %s: %s", sym, type(e).__name__)


async def replay_feed(engine: Engine) -> None:
    from . import replay
    start = pd.Timestamp(os.environ.get("XAHOO_REPLAY_START", "2026-10-20 12:00"), tz="UTC")
    speed = float(os.environ.get("XAHOO_REPLAY_SPEED", "20"))
    asyncio.create_task(replay.simulate_book_and_trades(engine))
    await replay.run(engine, engine.clock, start, int(os.environ.get("XAHOO_REPLAY_MINUTES", "2000")), speed)


async def _tick_loop(engine: Engine) -> None:
    while True:
        await asyncio.sleep(1.0)
        if HUB.clients:
            HUB.publish(_clean(engine.tick()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ENGINE
    logging.basicConfig(level=os.environ.get("XAHOO_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)          # one line per Binance request is too noisy
    if MODE == "live" and not PASSWORD and not DEV:
        raise RuntimeError("XAHOO_ADMIN_PASSWORD is required (set XAHOO_DEV=1 only for local testing)")
    clock = time.time
    if MODE == "replay":
        from .replay import SimClock
        clock = SimClock(time.time())
    ENGINE = Engine(Models(MODELS), Store(DATA / ("replay.db" if MODE == "replay" else "xahoo.db")), clock)
    HUB.loop = asyncio.get_running_loop()
    ENGINE.listeners.append(lambda m: HUB.publish(_clean(m)))
    tasks = [asyncio.create_task(replay_feed(ENGINE) if MODE == "replay" else live_feed(ENGINE)),
             asyncio.create_task(_tick_loop(ENGINE))]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="XAHOO", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ---------------------------------------------------------------- privacy + auth
def _authed(cookies) -> bool:
    return not PASSWORD or SESSIONS.valid(cookies.get(COOKIE, ""))


@app.middleware("http")
async def privacy_and_auth(request: Request, call_next):
    p = request.url.path
    public = p in PUBLIC or p.startswith(PUBLIC_PREFIX)
    if not public and not _authed(request.cookies):
        resp = JSONResponse({"detail": "login required"}, status_code=401) if p.startswith("/api/") \
            else RedirectResponse("/login", status_code=303)
    else:
        resp = await call_next(request)
    host = request.headers.get("host", "")
    for k, v in PRIVACY_HEADERS.items():
        if k == "Content-Security-Policy" and host:      # allow the app's own WebSocket explicitly
            v = v.replace("connect-src 'self'", f"connect-src 'self' wss://{host} ws://{host}")
        resp.headers[k] = v
    if p.startswith("/api/") or p in ("/", "/login", "/index.html"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.api_route("/robots.txt", methods=["GET", "HEAD"])
def robots():
    return PlainTextResponse(ROBOTS_TXT)


@app.api_route("/login", methods=["GET", "HEAD"])
def login_page():
    return FileResponse(WEB / "login.html")


@app.get("/api/login/info")
def login_info():
    return {"totp": bool(TOTP_SECRET)}


@app.post("/api/login")
async def login(request: Request, response: Response):
    # last X-Forwarded-For hop = the address our own HTTPS proxy saw (earlier hops can be spoofed)
    who = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[-1].strip()
    wait = LIMITER.locked(who)
    if wait:
        raise HTTPException(429, f"too many attempts — try again in {wait // 60 + 1} min")
    body = await request.json()
    ok = bool(PASSWORD) and hmac.compare_digest(str(body.get("password", "")), PASSWORD)
    if ok and TOTP_SECRET:
        ok = totp_ok(TOTP_SECRET, str(body.get("code", "")))
    if not ok:
        LIMITER.fail(who)
        raise HTTPException(401, "wrong password or code")
    LIMITER.ok(who)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"
    response.set_cookie(COOKIE, SESSIONS.issue(), httponly=True, samesite="strict", secure=secure, max_age=30 * 86400, path="/")
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------- data
@app.get("/api/health")
def health():
    e = ENGINE
    return _clean({"ok": True, "mode": MODE, "model": e.models.version, "status": e.status,
                   "bars": {s: len(m.bars) for s, m in e.m.items()}})


@app.get("/api/snapshot")
def snapshot():
    return _clean(ENGINE.snapshot())


@app.get("/api/tick")
def tick():
    """HTTP fallback for screens whose WebSocket is blocked: the same per-second update."""
    t = ENGINE.tick()
    t["forecast_ts"] = ENGINE.status.get("last_forecast")
    return _clean(t)


@app.get("/api/forecasts")
def forecasts():
    """HTTP fallback: the latest forecast for every market, in the WebSocket message format."""
    return _clean({"type": "forecast", "ts": ENGINE.status.get("last_forecast"),
                   "markets": {s: m.forecast for s, m in ENGINE.m.items() if m.forecast}})


@app.get("/api/candles")
def candles(sym: str, tf: int = 1, limit: int = 500):
    if sym not in ENGINE.m or tf not in (1, 5, 15, 60):
        raise HTTPException(404, "unknown market or timeframe")
    return _clean(ENGINE.candles(sym, tf, min(limit, 1500)))


@app.get("/api/scoreboard")
def scoreboard(sym: str | None = None, days: float = 30):
    if sym and sym not in ENGINE.m:
        raise HTTPException(404, "unknown market")
    since = int(ENGINE.clock() - days * 86400)
    return _clean({"since": since, "sym": sym, "horizons": ENGINE.store.scoreboard(since, sym),
                   "recent": ENGINE.store.recent(60)})


@app.websocket("/ws")
async def ws(sock: WebSocket):
    if not _authed(sock.cookies):
        await sock.close(code=4401)
        return
    await sock.accept()
    q: asyncio.Queue = asyncio.Queue()
    try:
        await sock.send_text(json.dumps(_clean(ENGINE.snapshot()), default=_json))
        HUB.clients.add(q)
        while True:
            await sock.send_text(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        HUB.clients.discard(q)


# ---------------------------------------------------------------- UI
@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB), name="web")

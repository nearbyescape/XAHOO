"""XAHOO API + static terminal UI.

Run:  cd engine && uvicorn xahoo.api:app --port 8000

Mode REPLAY (current): loads cached Dukascopy history, runs the engine over
the most recent days and serves the result as if live. The LIVE mode will
swap the data source for the chosen real-time provider and the database.

Privacy: every page, file and API call requires the owner's login (signed 30-day session cookie, optional TOTP
2-step code via XAHOO_TOTP_SECRET, lockout after 5 failures). Search engines are blocked (robots.txt + X-Robots-Tag
+ meta). LIVE mode refuses to start without XAHOO_ADMIN_PASSWORD (set XAHOO_DEV=1 only for local testing).
"""
from __future__ import annotations

import hashlib
import time
import hmac
import math
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import features, indicators as ind
from .config import SYMBOLS, TF_MINUTES, StrategyParams
from .data import dukascopy
from .data.resample import resample
from .engine import breakdown, generate, run_backtest, stats
from .security import PRIVACY_HEADERS, ROBOTS_TXT, LoginLimiter, Sessions, totp_ok

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
CACHE = ROOT / "data" / "dukascopy"
REPLAY_DAYS = int(os.environ.get("XAHOO_REPLAY_DAYS", "30"))
WARMUP_DAYS = 40

PASSWORD = os.environ.get("XAHOO_ADMIN_PASSWORD", "")
SECRET = os.environ.get("XAHOO_SECRET", "dev-secret-change-me").encode()
TOTP_SECRET = os.environ.get("XAHOO_TOTP_SECRET", "")
DEV = os.environ.get("XAHOO_DEV", "") == "1"
SESSIONS = Sessions(SECRET, PASSWORD)
LIMITER = LoginLimiter()
PUBLIC = {"/login", "/login.js", "/api/login", "/api/login/info", "/robots.txt", "/manifest.webmanifest", "/sw.js", "/styles.css",
          "/favicon.ico"}
PUBLIC_PREFIX = ("/icons/", "/vendor/fonts/")
COOKIE = "xahoo_session"

app = FastAPI(title="XAHOO", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------- state
class State:
    params = StrategyParams.trader()
    runner = None
    m1: dict[str, pd.DataFrame] = {}
    signals: pd.DataFrame = pd.DataFrame()
    now: pd.Timestamp | None = None
    mode = "REPLAY"


S = State()


def load_state() -> None:
    data = {}
    for sym in SYMBOLS:
        try:
            data[sym] = dukascopy.load(sym, CACHE)
        except FileNotFoundError:
            continue
    if not data:
        return
    S.m1 = data
    S.now = min(df.index[-1] for df in data.values()) + pd.Timedelta(minutes=1)
    start = S.now - pd.Timedelta(days=REPLAY_DAYS)
    win = {s: df[df.index >= start - pd.Timedelta(days=WARMUP_DAYS)] for s, df in data.items()}
    cand = generate(win, S.params, S.params.exec_tfs)
    if not cand.empty:
        cand = cand[cand["close_time"] >= start].reset_index(drop=True)
    bt = run_backtest(win, S.params, S.params.exec_tfs, cand=cand)
    if not bt.empty:
        ist = bt["close_time"] + pd.Timedelta(minutes=330)
        bt["id"] = [f"SIG-{t:%Y%m%d-%H%M}-{s[:3]}-{tf}" for t, s, tf in zip(ist, bt["symbol"], bt["tf"])]
        bt = bt.sort_values("close_time", ascending=False).reset_index(drop=True)
    S.signals = bt


MODE = os.environ.get("XAHOO_MODE", "replay").lower()


def _live_loop() -> None:
    """Backfill, then run the free-feed live service inside this process."""
    import logging
    import threading

    from .live.runner import LiveRunner
    r = LiveRunner(S.params)
    S.runner = r
    r.backfill(download=os.environ.get("XAHOO_BACKFILL", "1") == "1")
    try:
        load_state()                  # fresh server: history just arrived, so build the analytics replay now
    except Exception:  # noqa: BLE001
        logging.getLogger("xahoo.live").exception("replay after backfill failed")
    S.m1 = r.m1
    stop = threading.Event()
    while not stop.is_set():
        t0 = time.time()
        try:
            r.step()
            last = max((m.index[-1] for m in r.m1.values() if len(m)), default=None)
            if last is not None:
                S.now = last + pd.Timedelta(minutes=1)
        except Exception:  # noqa: BLE001
            logging.getLogger("xahoo.live").exception("live step failed")
        stop.wait(max(0.2, r.poll - (time.time() - t0)))


@app.on_event("startup")
def _startup() -> None:
    load_state()                      # backtest replay of the last N days (analytics + "BT" signals)
    if MODE == "live" and not PASSWORD and not DEV:
        raise RuntimeError("XAHOO_MODE=live requires XAHOO_ADMIN_PASSWORD (set XAHOO_DEV=1 only for local testing)")
    if MODE == "live":
        import threading
        S.mode = "LIVE"
        threading.Thread(target=_live_loop, name="xahoo-live", daemon=True).start()


# ---------------------------------------------------------------- auth
def _authed(request: Request) -> bool:
    return not PASSWORD or SESSIONS.valid(request.cookies.get(COOKIE, ""))


@app.middleware("http")
async def privacy_and_auth(request: Request, call_next):
    p = request.url.path
    public = p in PUBLIC or p.startswith(PUBLIC_PREFIX)
    if not public and not _authed(request):
        if p.startswith("/api/"):
            resp = JSONResponse({"detail": "login required"}, status_code=401)
        else:
            resp = RedirectResponse("/login", status_code=303)
    else:
        resp = await call_next(request)
    for k, v in PRIVACY_HEADERS.items():
        resp.headers[k] = v
    if p.startswith("/api/") or p in ("/", "/login", "/index.html", "/sw.js"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


@app.get("/robots.txt")
def robots():
    return PlainTextResponse(ROBOTS_TXT)


@app.get("/login")
def login_page():
    return FileResponse(WEB / "login.html")


@app.post("/api/login")
async def login(request: Request, response: Response):
    # last X-Forwarded-For hop = the address our own HTTPS proxy saw (earlier hops can be spoofed by the client)
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
    response.set_cookie(COOKIE, SESSIONS.issue(), httponly=True, samesite="strict", secure=_https(request),
                        max_age=30 * 86400, path="/")
    return {"ok": True}


@app.get("/api/login/info")
def login_info():
    return {"totp": bool(TOTP_SECRET)}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------- helpers
def _ts(t: pd.Timestamp) -> int:
    return int(t.timestamp())


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) else round(float(v), 5)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return _ts(v)
    return v


def _sig_dict(r: pd.Series) -> dict:
    keys = ["id", "symbol", "tf", "dir", "setup", "grade", "score", "entry", "sl", "tp1", "tp2", "tp3", "risk",
            "add_price", "lots",
            "close_time", "exit_time", "exit_price", "result", "r", "tp_hits", "mfe_r", "mae_r", "minutes",
            "session", "overlap", "1h_bias", "4h_bias", "atr"]
    d = {k: _clean(r[k]) for k in keys if k in r}
    d["components"] = r.get("components", {})
    d["source"] = "backtest"
    return d


def _session_now(t: pd.Timestamp) -> dict:
    m = t.hour * 60 + t.minute
    return {"asia": 0 <= m < 7 * 60, "london": 7 * 60 <= m < 16 * 60 + 30, "newyork": 12 * 60 + 30 <= m < 21 * 60,
            "signal_window": any(a <= m < b for a, b, _ in S.params.sessions.windows)}


# ---------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    return {"ok": True, "mode": S.mode, "auth": bool(PASSWORD), "now": _ts(S.now) if S.now is not None else None,
            "symbols": list(S.m1), "params_version": S.params.version,
            "bars": {s: int(len(df)) for s, df in S.m1.items()}}


@app.get("/api/overview")
def overview():
    if not S.m1:
        raise HTTPException(503, "no market data loaded")
    out = {"now": _ts(S.now), "session": _session_now(S.now), "symbols": {}}
    p = S.params
    for sym, m1 in S.m1.items():
        tail = m1[m1.index >= S.now - pd.Timedelta(days=WARMUP_DAYS + 5)]
        last = tail.iloc[-1]
        day = tail[tail.index >= S.now - pd.Timedelta(hours=24)]          # rolling 24h
        prev_close = day["close"].iloc[0] if len(day) else last["close"]
        matrix = {}
        for tf in ("1m", "5m", "15m", "1h", "4h"):
            f = features.tf_frame(tail, tf, p)
            f = f[f["close_time"] <= S.now]
            row = f.iloc[-1]
            matrix[tf] = {
                "bias": int(row["bias"]),
                "ema_fast": round(float(row["ema_fast"]), 3), "ema_slow": round(float(row["ema_slow"]), 3),
                "d_fast_atr": round(float((row["close"] - row["ema_fast"]) / row["atr"]), 2),
                "d_slow_atr": round(float((row["close"] - row["ema_slow"]) / row["atr"]), 2),
                "adx": round(float(row["adx"]), 1), "atr": round(float(row["atr"]), 3),
            }
        out["symbols"][sym] = {
            "price": float(last["close"]), "spread": SYMBOLS[sym].spread,
            "change": round(float(last["close"] - prev_close), 3),
            "change_pct": round(float((last["close"] / prev_close - 1) * 100), 2),
            "day_high": float(day["high"].max()) if len(day) else None,
            "day_low": float(day["low"].min()) if len(day) else None,
            "matrix": matrix,
        }
    return out


@app.get("/api/candles")
def candles(symbol: str = "XAUUSD", tf: str = "5m", limit: int = 600, end: int | None = None):
    """Last `limit` bars up to `end` (unix seconds, default = now)."""
    if symbol not in S.m1 or tf not in TF_MINUTES:
        raise HTTPException(404, "unknown symbol/tf")
    m1 = S.m1[symbol]
    stop = min(S.now, pd.Timestamp(end, unit="s", tz="UTC")) if end else S.now
    span = timedelta(minutes=TF_MINUTES[tf] * (limit + S.params.ema_slow * 3))
    df = resample(m1[(m1.index >= stop - span) & (m1.index < stop)], tf)
    df["ema_fast"] = ind.ema(df["close"], S.params.ema_fast)
    df["ema_slow"] = ind.ema(df["close"], S.params.ema_slow)
    df = df.tail(limit)
    t = [int(x.timestamp()) for x in df.index]
    r = lambda s: [round(float(v), 3) for v in s]
    return {"symbol": symbol, "tf": tf, "t": t, "o": r(df["open"]), "h": r(df["high"]), "l": r(df["low"]),
            "c": r(df["close"]), "ema_fast": r(df["ema_fast"]), "ema_slow": r(df["ema_slow"])}


@app.get("/api/signals")
def signals(limit: int = 200, symbol: str | None = None, tf: str | None = None):
    live = S.runner.store.signals(limit) if S.runner is not None else []
    for x in live:
        x.setdefault("result", None if x["state"] not in ("TP", "SL", "BE", "TRAIL", "TIME") else x["state"])
    df = S.signals
    bt = []
    if not df.empty:
        if symbol:
            df = df[df["symbol"] == symbol]
        if tf:
            df = df[df["tf"] == tf]
        bt = [_sig_dict(r) for _, r in df.head(limit).iterrows()]
    live = [x for x in live if (not symbol or x["symbol"] == symbol) and (not tf or x["tf"] == tf)]
    return {"signals": live + bt}


@app.get("/api/signals/{sid}/events")
def signal_events(sid: str):
    return {"events": S.runner.store.events(sid) if S.runner is not None else []}


@app.get("/api/alerts")
def alerts(since: int = 0, limit: int = 100):
    return {"alerts": S.runner.store.alerts(since, limit) if S.runner is not None else []}


@app.get("/api/alerts/latest")
def alerts_latest():
    """Used by the service worker after a (payload-free) push to show the notification text."""
    a = S.runner.store.alerts(0, 1) if S.runner is not None else []
    return a[0] if a else {"title": "XAHOO", "body": "New alert"}


@app.get("/api/push/key")
def push_key():
    if S.runner is None:
        raise HTTPException(409, "live mode not running")
    return {"key": S.runner.push.public_key}


@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    if S.runner is None:
        raise HTTPException(409, "live mode not running")
    sub = await request.json()
    if not str(sub.get("endpoint", "")).startswith("https://"):
        raise HTTPException(400, "bad subscription")
    subs = [x for x in (S.runner.store.get("push_subs", []) or []) if x.get("endpoint") != sub["endpoint"]]
    subs.append({"endpoint": sub["endpoint"], "keys": sub.get("keys", {})})
    S.runner.store.put("push_subs", subs[-10:])            # at most 10 devices
    return {"ok": True, "devices": len(subs[-10:])}


@app.post("/api/push/test")
def push_test():
    if S.runner is None:
        raise HTTPException(409, "live mode not running")
    S.runner.notify("test", "info", "XAHOO test alert", "Notifications are working on this device.", tg_text=None,
                    external=True)
    return {"ok": True}


@app.get("/api/watch")
def watch():
    return {"watch": list(S.runner.watch.values()) if S.runner is not None else []}


@app.get("/api/guard")
def guard():
    return S.runner.guard(notify=False) if S.runner is not None else {"state": "N/A"}


@app.post("/api/guard/resume")
def guard_resume():
    if S.runner is None:
        raise HTTPException(409, "live mode not running")
    return S.runner.resume()


@app.post("/api/guard/pause")
def guard_pause():
    if S.runner is None:
        raise HTTPException(409, "live mode not running")
    return S.runner.pause()


@app.get("/api/feed")
def feed():
    if S.runner is None:
        return {"mode": S.mode}
    r = S.runner
    q = {s: {"bid": v.bid, "ask": v.ask, "ts": v.ts, "source": v.source} for s, v in r.quotes.items()}
    return {"mode": S.mode, "status": r.status, "quotes": q,
            "ready": {s: bool(r.ready(s)) for s in r.m1}, "open": len(r.store.signals(open_only=True))}


@app.get("/api/stats")
def get_stats():
    bt = S.signals
    if bt.empty:
        return {"summary": stats(bt)}
    bt = bt.sort_values("close_time")
    bt = bt.assign(hour_ist=(bt["close_time"] + pd.Timedelta(minutes=330)).dt.hour)
    tables = {}
    for name, by in (("symbol", "symbol"), ("tf", "tf"), ("setup", "setup"), ("grade", "grade"),
                     ("session", "session"), ("hour_ist", "hour_ist")):
        b = breakdown(bt, by).reset_index().rename(columns={by: "key"})
        tables[name] = [{k: _clean(v) for k, v in row.items()} for row in b.to_dict("records")]
    eq = bt["r"].cumsum()
    return {
        "summary": stats(bt),
        "tables": tables,
        "equity": [{"t": _ts(t), "v": round(float(v), 3)} for t, v in zip(bt["exit_time"], eq)],
        "results": {k: int(v) for k, v in bt["result"].value_counts().items()},
        "window_days": REPLAY_DAYS,
    }


@app.get("/api/params")
def params():
    import json
    return {"version": S.params.version, "params": json.loads(S.params.to_json())}


@app.post("/api/reload")
def reload():
    load_state()
    return health()


# ---------------------------------------------------------------- UI
@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")

"""XAHOO API + static terminal UI.

Run:  cd engine && uvicorn xahoo.api:app --port 8000

Mode REPLAY (current): loads cached Dukascopy history, runs the engine over
the most recent days and serves the result as if live. The LIVE mode will
swap the data source for the chosen real-time provider and the database.

Auth: single admin. Set XAHOO_ADMIN_PASSWORD (and XAHOO_SECRET) to require
login; without it the API runs open in dev mode and the UI shows a warning.
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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import features, indicators as ind
from .config import SYMBOLS, TF_MINUTES, StrategyParams
from .data import dukascopy
from .data.resample import resample
from .engine import breakdown, generate, run_backtest, stats

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
CACHE = ROOT / "data" / "dukascopy"
REPLAY_DAYS = int(os.environ.get("XAHOO_REPLAY_DAYS", "30"))
WARMUP_DAYS = 40

PASSWORD = os.environ.get("XAHOO_ADMIN_PASSWORD", "")
SECRET = os.environ.get("XAHOO_SECRET", "dev-secret-change-me").encode()
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
    if MODE == "live":
        import threading
        S.mode = "LIVE"
        threading.Thread(target=_live_loop, name="xahoo-live", daemon=True).start()


# ---------------------------------------------------------------- auth
def _token() -> str:
    return hmac.new(SECRET, b"admin:" + PASSWORD.encode(), hashlib.sha256).hexdigest()


@app.middleware("http")
async def auth(request: Request, call_next):
    p = request.url.path
    if PASSWORD and p.startswith("/api/") and p not in ("/api/login", "/api/health"):
        if not hmac.compare_digest(request.cookies.get(COOKIE, ""), _token()):
            return JSONResponse({"detail": "login required"}, status_code=401)
    return await call_next(request)


@app.post("/api/login")
async def login(request: Request, response: Response):
    body = await request.json()
    if not PASSWORD or not hmac.compare_digest(str(body.get("password", "")), PASSWORD):
        raise HTTPException(401, "bad password")
    response.set_cookie(COOKIE, _token(), httponly=True, samesite="strict", secure=request.url.scheme == "https",
                        max_age=60 * 60 * 12)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
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

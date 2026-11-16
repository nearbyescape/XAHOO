"""Binance USD-M futures market data: REST history and the combined WebSocket stream. Public endpoints, no API key.

Parsers are pure functions (tested with sample payloads); network code is thin.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
import pandas as pd

log = logging.getLogger("xahoo.binance")
REST = "https://fapi.binance.com"
# Since 2026-04-23 Binance serves USD-M futures streams on routed paths; kline, markPrice, forceOrder and aggTrade
# are "market" streams. The old unrouted URL still accepts connections but delivers none of these.
WS = "wss://fstream.binance.com/market/stream?streams="
IDLE_S = 60          # no message for this long on 40 busy streams = a dead connection: reconnect
BAR_COLS = ["open", "high", "low", "close", "volume", "count", "taker_buy_volume"]
METRIC_ENDPOINTS = {            # column -> (path, field)
    "oi": ("/futures/data/openInterestHist", "sumOpenInterest"),
    "top_ls_acct": ("/futures/data/topLongShortAccountRatio", "longShortRatio"),
    "top_ls_pos": ("/futures/data/topLongShortPositionRatio", "longShortRatio"),
    "ls_acct": ("/futures/data/globalLongShortAccountRatio", "longShortRatio"),
    "taker_ratio": ("/futures/data/takerlongshortRatio", "buySellRatio"),
}


# ------------------------------------------------------------------ parsers
def parse_klines(rows: list) -> pd.DataFrame:
    """REST /fapi/v1/klines rows -> 1m bars indexed by open time (UTC)."""
    if not rows:
        return pd.DataFrame(columns=BAR_COLS)
    df = pd.DataFrame(rows).iloc[:, [0, 1, 2, 3, 4, 5, 8, 9]]
    df.columns = ["t", *BAR_COLS]
    df.index = pd.to_datetime(df.pop("t").astype("int64"), unit="ms", utc=True)
    return df.astype("float64")


def parse_ws(msg: dict) -> dict | None:
    """One combined-stream message -> a small event dict, or None for anything we don't use."""
    d = msg.get("data") or {}
    e = d.get("e")
    if e == "kline":
        k = d["k"]
        return {"type": "bar", "sym": k["s"], "t": int(k["t"]), "open": float(k["o"]), "high": float(k["h"]),
                "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"]), "count": float(k["n"]),
                "taker_buy_volume": float(k["V"]), "closed": bool(k["x"]), "ts": int(d["E"])}
    if e == "markPriceUpdate":
        return {"type": "mark", "sym": d["s"], "mark": float(d["p"]), "index": float(d.get("i") or 0),
                "funding": float(d.get("r") or 0), "next_funding": int(d.get("T") or 0), "ts": int(d["E"])}
    if e == "aggTrade":
        px, qty = float(d["p"]), float(d["q"])
        # m = buyer is the maker, so the aggressive side was a seller
        return {"type": "trade", "sym": d["s"], "price": px, "qty": qty, "usd": px * qty,
                "side": "sell" if d.get("m") else "buy", "ts": int(d.get("T") or d["E"])}
    if e == "forceOrder":
        o = d["o"]
        qty, px = float(o.get("z") or o.get("q") or 0), float(o.get("ap") or o.get("p") or 0)
        # a SELL liquidation order closes a LONG position (and vice versa)
        return {"type": "liq", "sym": o["s"], "side": "long" if o["S"] == "SELL" else "short", "usd": qty * px,
                "price": px, "ts": int(o.get("T") or d["E"])}
    return None


def streams(syms: list[str]) -> str:
    parts = []
    for s in syms:
        s = s.lower()
        parts += [f"{s}@kline_1m", f"{s}@markPrice@1s", f"{s}@forceOrder", f"{s}@aggTrade"]
    return "/".join(parts)


# ------------------------------------------------------------------ REST
class Rest:
    def __init__(self, timeout: float = 15.0):
        self.http = httpx.AsyncClient(base_url=REST, timeout=timeout, headers={"User-Agent": "xahoo-terminal"})

    async def _get(self, path: str, **params):
        for attempt in range(4):
            try:
                r = await self.http.get(path, params=params)
                if r.status_code == 429 or r.status_code == 418:
                    await asyncio.sleep(int(r.headers.get("Retry-After", "5")))
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                if attempt == 3:
                    raise
                log.warning("%s %s: %s (retry)", path, params.get("symbol"), type(e).__name__)
                await asyncio.sleep(1.5 * (attempt + 1))

    async def klines(self, sym: str, minutes: int) -> pd.DataFrame:
        """The last `minutes` completed-or-forming 1m bars."""
        parts, end = [], None
        while minutes > 0:
            n = min(1500, minutes)
            p = {"symbol": sym, "interval": "1m", "limit": n}
            if end:
                p["endTime"] = end
            df = parse_klines(await self._get("/fapi/v1/klines", **p))
            if df.empty:
                break
            parts.append(df)
            end = int(df.index[0].timestamp() * 1000) - 1
            minutes -= len(df)
            if len(df) < n:
                break
        if not parts:
            return pd.DataFrame(columns=BAR_COLS)
        out = pd.concat(parts).sort_index()
        return out[~out.index.duplicated(keep="last")]

    async def daily(self, sym: str, days: int = 40) -> pd.Series:
        """Daily closes (index = day open, UTC) for the last `days` days; the last row is the forming day."""
        df = parse_klines(await self._get("/fapi/v1/klines", symbol=sym, interval="1d", limit=days))
        return df["close"] if len(df) else pd.Series(dtype="float64")

    async def metrics(self, sym: str, points: int = 2100) -> pd.DataFrame:
        """5-minute positioning snapshots (open interest, long/short ratios, taker ratio), ~7 days by default."""
        cols = {}
        for col, (path, field) in METRIC_ENDPOINTS.items():
            rows, end, left = [], None, points
            while left > 0:
                p = {"symbol": sym, "period": "5m", "limit": min(500, left)}
                if end:
                    p["endTime"] = end
                got = await self._get(path, **p)
                if not got:
                    break
                rows = got + rows
                end = int(got[0]["timestamp"]) - 1
                left -= len(got)
                if len(got) < p["limit"]:
                    break
            if rows:
                s = pd.Series({pd.Timestamp(int(r["timestamp"]), unit="ms", tz="UTC"): float(r[field]) for r in rows})
                cols[col] = s[~s.index.duplicated(keep="last")].sort_index()
        return pd.DataFrame(cols)

    async def funding(self, sym: str, limit: int = 100) -> pd.DataFrame:
        rows = await self._get("/fapi/v1/fundingRate", symbol=sym, limit=limit) or []
        s = pd.Series({pd.Timestamp(int(r["fundingTime"]), unit="ms", tz="UTC"): float(r["fundingRate"]) for r in rows})
        return pd.DataFrame({"funding": s.sort_index()})

    async def depth(self, sym: str, limit: int = 1000) -> dict:
        """Order book snapshot: {"bids": [[price, qty], ...], "asks": [...]} best first."""
        d = await self._get("/fapi/v1/depth", symbol=sym, limit=limit) or {}
        return {"bids": [[float(p), float(q)] for p, q in d.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in d.get("asks", [])], "ts": int(d.get("E") or 0)}

    async def close(self):
        await self.http.aclose()


# ------------------------------------------------------------------ WebSocket
async def stream(syms: list[str], on_event, stop: asyncio.Event | None = None):
    """Connect to the combined stream and call on_event(event) for every parsed message. Reconnects forever
    (Binance closes each connection after 24 h)."""
    import websockets
    url = WS + streams(syms)
    backoff = 1.0
    while not (stop and stop.is_set()):
        try:
            async with websockets.connect(url, ping_interval=150, ping_timeout=60, max_queue=4096) as ws:
                log.info("stream connected (%d streams)", len(syms) * 4)
                backoff = 1.0
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=IDLE_S)
                    except asyncio.TimeoutError:
                        log.warning("stream silent for %ds; reconnecting", IDLE_S)
                        break
                    ev = parse_ws(json.loads(raw))
                    if ev:
                        on_event(ev)
                    if stop and stop.is_set():
                        return
        except Exception as e:  # noqa: BLE001 - any disconnect: wait and reconnect
            log.warning("stream disconnected: %s; reconnecting in %.0fs", type(e).__name__, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def now_ms() -> int:
    return int(time.time() * 1000)

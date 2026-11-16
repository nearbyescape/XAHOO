"""Replay feed for development and tests: plays archived Binance data through the engine as if it were live.

Needs data/binance/*.parquet (research/download.py). Each simulated minute is spread over `60 / speed` real seconds,
with a few partial bar updates so the screen animates the way it does on the live stream.
"""
from __future__ import annotations

import asyncio
import logging

import numpy as np
import pandas as pd

from .config import DATA, KEEP_BARS, SYMS
from .engine import Engine

log = logging.getLogger("xahoo.replay")
BN = DATA / "binance"


class SimClock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def load_market(sym: str, start: pd.Timestamp, minutes: int):
    k = pd.read_parquet(BN / f"{sym}_1m.parquet")
    k = k[["open", "high", "low", "close", "volume", "count", "taker_buy_volume"]]
    hist = k[(k.index >= start - pd.Timedelta(minutes=KEEP_BARS)) & (k.index < start)]
    play = k[(k.index >= start) & (k.index < start + pd.Timedelta(minutes=minutes))]
    mark = pd.read_parquet(BN / f"{sym}_mark.parquet")["mark"]
    met = pd.read_parquet(BN / f"{sym}_metrics.parquet")
    fund = pd.read_parquet(BN / f"{sym}_funding.parquet")
    return hist, play, mark, met, fund


def prime(engine: Engine, start: pd.Timestamp, minutes: int) -> dict:
    """Load history into the engine and return the bars to play, per symbol."""
    play = {}
    for sym in SYMS:
        hist, p, mark, met, fund = load_market(sym, start, minutes)
        mk = engine.m[sym]
        mk.bars = hist.copy()
        end = start + pd.Timedelta(minutes=minutes)
        mk.metrics = met[met.index < end]          # features only read snapshots older than each bar
        mk.funding = fund[fund.index < end]
        m0 = mark.reindex([start - pd.Timedelta(minutes=1)], method="ffill")
        mk.mark = float(m0.iloc[0]) if len(m0) and m0.iloc[0] == m0.iloc[0] else float(hist["close"].iloc[-1])
        if len(hist):
            engine.closed[sym] = int(hist.index[-1].timestamp())
        play[sym] = (p, mark.reindex(p.index, method="ffill"))
    engine.last_minute = min(engine.closed.values())
    return play


def bar_events(sym: str, ts: pd.Timestamp, row, mark: float, parts: int = 4):
    """Split one archived bar into `parts` cumulative updates (open → high/low → close)."""
    t = int(ts.timestamp() * 1000)
    o, h, l, c, v, n, tb = (float(row[x]) for x in ("open", "high", "low", "close", "volume", "count", "taker_buy_volume"))
    up = c >= o
    path = [o, (l if up else h), (h if up else l), c][:parts] if parts >= 4 else [c]
    hi = lo = o
    for i, px in enumerate(path, 1):
        hi, lo = max(hi, px), min(lo, px)
        frac = i / len(path)
        yield {"type": "bar", "sym": sym, "t": t, "open": o, "high": hi if i < len(path) else h, "low": lo if i < len(path) else l,
               "close": px, "volume": v * frac, "count": n * frac, "taker_buy_volume": tb * frac, "closed": i == len(path),
               "ts": t + int(60000 * frac) - 1}
    yield {"type": "mark", "sym": sym, "mark": mark if mark == mark else c, "funding": float("nan"), "ts": t + 59999}


async def run(engine: Engine, clock: SimClock, start: pd.Timestamp, minutes: int, speed: float = 60.0,
              stop: asyncio.Event | None = None) -> None:
    play = prime(engine, start, minutes)
    engine.status["feed"] = f"replay ×{speed:g}"
    idx = play[SYMS[0]][0].index
    step = 60.0 / speed / 4
    for ts in idx:
        if stop and stop.is_set():
            return
        gens = {}
        for sym in SYMS:
            p, mark = play[sym]
            if ts in p.index:
                gens[sym] = list(bar_events(sym, ts, p.loc[ts], float(mark.loc[ts])))
        for i in range(5):
            clock.t = ts.timestamp() + min(60.0, 15.0 * (i + 1))
            for evs in gens.values():
                if i < len(evs):
                    engine.on_event(evs[i])
            if i < 4:
                await asyncio.sleep(step)
        m = engine.minute_ready()
        if m is not None:
            await asyncio.to_thread(engine.forecast, m)
    log.info("replay finished")


def run_fast(engine: Engine, clock: SimClock, start: pd.Timestamp, minutes: int) -> int:
    """Synchronous replay without delays (tests, warm-up). Returns the number of forecast minutes."""
    play = prime(engine, start, minutes)
    n = 0
    for ts in play[SYMS[0]][0].index:
        for sym in SYMS:
            p, mark = play[sym]
            if ts in p.index:
                for ev in bar_events(sym, ts, p.loc[ts], float(mark.loc[ts]), parts=1):
                    engine.on_event(ev)
        clock.t = ts.timestamp() + 60
        m = engine.minute_ready()
        if m is not None:
            engine.forecast(m)
            n += 1
    return n


async def simulate_book_and_trades(engine: Engine, every: float = 3.0) -> None:
    """Replay has no order book or individual trades in the archive. To exercise the screen, this makes a
    SIMULATED book (walls near the 24h buyer/seller zones and support/resistance) and occasional big trades
    shaped by each bar's taker buy share. Everything it produces is flagged sim=True and labelled on screen."""
    from .orderflow import BIG_TRADE_USD
    rng = np.random.default_rng(11)
    await asyncio.sleep(5)
    while True:
        for sym, mk in engine.m.items():
            if not len(mk.bars):
                continue
            px = mk.price
            if not px == px:
                continue
            tail = mk.bars.iloc[-60:]
            scale = float((tail["volume"] * tail["close"]).mean()) or 1e5
            fc = mk.forecast or {}
            anchors = [z["price"] for z in (fc.get("profile") or {}).get("zones", {}).get("buyers", [])] + \
                      [x["price"] for x in (fc.get("levels") or {}).get("support", [])[:2]]
            anchors_a = [z["price"] for z in (fc.get("profile") or {}).get("zones", {}).get("sellers", [])] + \
                        [x["price"] for x in (fc.get("levels") or {}).get("resistance", [])[:2]]
            book = {}
            for side, sign, anc in (("bids", -1, anchors), ("asks", 1, anchors_a)):
                d = np.sort(rng.uniform(0.00005, 0.012, 400))
                prices = px * (1 + sign * d)
                usd = rng.lognormal(0, 1.0, 400) * scale * 0.004
                for a in anc:
                    j = int(np.argmin(np.abs(prices - a)))
                    usd[j] += scale * rng.uniform(0.3, 1.2)
                book[side] = [[float(p), float(u / p)] for p, u in zip(prices, usd)]
            engine.set_book(sym, book, simulated=True)
            last = mk.bars.iloc[-1]
            share = float(last["taker_buy_volume"] / last["volume"]) if last["volume"] > 0 else 0.5
            thr = BIG_TRADE_USD.get(sym, 1e5)
            if rng.random() < min(0.6, scale / thr * 0.05):
                side = "buy" if rng.random() < share else "sell"
                usd = thr * (1 + rng.exponential(1.2))
                engine.on_event({"type": "trade", "sym": sym, "price": px, "qty": usd / px, "usd": usd, "side": side,
                                 "ts": int(engine.clock() * 1000), "sim": True})
        await asyncio.sleep(every)

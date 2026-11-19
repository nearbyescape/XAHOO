"""Where the strong buyers and sellers are.

1. Volume delta profile (from 1m bars, last 24 h): for each price band, how much was bought and sold by
   aggressive (taker) orders. Bands where one side clearly dominated are "buyer zones" / "seller zones".
2. Order-book walls (live): unusually large resting orders near the price, from the Binance order book
   (top 1000 levels per side). Walls are tracked between snapshots so the screen can show how long one has stood.
3. Big trades (live): single aggressive trades above a per-market size (BIG_TRADE_USD), and their 15-minute
   buy/sell totals.

These describe what is happening; they are not part of the tested forecast. Resting orders can be pulled
at any time.
"""
from __future__ import annotations

import math
import time

import numpy as np

BIG_TRADE_USD = {"BTCUSDT": 250_000, "ETHUSDT": 150_000, "SOLUSDT": 60_000, "XRPUSDT": 60_000, "BNBUSDT": 40_000,
                 "DOGEUSDT": 40_000, "ADAUSDT": 25_000, "LINKUSDT": 25_000, "XAUUSDT": 50_000, "XAGUSDT": 25_000}


def delta_profile(high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray, taker_buy: np.ndarray,
                  bins: int = 48) -> dict:
    """Aggressive buy / sell volume (USD) by price band. Each bar's volume is spread evenly over its range."""
    if len(close) < 30:
        return {}
    lo, hi = float(np.min(low)), float(np.max(high))
    if not hi > lo:
        return {}
    edges = np.linspace(lo, hi, bins + 1)
    buy, sell = np.zeros(bins), np.zeros(bins)
    usd_b = taker_buy * close
    usd_s = np.maximum(vol - taker_buy, 0) * close
    width = (hi - lo) / bins
    i0 = np.clip(((low - lo) / width).astype(int), 0, bins - 1)
    i1 = np.clip(((high - lo) / width).astype(int), 0, bins - 1)
    for a, b, ub, us in zip(i0, i1, usd_b, usd_s):
        k = b - a + 1
        buy[a:b + 1] += ub / k
        sell[a:b + 1] += us / k
    net = buy - sell
    tot = buy + sell
    scale = float(np.median(np.abs(net[tot > 0]))) if (tot > 0).any() else 0.0
    mids = (edges[:-1] + edges[1:]) / 2
    zones = {"buyers": [], "sellers": []}
    for side, order in (("buyers", np.argsort(-net)), ("sellers", np.argsort(net))):
        for i in order[:6]:
            v = net[i]
            if (side == "buyers" and v <= 0) or (side == "sellers" and v >= 0) or abs(v) < 2.0 * scale:
                continue
            if any(abs(z["i"] - i) <= 1 for z in zones[side]):          # skip neighbours of a zone already taken
                continue
            zones[side].append({"i": int(i), "price": float(mids[i]), "net": float(v),
                                "share": float(buy[i] / tot[i]) if tot[i] > 0 else 0.5})
            if len(zones[side]) == 2:
                break
    for z in zones["buyers"] + zones["sellers"]:
        z.pop("i")
    return {"lo": lo, "hi": hi, "buy": [round(float(x)) for x in buy], "sell": [round(float(x)) for x in sell],
            "zones": zones}


def book_walls(bids: list, asks: list, bin_frac: float = 0.0005, max_dist: float = 0.02, per_side: int = 3) -> dict:
    """bids / asks: [[price, qty], ...] best first. Returns walls (largest bands of resting orders) and imbalance."""
    if not bids or not asks:
        return {}
    b = np.array(bids, dtype=float)
    a = np.array(asks, dtype=float)
    mid = (b[0, 0] + a[0, 0]) / 2
    out = {"mid": mid, "bid": [], "ask": [], "covered": {}}
    usd = {}
    for side, arr, sign in (("bid", b, -1), ("ask", a, 1)):
        d = sign * (arr[:, 0] / mid - 1)                    # distance from mid, positive
        keep = d <= max_dist
        arr, d = arr[keep], d[keep]
        if not len(arr):
            continue
        out["covered"][side] = round(float(d.max()) * 100, 3)
        n = arr[:, 0] * arr[:, 1]
        band = np.floor(d / bin_frac).astype(int)
        sums = np.bincount(band, weights=n)
        px = np.bincount(band, weights=n * arr[:, 0]) / np.maximum(sums, 1e-12)
        usd[side] = (d, n)
        filled = sums[sums > 0]
        med = float(np.median(filled)) if len(filled) else 0.0
        for i in np.argsort(-sums)[:per_side * 3]:
            if sums[i] < 3.0 * med or sums[i] <= 0:
                break
            out[side].append({"price": float(px[i]), "usd": float(sums[i]), "dist": float(sign * (i + 0.5) * bin_frac * 100),
                              "x": round(float(sums[i] / med), 1) if med > 0 else None})
            if len(out[side]) == per_side:
                break
    for w in (0.0025, 0.01):
        bu = float(usd["bid"][1][usd["bid"][0] <= w].sum()) if "bid" in usd else 0.0
        au = float(usd["ask"][1][usd["ask"][0] <= w].sum()) if "ask" in usd else 0.0
        out[f"imb_{w * 100:g}"] = round(bu / (bu + au), 4) if bu + au > 0 else None
        out[f"bid_usd_{w * 100:g}"], out[f"ask_usd_{w * 100:g}"] = round(bu), round(au)
    return out


class WallTracker:
    """Remembers when each wall (side + price band) was first seen, so the screen can show its age."""

    def __init__(self, band_frac: float = 0.0008):
        self.first: dict = {}
        self.band = band_frac

    def update(self, walls: dict, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        seen = {}
        for side in ("bid", "ask"):
            for w in walls.get(side, []):
                key = (side, round(math.log(w["price"]) / self.band))
                t0 = next((self.first[k] for k in (key, (side, key[1] - 1), (side, key[1] + 1)) if k in self.first), now)
                seen[key] = t0
                w["age"] = round(now - t0)
        self.first = seen
        return walls


DEPTHS = (0.001, 0.0025, 0.005, 0.01, 0.02)


def book_stats(bids: list, asks: list) -> dict:
    """Compact order-book summary for the research recorder: spread, size at the best prices, resting USD within
    0.1 / 0.25 / 0.5 / 1 / 2% of the mid on each side, and the imbalance bid / (bid + ask) at each depth."""
    if not bids or not asks:
        return {}
    b, a = np.array(bids, dtype=float), np.array(asks, dtype=float)
    mid = (b[0, 0] + a[0, 0]) / 2
    out = {"mid": mid, "spread_bp": (a[0, 0] - b[0, 0]) / mid * 1e4,
           "bid1_usd": b[0, 0] * b[0, 1], "ask1_usd": a[0, 0] * a[0, 1]}
    db, da = 1 - b[:, 0] / mid, a[:, 0] / mid - 1
    nb, na = b[:, 0] * b[:, 1], a[:, 0] * a[:, 1]
    for w in DEPTHS:
        key = f"{w * 100:g}".replace(".", "_")
        bu, au = float(nb[db <= w].sum()), float(na[da <= w].sum())
        out[f"bid_{key}"], out[f"ask_{key}"] = bu, au
        out[f"imb_{key}"] = bu / (bu + au) if bu + au > 0 else None
    out["covered_bid"], out["covered_ask"] = float(db.max()), float(da.max())     # how deep the snapshot reached
    return out

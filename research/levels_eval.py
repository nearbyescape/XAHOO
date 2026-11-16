"""Support / resistance: what the levels are worth, measured on Binance 1m data (2024-01 -> 2026-10).

1. Reach table. For each horizon, the chance that price trades k 68%-bands above (or below) the current price
   at some point within the horizon, k = 0 ... 4. The screen uses it to say "chance price reaches this level".
2. Hold test. Every 4 hours, compute the levels exactly as the live server does (last 7 days only). Follow the
   nearest resistance and support for 24 hours. When price first touches the level, was it back on the near
   side 15 and 60 minutes later ("held")? Compare with control levels: arbitrary prices at the same distance
   (distances shuffled between dates). If real levels hold no more often than the controls, they are just
   reference prices.

Writes models/levels.json (reach tables + hold results) and prints a summary.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from xahoo.levels import find_levels  # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
METALS = ["XAUUSDT", "XAGUSDT"]
H = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
K = np.round(np.arange(0, 4.001, 0.1), 2)
START, END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-10-31", tz="UTC")


def load(sym):
    d = pd.read_parquet(ROOT / f"data/binance/{sym}_1m.parquet", columns=["high", "low", "close", "volume"])
    d = d[d.index >= START - pd.Timedelta(days=8)]
    d = d[~d.index.duplicated()].asfreq("1min")
    d["close"] = d["close"].ffill()
    for c in ("high", "low"):
        d[c] = d[c].fillna(d["close"])
    d["volume"] = d["volume"].fillna(0.0)
    return d


def reach_samples(d: pd.DataFrame, step: int = 15) -> dict:
    lc = np.log(d["close"].to_numpy())
    sig = pd.Series(lc).diff().rolling(1440, min_periods=1000).std().to_numpy()
    hi, lo = d["high"].to_numpy(), d["low"].to_numpy()
    t = d.index
    ok = (t >= START) & (t <= END)
    out = {}
    for h, n in H.items():
        fmax = pd.Series(hi[::-1]).rolling(n, min_periods=n).max().to_numpy()[::-1]    # max over [i, i+n-1]
        fmin = pd.Series(lo[::-1]).rolling(n, min_periods=n).min().to_numpy()[::-1]
        fmax = np.concatenate([fmax[1:], [np.nan]])                                       # -> [i+1, i+n]
        fmin = np.concatenate([fmin[1:], [np.nan]])
        end = np.concatenate([lc[n:], np.full(n, np.nan)])
        idx = np.nonzero(ok)[0][::step]
        s = sig[idx] * math.sqrt(n)
        rows = pd.DataFrame({"s": s, "up": np.log(fmax[idx]) - lc[idx], "dn": lc[idx] - np.log(fmin[idx]),
                             "u": np.abs(end[idx] - lc[idx]) / s}).dropna()
        out[h] = rows[rows["s"] > 0]
    return out


def reach_table(samples: list[dict]) -> dict:
    tab = {"k": K.tolist()}
    for h in H:
        r = pd.concat([s[h] for s in samples])
        c68 = float(r["u"].quantile(0.68))
        b = c68 * r["s"].to_numpy()
        tab[h] = {"c68": round(c68, 4), "n": len(r)}
        for side in ("up", "dn"):
            x = r[side].to_numpy() / b
            tab[h]["up" if side == "up" else "down"] = [round(float((x >= k).mean()), 4) for k in K]
    return tab


def hold_events(sym: str, d: pd.DataFrame, every: int = 240) -> list[dict]:
    ts = np.asarray((d.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1), dtype=np.int64)
    hi, lo, cl, vo = (d[c].to_numpy() for c in ("high", "low", "close", "volume"))
    first = np.searchsorted(d.index, START)
    last = np.searchsorted(d.index, END) - 1500
    ev = []
    for i in range(max(first, 10080), last, every):
        sl = slice(i - 10079, i + 1)
        lv = find_levels(ts[sl], hi[sl], lo[sl], cl[sl], vo[sl])
        if lv["day_sigma"] is None:
            continue
        for side, key in (("res", "resistance"), ("sup", "support")):
            if lv[key]:
                x = lv[key][0]
                ev.append({"sym": sym, "i": i, "side": side, "dist_sig": x["dist_sig"], "dsig": lv["day_sigma"],
                           "strength": x["strength"], "price": cl[i]})
    return ev


def outcome(hi, lo, cl, i, side, level):
    """First touch within 24h, then where price is 15 and 60 minutes later."""
    w = hi[i + 1:i + 1441] >= level if side == "res" else lo[i + 1:i + 1441] <= level
    if not w.any():
        return {"touch": 0, "t": None, "held15": None, "held60": None}
    j = i + 1 + int(np.argmax(w))
    if j + 60 >= len(cl):
        return {"touch": 1, "t": j - i, "held15": None, "held60": None}
    if side == "res":
        return {"touch": 1, "t": j - i, "held15": int(cl[j + 15] < level), "held60": int(cl[j + 60] < level)}
    return {"touch": 1, "t": j - i, "held15": int(cl[j + 15] > level), "held60": int(cl[j + 60] > level)}


def main():
    out = {"period": f"{START.date()} to {END.date()}", "k": K.tolist()}
    samples, metal_samples, events = [], [], []
    data = {}
    for sym in COINS + METALS:
        d = load(sym)
        data[sym] = d
        (metal_samples if sym in METALS else samples).append(reach_samples(d))
        if sym in COINS:
            e = hold_events(sym, d)
            events += e
            print(f"{sym}: {len(e)} level events", flush=True)
    out["reach"] = {"coin": reach_table(samples), "metal": reach_table(metal_samples)}

    ev = pd.DataFrame(events)
    rng = np.random.default_rng(7)
    rows = []
    for side in ("res", "sup"):
        e = ev[ev["side"] == side].reset_index(drop=True)
        ctrl = e["dist_sig"].to_numpy()[rng.permutation(len(e))]
        for r, cd in zip(e.itertuples(), ctrl):
            d = data[r.sym]
            hi, lo, cl = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
            lvl = r.price * math.exp(r.dist_sig * r.dsig)
            o = outcome(hi, lo, cl, r.i, side, lvl)
            rows.append({"side": side, "kind": "level", "strength": r.strength, "dist_sig": r.dist_sig, **o})
            lc = r.price * math.exp(cd * r.dsig)
            o = outcome(hi, lo, cl, r.i, side, lc)
            rows.append({"side": side, "kind": "control", "strength": r.strength, "dist_sig": cd, **o})
    res = pd.DataFrame(rows)
    hold = {}
    for (side, kind), g in res.groupby(["side", "kind"]):
        t = g[g["touch"] == 1]
        hold.setdefault(side, {})[kind] = {
            "n": len(g), "touched_24h": round(float(g["touch"].mean()), 4), "touches": len(t),
            "held15": round(float(t["held15"].dropna().mean()), 4), "held60": round(float(t["held60"].dropna().mean()), 4),
            "by_strength": {int(s): {"touches": len(gs), "held60": round(float(gs["held60"].dropna().mean()), 4)}
                            for s, gs in t.groupby("strength")}}
    out["hold"] = hold
    # standard error of a difference of two proportions near 0.5
    for side in hold:
        a, b = hold[side]["level"], hold[side]["control"]
        se = math.sqrt(0.25 / max(a["touches"], 1) + 0.25 / max(b["touches"], 1))
        hold[side]["diff60"] = round(a["held60"] - b["held60"], 4)
        hold[side]["diff60_se"] = round(se, 4)
    (ROOT / "models/levels.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"hold": hold, "reach_1h_up": out["reach"]["coin"]["1h"]["up"][::5],
                      "reach_1h_c68": out["reach"]["coin"]["1h"]["c68"]}, indent=1))


if __name__ == "__main__":
    main()

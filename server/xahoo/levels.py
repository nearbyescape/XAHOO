"""Support and resistance levels from the last 7 days of 1-minute bars.

Candidate prices come from five places, each with a weight:
  swing high / low on 15-minute bars (2 hours either side)        1.0
  swing high / low on 1-hour bars (6 hours either side)            2.0
  previous UTC day's high / low                                    2.0
  7-day high / low                                                 1.5
  volume node (price where unusually much volume traded)       1.0-2.0
Candidates closer together than `tol` (about 0.12 of a day's typical move) are merged into one level. Each later
15-minute bar that reached into the level and closed back away from it ("a reaction") adds 0.4. Newer swings
count a little more than old ones. Strength 1-3 comes from the total score (thresholds 6.5 and 11 split the
levels roughly 30 / 45 / 25). Strength measures confluence - how many reasons point at the price - not
reliability: in testing, stronger levels did not hold better.

The levels are reference prices, not predictions. research/levels_eval.py measures how often price turns back
at them compared with arbitrary prices the same distance away, and how often price reaches a level within each
horizon; both results ship in models/levels.json.

Everything is causal: a swing needs its right-hand bars to be complete before it counts.
"""
from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

SRC_LABEL = {"s15": "15m swing", "s60": "1h swing", "pdh": "prior-day high", "pdl": "prior-day low",
             "wkh": "7-day high", "wkl": "7-day low", "vol": "volume node"}


def _blocks(a: np.ndarray, m: int, how: str) -> np.ndarray:
    k = len(a) // m * m
    r = a[len(a) - k:].reshape(-1, m)
    return {"max": r.max(1), "min": r.min(1), "sum": r.sum(1), "last": r[:, -1]}[how]


def _pivots(x: np.ndarray, L: int, high: bool) -> np.ndarray:
    """Indices i (L <= i < len-L) where x[i] is the extreme of x[i-L : i+L+1]."""
    if len(x) < 2 * L + 1:
        return np.array([], dtype=int)
    w = sliding_window_view(x, 2 * L + 1)
    ext = w.max(1) if high else w.min(1)
    idx = np.nonzero(x[L:len(x) - L] == ext)[0] + L
    return idx


def find_levels(ts: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray,
                price: float | None = None, per_side: int = 3, max_dist_days: float = 3.0) -> dict:
    """ts in seconds (bar open time), arrays of closed 1m bars, oldest first (ideally 7 days = 10,080 bars).
    Returns {"tol", "day_sigma", "resistance": [...], "support": [...]} with levels nearest first."""
    n = len(close)
    out = {"tol": None, "day_sigma": None, "resistance": [], "support": []}
    if n < 1500:
        return out
    price = float(close[-1]) if price is None or not math.isfinite(price) else float(price)
    lp = math.log(price)
    r1 = np.diff(np.log(close[-1441:]))
    dsig = float(np.nanstd(r1)) * math.sqrt(1440)
    if not math.isfinite(dsig) or dsig <= 0:
        return out
    tol = max(0.12 * dsig, 0.0006)
    lh, ll, lc = np.log(high), np.log(low), np.log(close)

    cand = []                                   # (log price, weight, source)
    # swings on 15m and 1h bars
    for m, L, w, src in ((15, 8, 1.0, "s15"), (60, 6, 2.0, "s60")):
        h, l = _blocks(lh, m, "max"), _blocks(ll, m, "min")
        nb = len(h)
        for idx in _pivots(h, L, True):
            cand.append((h[idx], w * (0.7 + 0.3 * idx / nb), src))
        for idx in _pivots(l, L, False):
            cand.append((l[idx], w * (0.7 + 0.3 * idx / nb), src))
    # previous UTC day and 7-day extremes
    day = ts // 86400
    prev = day == day[-1] - 1
    if prev.any():
        cand.append((lh[prev].max(), 2.0, "pdh"))
        cand.append((ll[prev].min(), 2.0, "pdl"))
    cand.append((lh.max(), 1.5, "wkh"))
    cand.append((ll.min(), 1.5, "wkl"))
    # volume nodes: volume by price, in bins of tol/2
    tp = (lh + ll + lc) / 3
    lo_, hi_ = tp.min(), tp.max()
    nbins = int((hi_ - lo_) / (tol / 2)) + 1
    if nbins >= 7:
        hist, edges = np.histogram(tp, bins=nbins, range=(lo_, hi_ + 1e-12), weights=vol)
        sm = np.convolve(hist, [0.25, 0.5, 0.25], mode="same")
        nz = sm[sm > 0]
        if len(nz):
            med, top = float(np.median(nz)), float(sm.max())
            peaks = [i for i in range(1, nbins - 1) if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] >= 1.6 * med]
            peaks = sorted(peaks, key=lambda i: -sm[i])[:6]
            for i in peaks:
                cand.append(((edges[i] + edges[i + 1]) / 2, 1.0 + sm[i] / top, "vol"))

    if not cand:
        return out
    cand.sort(key=lambda c: c[0])
    clusters: list[list] = []
    for c in cand:
        if clusters:
            cl = clusters[-1]
            center = sum(x[0] * x[1] for x in cl) / sum(x[1] for x in cl)
            if c[0] - center <= tol:
                cl.append(c)
                continue
        clusters.append([c])

    # reactions on 15m bars: reached into the level's zone and closed back out on the side it came from
    h15, l15, c15 = _blocks(lh, 15, "max"), _blocks(ll, 15, "min"), _blocks(lc, 15, "last")
    o15 = np.concatenate([[c15[0]], c15[:-1]])
    levels = []
    for cl in clusters:
        wsum = sum(x[1] for x in cl)
        lv = sum(x[0] * x[1] for x in cl) / wsum
        half = tol / 2
        rej_dn = (h15 >= lv - half) & (o15 < lv - half) & (c15 < lv - half)     # came from below, turned down
        rej_up = (l15 <= lv + half) & (o15 > lv + half) & (c15 > lv + half)     # came from above, turned up
        reactions = int(rej_dn.sum() + rej_up.sum())
        score = wsum + 0.4 * min(reactions, 8)
        d = lv - lp
        if abs(d) < 0.25 * tol or abs(d) > max_dist_days * dsig:
            continue
        srcs = sorted({x[2] for x in cl}, key=list(SRC_LABEL).index)
        levels.append({"price": float(math.exp(lv)), "dist": float(d), "dist_sig": float(d / dsig),
                       "score": round(float(score), 2), "strength": 3 if score >= 11.0 else 2 if score >= 6.5 else 1,
                       "reactions": reactions, "sources": [SRC_LABEL[s] for s in srcs]})
    res = sorted([x for x in levels if x["dist"] > 0], key=lambda x: x["dist"])[:per_side]
    sup = sorted([x for x in levels if x["dist"] < 0], key=lambda x: -x["dist"])[:per_side]
    out.update(tol=tol, day_sigma=dsig, resistance=res, support=sup)
    return out


def reach_prob(table: dict | None, h: str, side: str, k: float) -> float | None:
    """Measured chance that price trades at a level k 68%-bands away within horizon h (side 'up' or 'down')."""
    if not table or h not in table:
        return None
    t = table[h][side]
    return float(np.interp(k, table["k"], t, right=t[-1]))

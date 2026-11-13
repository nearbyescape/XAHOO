"""Trade outcome tracker: walks 1m bars after entry and applies the management
rules (partials at TP1/TP2/TP3, SL to entry after TP1). Shared by backtests
and by the live tracker (which feeds it bar by bar)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Outcome:
    result: str          # SL | BE | TP1 | TP2 | TP3 | EXPIRED
    r: float             # realised R multiple after spread
    tp_hits: int         # how many targets were reached (0-3)
    exit_idx: int        # index into the 1m arrays of the exit bar
    exit_price: float
    mfe_r: float         # max favourable excursion, R
    mae_r: float         # max adverse excursion, R


def simulate(lo: np.ndarray, hi: np.ndarray, cl: np.ndarray, start: int, end: int, d: int,
             entry: float, sl: float, tps: tuple[float, float, float], partials: tuple[float, float, float],
             spread: float, be_after_tp1: bool = True, be_at_r: float | None = None) -> Outcome:
    """Bars are BID prices. Longs exit at bid, shorts at ask (= bid + spread).

    Within one bar, if the stop and a target are both touched, the stop is assumed
    to have come first (conservative).
    be_at_r: move the stop to entry once price has moved this many R in favour
    ("cost to cost"); takes effect from the next bar.
    """
    risk = abs(entry - sl)
    off = 0.0 if d == 1 else spread           # convert bid bar to the side we exit on
    stop = sl
    remaining, realized, stage = 1.0, 0.0, 0
    mfe = mae = 0.0
    end = min(end, len(lo))
    for i in range(start, end):
        bl, bh = lo[i] + off, hi[i] + off
        fav = (bh - entry) if d == 1 else (entry - bl)
        adv = (entry - bl) if d == 1 else (bh - entry)
        mfe, mae = max(mfe, fav / risk), max(mae, adv / risk)
        stopped = (bl <= stop) if d == 1 else (bh >= stop)
        if stopped:
            realized += remaining * (stop - entry) * d / risk
            res = ("BE" if stop == entry else "SL") if stage == 0 else ("BE" if stage == 1 else f"TP{stage}")
            return Outcome(res, round(realized, 3), stage, i, stop, round(mfe, 2), round(mae, 2))
        while stage < 3:
            t = tps[stage]
            if (bh >= t) if d == 1 else (bl <= t):
                realized += partials[stage] * (t - entry) * d / risk
                remaining -= partials[stage]
                stage += 1
                if stage == 1 and be_after_tp1:
                    stop = entry
            else:
                break
        if remaining <= 1e-9:
            return Outcome("TP3", round(realized, 3), 3, i, tps[2], round(mfe, 2), round(mae, 2))
        if be_at_r is not None and mfe >= be_at_r and (stop - entry) * d < 0:
            stop = entry
    i = end - 1
    px = cl[i] + off
    realized += remaining * (px - entry) * d / risk
    return Outcome("EXPIRED" if stage == 0 else f"TP{stage}", round(realized, 3), stage, i, px,
                   round(mfe, 2), round(mae, 2))


@dataclass
class ScaleOutcome:
    result: str          # SL | BE | TP | TIME
    r: float             # in units of ONE lot's initial risk, after spread
    lots: int            # 1 or 2
    add_idx: int | None  # index of the bar where lot 2 filled
    be_idx: int | None   # index of the bar after which the stop sits at the average entry
    exit_idx: int
    exit_price: float
    mfe_r: float
    mae_r: float


def simulate_scalein(lo: np.ndarray, hi: np.ndarray, cl: np.ndarray, start: int, end: int, d: int,
                     entry: float, sl: float, tp: float, add_px: float | None, spread: float,
                     be_at_r: float | None = 1.0, trail: np.ndarray | None = None,
                     trail_buf: float = 0.0) -> ScaleOutcome:
    """Trader-style position: 1 lot at entry, a 2nd lot when price returns to `add_px` (limit, filled at touch),
    one shared stop, one target. Once price has moved `be_at_r` R in favour (from the first entry) the stop moves
    to the average entry. Same-bar ambiguity is resolved against us: an add and a stop in the same bar both count.
    Bars are BID; shorts trade at ask (bid + spread).
    trail: optional per-bar trailing level (e.g. 5m EMA12 known at each 1m bar); once the stop is at the average
    entry it follows trail -/+ trail_buf, only ever tightening."""
    off = 0.0 if d == 1 else spread
    risk = abs(entry - sl)
    lots = [(entry, 1.0)]
    stop, add_i, be_i = sl, None, None
    mfe = mae = 0.0
    end = min(end, len(lo))
    for k in range(start, end):
        l, h = lo[k] + off, hi[k] + off
        mfe = max(mfe, ((h - entry) if d == 1 else (entry - l)) / risk)
        mae = max(mae, ((entry - l) if d == 1 else (h - entry)) / risk)
        if add_i is None and add_px is not None and np.isfinite(add_px) and ((l <= add_px) if d == 1 else (h >= add_px)):
            lots.append((add_px, 1.0))
            add_i = k
        if (l <= stop) if d == 1 else (h >= stop):
            r = sum(q * (stop - px) * d for px, q in lots) / risk
            res = "SL" if be_i is None else ("TRAIL" if r > 0.05 else "BE")
            return ScaleOutcome(res, round(r, 3), len(lots), add_i, be_i, k, stop,
                                round(mfe, 2), round(mae, 2))
        if (h >= tp) if d == 1 else (l <= tp):
            r = sum(q * (tp - px) * d for px, q in lots) / risk
            return ScaleOutcome("TP", round(r, 3), len(lots), add_i, be_i, k, tp, round(mfe, 2), round(mae, 2))
        if be_i is None and be_at_r is not None and mfe >= be_at_r:
            stop = sum(px * q for px, q in lots) / sum(q for _, q in lots)
            be_i = k
        if trail is not None and be_i is not None and np.isfinite(trail[k]):
            c = trail[k] - d * trail_buf
            if (c - stop) * d > 0:
                stop = c
    k = end - 1
    px = cl[k] + off
    r = sum(q * (px - p0) * d for p0, q in lots) / risk
    return ScaleOutcome("TIME", round(r, 3), len(lots), add_i, be_i, k, px, round(mfe, 2), round(mae, 2))

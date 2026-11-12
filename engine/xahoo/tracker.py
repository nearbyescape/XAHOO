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
             spread: float, be_after_tp1: bool = True) -> Outcome:
    """Bars are BID prices. Longs exit at bid, shorts at ask (= bid + spread).

    Within one bar, if the stop and a target are both touched, the stop is assumed
    to have come first (conservative).
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
            res = "SL" if stage == 0 else ("BE" if stage == 1 else f"TP{stage}")
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
    i = end - 1
    px = cl[i] + off
    realized += remaining * (px - entry) * d / risk
    return Outcome("EXPIRED" if stage == 0 else f"TP{stage}", round(realized, 3), stage, i, px,
                   round(mfe, 2), round(mae, 2))

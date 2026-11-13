"""Exit study on the live strategy (StrategyParams.trader(): his setup + scale-in). Same entries, five exits,
fixed in advance (docs/BACKTEST.md run 15). Develop on 2025, confirm on 2024 and 2026.
usage: python research/exits.py [SYMBOL,SYMBOL ...]"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo import indicators as ind
from xahoo.config import StrategyParams, spec_for
from xahoo.data import dukascopy
from xahoo.data.resample import resample
from xahoo.engine import generate

CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
PERIODS = {"2024": (date(2024, 2, 10), date(2024, 12, 31)), "2025 (dev)": (date(2025, 2, 10), date(2025, 12, 31)),
           "2026": (date(2026, 2, 10), date(2026, 11, 11))}
MAX_HOLD = 300   # minutes
CAP_R = 5.0      # trailing exits are capped at 5R from the first entry


def ema5_on_1m(m1: pd.DataFrame) -> np.ndarray:
    """EMA12 of CLOSED 5m bars, as known at the open of each 1m bar (causal)."""
    f = resample(m1, "5m")
    e = ind.ema(f["close"], 12)
    s = pd.Series(e.values, index=f["close_time"])
    return s.reindex(m1.index, method="ffill").to_numpy()


def run_exit(mode, lo, hi, cl, ema, i, b, d, entry, sl, add_px, spread, atr):
    """R in units of the FIRST lot's risk. Pessimistic same-bar rules: an add fills before a stop; stops before targets.

    E0 both lots at 2R · E1 trail EMA12 after +1R (cap 5R) · E2 lot 1 at 1R, lot 2 trails (cap 5R)
    E3 lot 1 at 1R, lot 2 at 3R · E4 = E0 + exit at market if +1R not reached within 60 min.
    Stop moves to the average price of the open lots at +1R (all modes). If lot 1 has already exited
    and lot 2 was never added, the add is cancelled."""
    off = 0.0 if d == 1 else spread
    risk = abs(entry - sl)
    tgt = {"E0": (2, 2), "E4": (2, 2), "E1": (CAP_R, CAP_R), "E2": (1, CAP_R), "E3": (1, 3)}[mode]
    t1, t2 = entry + d * tgt[0] * risk, entry + d * tgt[1] * risk
    trail = mode in ("E1", "E2")
    lots = [[entry, None]]                       # [price, exit]
    stop, be, mfe = sl, False, 0.0
    hit = lambda l, h, lvl: (h >= lvl) if d == 1 else (l <= lvl)
    stopped = lambda l, h, lvl: (l <= lvl) if d == 1 else (h >= lvl)
    end = min(b, len(cl))
    for k in range(i, end):
        l, h = lo[k] + off, hi[k] + off
        if len(lots) == 1 and lots[0][1] is None and add_px is not None and ((l <= add_px) if d == 1 else (h >= add_px)):
            lots.append([add_px, None])
        if stopped(l, h, stop):
            for lt in lots:
                if lt[1] is None:
                    lt[1] = stop
            break
        if lots[0][1] is None and hit(l, h, t1):
            lots[0][1] = t1
        if len(lots) > 1 and lots[1][1] is None and hit(l, h, t2):
            lots[1][1] = t2
        if all(lt[1] is not None for lt in lots):
            break
        mfe = max(mfe, ((h - entry) if d == 1 else (entry - l)) / risk)
        if not be and mfe >= 1.0:
            open_px = [lt[0] for lt in lots if lt[1] is None]
            stop = sum(open_px) / len(open_px)
            be = True
        if mode == "E4" and not be and (k - i) >= 60:
            break
        if trail and be and np.isfinite(ema[k]):
            c = ema[k] - d * 0.1 * atr
            if (c - stop) * d > 0:
                stop = c
    for lt in lots:
        if lt[1] is None:
            lt[1] = cl[k] + off
    return sum((x - p0) * d for p0, x in lots) / risk, len(lots)


def main():
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["XAUUSD", "XAGUSD"]
    p = StrategyParams.trader()
    rows = []
    for label, (a, b_) in PERIODS.items():
        data = {}
        for s in syms:
            try:
                data[s] = dukascopy.load(s, CACHE, a - timedelta(days=60), b_)
            except FileNotFoundError:
                pass
        data = {s: m for s, m in data.items() if len(m) > 50_000}
        if not data:
            continue
        cand = generate(data, p, p.exec_tfs)
        if cand.empty:
            continue
        cand = cand[cand["close_time"] >= pd.Timestamp(a, tz="UTC")].sort_values("close_time")
        for sym, m1 in data.items():
            lo, hi, cl, idx = m1.low.to_numpy(), m1.high.to_numpy(), m1.close.to_numpy(), m1.index
            ema = ema5_on_1m(m1)
            spread = spec_for(sym).spread
            busy_until = None
            for r in cand[cand.symbol == sym].itertuples():
                if busy_until is not None and r.close_time < busy_until:
                    continue
                i = idx.searchsorted(r.close_time)
                b = idx.searchsorted(r.close_time + pd.Timedelta(minutes=MAX_HOLD))
                if i >= len(idx) - 1:
                    continue
                add = r.add_price if np.isfinite(r.add_price) else None
                for mode in ("E0", "E1", "E2", "E3", "E4"):
                    R, n = run_exit(mode, lo, hi, cl, ema, i, b, r.dir, r.entry, r.sl, add, spread, r.atr)
                    rows.append({"t": r.close_time, "period": label, "symbol": sym, "exit": mode, "R": R, "lots": n})
                busy_until = idx[min(b, len(idx) - 1)]
    df = pd.DataFrame(rows).sort_values("t")
    g = df.groupby(["exit", "period"])
    out = pd.DataFrame({
        "trades": g.size(), "win%": g.R.apply(lambda x: round((x > 0.05).mean() * 100, 1)),
        "green%": g.R.apply(lambda x: round((x > -0.05).mean() * 100, 1)),
        "avg R": g.R.mean().round(3), "net R": g.R.sum().round(1),
        "max DD": g.R.apply(lambda x: round((x.cumsum() - x.cumsum().cummax()).min(), 1)),
        "worst": g.R.min().round(2)})
    pd.set_option("display.width", 200)
    print(out.to_string())


if __name__ == "__main__":
    main()

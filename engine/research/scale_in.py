"""Trader's scale-in (add a 2nd lot at EMA12) on his setup: impulse 5ATR + daily trend, 5m. Rules fixed in advance.
Run on 2025, 2024 and 2026 in one go (no tuning)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from trend_pullback import daily_context
from xahoo import features
from xahoo.config import SYMBOLS, StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import generate
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"


def sim(lo, hi, cl, i, b, d, entry, sl, tp, add_px, spread, be_r=1.0):
    """Units in R of ONE lot's initial risk. Same-bar ambiguity resolved against us (add fills, then stop)."""
    off = 0.0 if d == 1 else spread
    risk = abs(entry - sl)
    lots = [(entry, 1.0)]
    stop, added, moved = sl, False, False
    for k in range(i, b):
        l, h = lo[k] + off, hi[k] + off
        if not added and add_px is not None and ((l <= add_px) if d == 1 else (h >= add_px)):
            lots.append((add_px, 1.0)); added = True
        if (l <= stop) if d == 1 else (h >= stop):
            return sum(q * (stop - p) * d for p, q in lots) / risk, len(lots), "SL" if not moved else "BE"
        if (h >= tp) if d == 1 else (l <= tp):
            return sum(q * (tp - p) * d for p, q in lots) / risk, len(lots), "TP"
        fav = (h - entry) if d == 1 else (entry - l)
        if not moved and fav >= be_r * risk:
            avg = sum(p * q for p, q in lots) / sum(q for _, q in lots)
            stop, moved = avg, True
    px = cl[b - 1] + off
    return sum(q * (px - p) * d for p, q in lots) / risk, len(lots), "TIME"


import itertools
IMPULSES = [float(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["5"])]
TPS = [float(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["2"])]
H4_FILTER = len(sys.argv) > 3 and sys.argv[3] == "h4"
from xahoo import indicators as ind
from xahoo.data.resample import align_closed, resample
PERIODS = {"2024": (date(2024, 2, 10), date(2024, 12, 31)), "2025 (dev)": (date(2025, 2, 10), date(2025, 12, 31)),
           "2026": (date(2026, 2, 10), date(2026, 11, 11))}
rows = []
for label, (a, b_) in PERIODS.items():
    data = {s: dukascopy.load(s, CACHE, a - timedelta(days=40), b_) for s in ("XAUUSD", "XAGUSD")}
    ctx = {}
    h4lv = {}
    for sym, m1 in data.items():
        h4 = resample(m1, "4h").join(ind.structure(resample(m1, "4h"), k=2))
        h4lv[sym] = h4
        ctx[sym] = (daily_context(m1)["trend"],
                    features.build(m1, "5m", StrategyParams()).set_index("close_time")["ema_fast"],
                    m1.low.to_numpy(), m1.high.to_numpy(), m1.close.to_numpy(), m1.index)
    for K, TPR in itertools.product(IMPULSES, TPS):
        p = StrategyParams()
        p.enabled_setups, p.exec_tfs, p.trade_asia, p.ip_impulse_atr = ("impulse_pullback",), ("5m",), True, K
        p.tp_r = (TPR, TPR, TPR)
        c = generate(data, p, p.exec_tfs)
        c = c[c["close_time"] >= pd.Timestamp(a, tz="UTC")]
        for sym in data:
            dt, f, lo, hi, cl, idx = ctx[sym]
            last_exit = None
            cs = c[c.symbol == sym]
            if H4_FILTER and len(cs):
                lv = align_closed(h4lv[sym], cs["close_time"], ["last_sh", "last_sl"], "h4_")
                cs = cs.join(lv)
            for r in cs.itertuples():
                if dt.reindex([r.close_time.normalize()]).iloc[0] != r.dir:
                    continue
                if H4_FILTER:
                    lvl = r.h4_last_sl if r.dir == -1 else r.h4_last_sh     # 4h support below a short / resistance above a long
                    if np.isfinite(lvl) and (r.entry - lvl) * r.dir < 0 and abs(lvl - r.entry) < abs(r.tp1 - r.entry):
                        continue
                if last_exit is not None and r.close_time < last_exit:
                    continue
                i = idx.searchsorted(r.close_time); b = idx.searchsorted(r.close_time + pd.Timedelta(minutes=300))
                e12 = f.get(r.close_time, np.nan)
                between = np.isfinite(e12) and (r.sl < e12 < r.entry if r.dir == 1 else r.entry < e12 < r.sl)
                add_px = e12 if between else r.entry - r.dir * 0.5 * r.risk
                for mode, ap in (("1 lot", None), ("scale-in", add_px)):
                    R, n, res = sim(lo, hi, cl, i, b, r.dir, r.entry, r.sl, r.tp1, ap, SYMBOLS[sym].spread)
                    rows.append({"variant": f"impulse {K:.0f} | TP {TPR}R | {mode}", "period": label,
                                 "symbol": sym, "R": R, "lots": n})
                last_exit = idx[min(b, len(idx) - 1)]
df = pd.DataFrame(rows)
g = df.groupby(["variant", "period"])
out = pd.DataFrame({"trades": g.size(), "win%": g.R.apply(lambda x: round((x > 0.05).mean() * 100, 1)),
                    "avg R": g.R.mean().round(3), "net R": g.R.sum().round(1),
                    "worst R": g.R.min().round(1), "added%": g.lots.apply(lambda x: round((x > 1).mean() * 100, 1))})
pd.set_option("display.width", 200)
print(out.to_string())

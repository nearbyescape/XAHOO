"""Daily-trend + intraday pullback ("buy the dip in an up-trend, sell the rally in a down-trend").
One trade per symbol per day at most. Units are the daily ATR (14 days), so it scales with volatility.

Rules (all known at decision time):
  trend   : yesterday's close vs 50-day EMA and 20-day return (time-series momentum). +1 / -1 / 0
  pullback: during 07:00-17:00 UTC, price trades `depth` x dATR against the trend from today's extreme
  entry   : at that moment (next 1m bar), in the trend direction, plus spread
  exit    : TP = tp x dATR, SL = sl x dATR, or market close of the session at 20:00 UTC
usage: python research/trend_pullback.py 2025 [2024 ...]"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo.config import SYMBOLS
from xahoo.data import dukascopy
from xahoo.tracker import simulate
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"


def daily_context(m1):
    d = m1.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = d[d.index.dayofweek < 5]
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    d["datr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)            # known at the open
    ema50 = d.close.ewm(span=50, adjust=False).mean()
    mom20 = d.close / d.close.shift(20) - 1
    t = np.where((d.close > ema50) & (mom20 > 0), 1, np.where((d.close < ema50) & (mom20 < 0), -1, 0))
    d["trend"] = pd.Series(t, index=d.index).shift(1)                         # yesterday's state
    return d


def run(sym, years, depth, tp, sl, use_trend=True, win=(7, 17)):
    m1 = dukascopy.load(sym, CACHE)
    d = daily_context(m1)
    lo, hi, cl, idx = m1.low.to_numpy(), m1.high.to_numpy(), m1.close.to_numpy(), m1.index
    spread = SYMBOLS[sym].spread
    rows = []
    for day, ctx in d.iterrows():
        if day.year not in years or np.isnan(ctx.datr) or (use_trend and ctx.trend == 0):
            continue
        a, b = idx.searchsorted(day), idx.searchsorted(day + pd.Timedelta(hours=20))
        if b - a < 300:
            continue
        hrs = idx[a:b].hour
        seg_hi, seg_lo = np.maximum.accumulate(hi[a:b]), np.minimum.accumulate(lo[a:b])
        ok = (hrs >= win[0]) & (hrs < win[1])
        dirs = [int(ctx.trend)] if use_trend else [1, -1]
        best = None
        for dr in dirs:
            trig = (seg_hi - lo[a:b] >= depth * ctx.datr) if dr == 1 else (hi[a:b] - seg_lo >= depth * ctx.datr)
            j = np.flatnonzero(trig & ok)
            if len(j) and (best is None or j[0] < best[0]):
                best = (j[0], dr)
        if best is None:
            continue
        j, dr = best
        i = a + j + 1                                      # enter on the next minute
        if i >= b:
            continue
        entry = cl[a + j] + (spread if dr == 1 else 0.0)
        o = simulate(lo, hi, cl, i, b, dr, entry, entry - dr * sl * ctx.datr,
                     (entry + dr * tp * ctx.datr,) * 3, (1, 0, 0), spread, False)
        rows.append({"day": day, "dir": dr, "r": o.r, "result": o.result})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]]
    out = []
    for sym in ("XAUUSD", "XAGUSD"):
        for use_trend in (True, False):
            for depth in (0.3, 0.5):
                for tp, sl in ((0.15, 0.5), (0.25, 0.5), (0.25, 1.0), (0.4, 0.6), (0.5, 0.5)):
                    bt = run(sym, years, depth, tp, sl, use_trend)
                    if bt.empty:
                        continue
                    rr = bt.r
                    out.append({"sym": sym, "trend": use_trend, "depth": depth, "tp/sl": f"{tp}/{sl}",
                                "trades": len(bt), "win%": round((rr > 0).mean() * 100, 1),
                                "avg R": round(rr.mean(), 3), "avg %risk": round(rr.mean() * 100, 1),
                                "net R": round(rr.sum(), 1),
                                "maxDD R": round((rr.cumsum() - rr.cumsum().cummax()).min(), 1)})
    pd.set_option("display.width", 220)
    print(pd.DataFrame(out).to_string(index=False))

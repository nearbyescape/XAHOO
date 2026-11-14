"""Swing / position strategy candidates on 17 years of daily bars (2009-2026), textbook parameters, no tuning.

Costs: spread per round trip + overnight financing (CFD swap approximation: longs pay FIN_LONG %/yr of notional,
shorts FIN_SHORT %/yr). Signals use the daily close; orders fill at the NEXT day's open. Protective stops are
checked on the daily high/low (gap through the stop = filled at the open). R = initial stop distance.
usage: python research/swing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SW = Path(__file__).resolve().parents[2] / "data" / "swing"
SPREAD = {"XAUUSD": 0.30, "XAGUSD": 0.03}
FIN_LONG, FIN_SHORT = 0.05, 0.01
PERIODS = {"2009-2012 bull": ("2009", "2012"), "2013-2018 bear/range": ("2013", "2018"), "2019-2026 bull": ("2019", "2026")}


def load(sym, tf="1d"):
    if tf == "4h":
        h = pd.read_pickle(SW / f"{sym}_1h.pkl")
        d = h.resample("4h", offset="2h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    else:
        d = pd.read_pickle(SW / f"{sym}_{tf}.pkl").copy()
    return prep(d)


def prep(d):
    c = d["close"]
    tr = pd.concat([d.high - d.low, (d.high - c.shift()).abs(), (d.low - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 20, adjust=False).mean()
    for n in (5, 20, 50, 100, 200):
        d[f"sma{n}"] = c.rolling(n).mean()
    d["ema20"] = c.ewm(span=20, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    delta = c.diff()
    up, dn = delta.clip(lower=0), (-delta).clip(lower=0)
    d["rsi2"] = 100 - 100 / (1 + up.ewm(alpha=1 / 2, adjust=False).mean() / dn.ewm(alpha=1 / 2, adjust=False).mean())
    for n in (10, 20, 40, 55):
        d[f"hh{n}"] = d.high.rolling(n).max().shift(1)
        d[f"ll{n}"] = d.low.rolling(n).min().shift(1)
    d["mom252"] = c / c.shift(252) - 1
    return d.dropna()


def simulate(d, sym, entries, exit_fn, stop_atr, max_days=None, target_r=None, trail_atr=None,
             part_r=None, part_frac=0.5, be_after_part=False):
    """entries: Series of +1/-1/0 decided at the close of day t (enter at open t+1).
    exit_fn(d, i, dir, entry_i) -> True to exit at next open (evaluated at close of day i)."""
    o, h, l, c, atr = (d[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    e = entries.to_numpy()
    idx = d.index
    sp = SPREAD[sym]
    trades, i, n = [], 0, len(d)
    while i < n - 1:
        if e[i] == 0:
            i += 1
            continue
        dr = int(e[i])
        j = i + 1
        entry = o[j] + (sp if dr == 1 else 0)
        risk = stop_atr * atr[i]
        stop = entry - dr * risk
        tgt = entry + dr * target_r * risk if target_r else None
        best = entry
        banked, left = 0.0, 1.0
        exit_px, k = None, j
        while k < n:
            lo, hi = l[k], h[k] + (0 if dr == 1 else sp)
            if dr == 1 and lo <= stop:
                exit_px = min(o[k], stop) if k > j else stop
                break
            if dr == -1 and hi >= stop:
                exit_px = max(o[k] + sp, stop) if k > j else stop
                break
            if tgt is not None and ((dr == 1 and h[k] >= tgt) or (dr == -1 and l[k] + sp <= tgt)):
                exit_px = tgt
                break
            if part_r and left == 1.0:
                pt = entry + dr * part_r * risk
                if (dr == 1 and h[k] >= pt) or (dr == -1 and l[k] + sp <= pt):
                    banked, left = part_frac * part_r, 1.0 - part_frac
                    if be_after_part:
                        stop = max(stop, entry) if dr == 1 else min(stop, entry)
            if trail_atr:
                best = max(best, h[k]) if dr == 1 else min(best, l[k])
                ns = best - dr * trail_atr * atr[k]
                stop = max(stop, ns) if dr == 1 else min(stop, ns)
            if (max_days and k - j + 1 >= max_days) or exit_fn(d, k, dr, j):
                if k + 1 < n:
                    exit_px = o[k + 1] + (0 if dr == 1 else sp)
                    k += 1
                else:
                    exit_px = c[k]
                break
            k += 1
        if exit_px is None:
            exit_px, k = c[n - 1], n - 1
        days = max(0.04, (idx[k] - idx[j]).total_seconds() / 86400)
        fin = entry * (FIN_LONG if dr == 1 else FIN_SHORT) * days / 365
        r = banked + left * (exit_px - entry) * dr / risk - fin / risk
        trades.append({"sym": sym, "t": idx[j], "exit": idx[k], "dir": dr, "r": r, "days": days})
        i = k + 1 if k > i else i + 1
    return pd.DataFrame(trades)


# ----------------------------------------------------------------------------- strategies (textbook settings)
def s_donchian(d, long_only=False):          # Turtle "system 2": 55-day breakout, exit 20-day opposite, stop 2 ATR
    c = d.close
    ent = pd.Series(0, index=d.index)
    ent[c > d.hh55] = 1
    if not long_only:
        ent[c < d.ll55] = -1
    ex = lambda d, i, dr, j: (d.close.iat[i] < d.ll20.iat[i]) if dr == 1 else (d.close.iat[i] > d.hh20.iat[i])
    return ent, ex, dict(stop_atr=2.0)


def s_ma_trend(d, brk=20, trail=3.0):         # 50/200 trend with N-bar breakout entry, k-ATR chandelier trail
    up = (d.close > d.sma200) & (d.sma50 > d.sma200)
    dn = (d.close < d.sma200) & (d.sma50 < d.sma200)
    ent = pd.Series(0, index=d.index)
    ent[up & (d.close > d[f"hh{brk}"])] = 1
    ent[dn & (d.close < d[f"ll{brk}"])] = -1
    return ent, (lambda d, i, dr, j: False), dict(stop_atr=trail, trail_atr=trail)


def s_rsi2(d, both=True):                    # Connors RSI(2) pullback in the 200-day trend, exit above 5-day average
    ent = pd.Series(0, index=d.index)
    ent[(d.close > d.sma200) & (d.rsi2 < 10)] = 1
    if both:
        ent[(d.close < d.sma200) & (d.rsi2 > 90)] = -1
    ex = lambda d, i, dr, j: (d.close.iat[i] > d.sma5.iat[i]) if dr == 1 else (d.close.iat[i] < d.sma5.iat[i])
    return ent, ex, dict(stop_atr=3.0, max_days=10)


def s_3down(d):                              # three lower closes in an up-trend (mirror for down), exit on first strong close
    c = d.close
    dn3 = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    up3 = (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & (c.shift(2) > c.shift(3))
    ent = pd.Series(0, index=d.index)
    ent[(c > d.sma100) & dn3] = 1
    ent[(c < d.sma100) & up3] = -1
    ex = lambda d, i, dr, j: (d.close.iat[i] > d.high.iat[i - 1]) if dr == 1 else (d.close.iat[i] < d.low.iat[i - 1])
    return ent, ex, dict(stop_atr=2.5, max_days=7)


def s_ema_pullback(d):                       # trend (EMA20>EMA50, above SMA200), dip to EMA20 that closes back above; 2R target
    up = (d.ema20 > d.ema50) & (d.close > d.sma200)
    dn = (d.ema20 < d.ema50) & (d.close < d.sma200)
    ent = pd.Series(0, index=d.index)
    ent[up & (d.low <= d.ema20) & (d.close > d.ema20) & (d.close > d.open)] = 1
    ent[dn & (d.high >= d.ema20) & (d.close < d.ema20) & (d.close < d.open)] = -1
    return ent, (lambda d, i, dr, j: False), dict(stop_atr=1.5, target_r=2.0, max_days=15)


def s_tsmom(d):                              # 12-month time-series momentum, re-checked monthly (Moskowitz-Ooi-Pedersen)
    ent = pd.Series(0, index=d.index)
    ent[d.mom252 > 0] = 1
    ent[d.mom252 < 0] = -1
    ex = lambda d, i, dr, j: (i - j) >= 20
    return ent, ex, dict(stop_atr=4.0)


STRATS = {
    "T1 Donchian 55/20 trend (long+short)": lambda d: s_donchian(d),
    "T1L Donchian 55/20 trend (long only)": lambda d: s_donchian(d, True),
    "T2 50/200 trend + 20d breakout, 3ATR trail": s_ma_trend,
    "T3 12-month momentum, monthly": s_tsmom,
    "P1 RSI(2) pullback in 200d trend (long+short)": lambda d: s_rsi2(d),
    "P1L RSI(2) pullback in 200d trend (long only)": lambda d: s_rsi2(d, False),
    "P2 3 down closes in trend": s_3down,
    "P3 EMA20 pullback in trend, 2R target": s_ema_pullback,
}


def summarize(t):
    if t.empty:
        return {"trades": 0}
    r = t.r
    eq = r.cumsum()
    yrs = (t.exit.max() - t.t.min()).days / 365.25
    return {"trades": len(t), "per yr": round(len(t) / max(yrs, 0.1), 1), "win%": round((r > 0).mean() * 100, 1),
            "avg R": round(r.mean(), 3), "net R": round(r.sum(), 1), "R/yr": round(r.sum() / max(yrs, 0.1), 1),
            "PF": round(r[r > 0].sum() / -r[r < 0].sum(), 2) if (r < 0).any() else np.inf,
            "maxDD R": round((eq - eq.cummax()).min(), 1), "avg days": round(t.days.mean(), 1)}


def main():
    data = {s: load(s) for s in ("XAUUSD", "XAGUSD")}
    rows = []
    for name, fn in STRATS.items():
        allt = []
        for sym, d in data.items():
            ent, ex, kw = fn(d)
            t = simulate(d, sym, ent, ex, **kw)
            allt.append(t)
            rows.append({"strategy": name, "market": sym, "period": "ALL 2010-2026", **summarize(t)})
        t = pd.concat(allt).sort_values("t")
        for pn, (a, b) in PERIODS.items():
            rows.append({"strategy": name, "market": "both", "period": pn, **summarize(t[(t.t >= a) & (t.t <= f"{b}-12-31")])})
    df = pd.DataFrame(rows).set_index(["strategy", "market", "period"])
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    print(df.to_string())


if __name__ == "__main__":
    main()

"""Probability filter (PLAN v2, Track C): learn P(trade succeeds) for candidate entries, trade only high-P ones.

Candidates : every 15m close 07:00-17:00 UTC, both directions, both metals.
Structure  : TP = 0.2 x daily ATR, SL = 0.6 x daily ATR, flat at 20:00 UTC (built for a high hit rate:
             break-even win rate ~75% before costs, so the model must find > ~80% to make money).
Label      : 1 if the trade closes with profit (after spread).
Split      : train / validate / test by time (no shuffling). Final test is run once.
Policy     : per symbol per day, take the first candidate whose calibrated P >= threshold; at most 1 trade.
usage: python research/ml_filter.py --train 2025-02-10:2025-09-30 --valid 2025-10-01:2025-12-31 --test 2026-02-10:2026-11-11
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression

from trend_pullback import daily_context
from xahoo import features
from xahoo.config import SYMBOLS, StrategyParams
from xahoo.data import dukascopy

CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
TP, SL, FLAT_H = 0.2, 0.6, 20
OUT = Path(__file__).resolve().parents[2] / "data" / "ml"


def first_touch(lo, hi, cl, i, b, d, entry, tp, sl, spread):
    """R-multiple of a single trade (stop first if both in one bar). Prices BID; shorts exit at ask."""
    off = 0.0 if d == 1 else spread
    l, h = lo[i:b] + off, hi[i:b] + off
    risk = abs(entry - sl)
    if d == 1:
        hit_sl, hit_tp = l <= sl, h >= tp
    else:
        hit_sl, hit_tp = h >= sl, l <= tp
    js = np.argmax(hit_sl) if hit_sl.any() else len(l)
    jt = np.argmax(hit_tp) if hit_tp.any() else len(l)
    if js <= jt and js < len(l):
        return -1.0, i + js
    if jt < len(l):
        return abs(tp - entry) / risk, i + jt
    return (cl[b - 1] + off - entry) * d / risk, b - 1


def build_dataset(sym: str, p: StrategyParams, other: pd.DataFrame | None) -> pd.DataFrame:
    m1 = dukascopy.load(sym, CACHE)
    spread = SYMBOLS[sym].spread
    dctx = daily_context(m1)
    dctx["ema50"] = dctx["close"].ewm(span=50, adjust=False).mean().shift(1)
    dctx["mom20"] = (dctx["close"] / dctx["close"].shift(20) - 1).shift(1)
    dctx["prev_ret"] = ((dctx["close"] - dctx["open"]) / dctx["datr"]).shift(1)
    dctx["prev_close"] = dctx["close"].shift(1)
    f = features.build(m1, "15m", p)
    t = f["close_time"]
    day = t.dt.normalize()
    f = f[(t.dt.hour >= 7) & (t.dt.hour < 17) & day.isin(dctx.index)].copy()
    day = f["close_time"].dt.normalize()
    dc = dctx.reindex(pd.DatetimeIndex(day)).set_axis(f.index)
    # intraday state at decision time, from 1m bars of the same day up to the decision
    day_open = m1["open"].groupby(m1.index.normalize()).first()
    f["day_open"] = day_open.reindex(pd.DatetimeIndex(day)).values
    m1_hi = m1["high"].groupby(m1.index.normalize()).cummax()
    m1_lo = m1["low"].groupby(m1.index.normalize()).cummin()
    last_min = pd.DatetimeIndex(f["close_time"] - pd.Timedelta(minutes=1))
    f["intra_hi"] = m1_hi.reindex(last_min).values
    f["intra_lo"] = m1_lo.reindex(last_min).values
    if other is not None:
        o_day_open = other["open"].groupby(other.index.normalize()).first()
        o_last = other["close"].reindex(last_min, method="ffill").values
        o_dctx = daily_context(other)
        f["o_move"] = (o_last - o_day_open.reindex(pd.DatetimeIndex(day)).values) / o_dctx["datr"].reindex(pd.DatetimeIndex(day)).values
    else:
        f["o_move"] = 0.0
    lo, hi, cl, idx = m1["low"].to_numpy(), m1["high"].to_numpy(), m1["close"].to_numpy(), m1.index
    rows = []
    datr = dc["datr"].to_numpy()
    for k, (ts, r) in enumerate(f.iterrows()):
        da = datr[k]
        if not np.isfinite(da) or da <= 0:
            continue
        i = idx.searchsorted(r["close_time"])
        b = idx.searchsorted(r["close_time"].normalize() + pd.Timedelta(hours=FLAT_H))
        if b - i < 10:
            continue
        for d in (1, -1):
            entry = r["close"] + (spread if d == 1 else 0.0)
            rr, _ = first_touch(lo, hi, cl, i, b, d, entry, entry + d * TP * da, entry - d * SL * da, spread)
            c = r["close"]
            rows.append({
                "ts": r["close_time"], "symbol": sym, "dir": d, "R": rr, "y": int(rr > 0),
                "trend": d * dc["trend"].iat[k],
                "mom20": d * dc["mom20"].iat[k],
                "ema50_dist": d * (dc["prev_close"].iat[k] - dc["ema50"].iat[k]) / da,
                "prev_ret": d * dc["prev_ret"].iat[k],
                "from_open": d * (c - r["day_open"]) / da,
                "range_so_far": (r["intra_hi"] - r["intra_lo"]) / da,
                "pullback": (r["intra_hi"] - c) / da if d == 1 else (c - r["intra_lo"]) / da,
                "extension": (c - r["intra_lo"]) / da if d == 1 else (r["intra_hi"] - c) / da,
                "pdh_dist": d * (c - r["pdh"]) / da, "pdl_dist": d * (c - r["pdl"]) / da,
                "hour": r["close_time"].hour + r["close_time"].minute / 60, "weekday": r["close_time"].dayofweek,
                "e12": d * (c - r["ema_fast"]) / r["atr"], "e200": d * (c - r["ema_slow"]) / r["atr"],
                "adx": r["adx"], "bias15": d * r["bias"], "bias1h": d * r["1h_bias"], "bias4h": d * r["4h_bias"],
                "atr_ratio": r["atr"] / da, "press3": d * r["press3"], "rvol": r["rvol"],
                "o_move": d * r["o_move"], "is_gold": int(sym == "XAUUSD"),
            })
    return pd.DataFrame(rows)


FEATS = ["dir", "trend", "mom20", "ema50_dist", "prev_ret", "from_open", "range_so_far", "pullback", "extension",
         "pdh_dist", "pdl_dist", "hour", "weekday", "e12", "e200", "adx", "bias15", "bias1h", "bias4h",
         "atr_ratio", "press3", "rvol", "o_move", "is_gold"]


def window(df, spec):
    a, b = spec.split(":")
    return df[(df.ts >= pd.Timestamp(a, tz="UTC")) & (df.ts < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1))]


def policy(df, p_col, thr, max_per_day=1):
    """First qualifying candidate per symbol per day (time order). Returns the trades taken."""
    q = df[df[p_col] >= thr].sort_values("ts")
    q = q.assign(day=q.ts.dt.normalize())
    return q.groupby(["symbol", "day"]).head(max_per_day)


def report(tr, label):
    if tr.empty:
        return {"set": label, "trades": 0}
    r = tr.R
    days = tr.ts.dt.normalize().nunique()
    return {"set": label, "trades": len(tr), "days w/ signal": days, "win%": round((r > 0).mean() * 100, 1),
            "avg R": round(r.mean(), 3), "net R": round(r.sum(), 1),
            "maxDD R": round((r.cumsum() - r.cumsum().cummax()).min(), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--valid", required=True)
    ap.add_argument("--test", default=None)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "dataset.pkl"
    if cache.exists() and not a.rebuild:
        ds = pd.read_pickle(cache)
    else:
        p = StrategyParams()
        gold, silver = dukascopy.load("XAUUSD", CACHE), dukascopy.load("XAGUSD", CACHE)
        ds = pd.concat([build_dataset("XAUUSD", p, silver), build_dataset("XAGUSD", p, gold)], ignore_index=True)
        ds.to_pickle(cache)
    ds = ds.dropna(subset=["R"]).sort_values("ts").reset_index(drop=True)
    tr, va = window(ds, a.train), window(ds, a.valid)
    print(f"candidates: train {len(tr)} (base win {tr.y.mean()*100:.1f}%), valid {len(va)} (base win {va.y.mean()*100:.1f}%)")
    model = LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=300,
                           subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    model.fit(tr[FEATS], tr.y)
    iso = IsotonicRegression(out_of_bounds="clip").fit(model.predict_proba(va[FEATS])[:, 1], va.y)
    for d in (tr, va):
        d["p"] = iso.predict(model.predict_proba(d[FEATS])[:, 1])
    rows = []
    for thr in (0.70, 0.75, 0.80, 0.85, 0.90):
        rows.append({"thr": thr, **report(policy(va, "p", thr), "valid")})
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).to_string(index=False))
    imp = pd.Series(model.feature_importances_, index=FEATS).sort_values(ascending=False)
    print("\ntop features:", ", ".join(f"{k}({v})" for k, v in imp.head(10).items()))
    if a.test:
        te = window(ds, a.test).copy()
        te["p"] = iso.predict(model.predict_proba(te[FEATS])[:, 1])
        print(f"\nTEST {a.test}  candidates {len(te)} (base win {te.y.mean()*100:.1f}%)")
        rows = [{"thr": thr, **report(policy(te, "p", thr), "test")} for thr in (0.70, 0.75, 0.80, 0.85, 0.90)]
        print(pd.DataFrame(rows).to_string(index=False))
        cal = te.assign(bin=pd.cut(te.p, [0, .6, .7, .8, .85, .9, 1.0])).groupby("bin", observed=True).agg(
            n=("y", "size"), predicted=("p", "mean"), actual=("y", "mean")).round(3)
        print("\ncalibration on test (all candidates):"); print(cal.to_string())


if __name__ == "__main__":
    main()

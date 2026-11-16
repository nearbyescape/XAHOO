"""Strategy research (2026-11-17): do EMA 9/26 structure and market-state (trend vs range) inputs make the
direction probabilities more accurate at 5m, 15m, 1h and 4h?

  python research/ema_regime_eval.py build          # data/features_xr/{SYM}.parquet
  python research/ema_regime_eval.py 1h 15m 5m 4h   # walk-forward: base / +ema / +regime / +both

x_ inputs (EMA 9/26 on 5m, 15m and 1h candles; a candle's value is used only after that candle has closed):
  cross   +1 when EMA9 > EMA26, -1 when below
  gap     (EMA9 - EMA26) / price, in volatility units
  age     log(1 + candles since the last cross)
  slope   one-candle change of EMA9 / price, in volatility units
  px      (price - EMA26) / price, in volatility units
r_ inputs (market state):
  er1h    efficiency ratio of 1h closes over 24h: |net move| / sum of |moves| (1 = straight trend, 0 = chop)
  er4h    efficiency ratio of 4h closes over 5 days
  d20     daily close vs its 20-day average, in volatility units
  state   +1 trending up, -1 trending down, 0 range (er1h > 0.35 and the 24h move decides the side)
Same folds, coins, model settings and scoring as train_eval.py. Results: data/preds/xr_{h}.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research")); sys.path.insert(0, str(ROOT / "server"))
from train_eval import COINS, METALS, PRED, STEP, walk_forward  # noqa: E402

BN, FEAT, XR = ROOT / "data/binance", ROOT / "data/features", ROOT / "data/features_xr"


def closed(series: pd.Series, tf: int, idx: pd.DatetimeIndex) -> pd.Series:
    """A value computed on tf-minute candles, placed on the 1m rows where that candle has fully closed."""
    s = series.copy()
    s.index = s.index + pd.Timedelta(minutes=tf - 1)
    return s.reindex(idx, method="ffill")


def ema_features(c: pd.Series, sig: pd.Series, idx) -> dict:
    out = {}
    for tf in (5, 15, 60):
        k = c.resample(f"{tf}min", label="left", closed="left").last().dropna()
        e9, e26 = k.ewm(span=9, adjust=False).mean(), k.ewm(span=26, adjust=False).mean()
        side = np.sign(e9 - e26)
        flip = side != side.shift(1)
        age = flip.astype(int).groupby(flip.cumsum()).cumcount()
        s_tf = closed(sig, 1, k.index) * np.sqrt(tf)                     # volatility of one candle (from 1m data)
        feats = {"cross": side, "gap": (e9 - e26) / k / s_tf, "age": np.log1p(age.clip(upper=500)),
                 "slope": (e9 - e9.shift(1)) / k / s_tf, "px": (k - e26) / k / s_tf}
        for name, v in feats.items():
            out[f"x_{name}{tf}"] = closed(v, tf, idx)
    return out


def regime_features(c: pd.Series, sig: pd.Series, idx) -> dict:
    out = {}
    h1 = c.resample("60min", label="left", closed="left").last().dropna()
    h4 = c.resample("240min", label="left", closed="left").last().dropna()
    d1 = c.resample("1D", label="left", closed="left").last().dropna()
    er = lambda x, n: (x - x.shift(n)).abs() / (x.diff().abs().rolling(n).sum() + 1e-12)  # noqa: E731
    er1h, er4h = er(h1, 24), er(h4, 30)
    ret24 = np.log(h1 / h1.shift(24))
    sig_d = closed(sig, 1, d1.index) * np.sqrt(1440)
    d20 = (d1 / d1.rolling(20).mean() - 1) / sig_d
    state = np.where(er1h > 0.35, np.sign(ret24), 0.0)
    out["r_er1h"] = closed(er1h, 60, idx)
    out["r_er4h"] = closed(er4h, 240, idx)
    out["r_d20"] = closed(d20, 1440, idx)
    out["r_state"] = closed(pd.Series(state, index=h1.index), 60, idx)
    return out


def build():
    XR.mkdir(exist_ok=True)
    for sym in COINS + METALS:
        t0 = time.time()
        k = pd.read_parquet(BN / f"{sym}_1m.parquet", columns=["close"])
        k = k[~k.index.duplicated()]
        c = k["close"]
        sig = np.log(c).diff().rolling(1440, min_periods=360).std()
        idx = pd.read_parquet(FEAT / f"{sym}.parquet", columns=["y_1m"]).index
        f = {**ema_features(c, sig, idx), **regime_features(c, sig, idx)}
        x = pd.DataFrame(f, index=idx).replace([np.inf, -np.inf], np.nan).astype("float32").clip(-50, 50)
        x.to_parquet(XR / f"{sym}.parquet")
        print(f"{sym}: {x.shape} missing {x.isna().mean().max():.3f} ({time.time() - t0:.0f}s)", flush=True)


def load(h: str):
    step, parts = STEP[h], []
    for sym in COINS + METALS:
        f = pd.read_parquet(FEAT / f"{sym}.parquet")
        cols = [c for c in f.columns if c[:2] in ("a_", "b_", "c_", "d_")]
        f = f[cols + [f"y_{h}"]].join(pd.read_parquet(XR / f"{sym}.parquet"))
        minute = f.index.asi8 // (60 * {"ns": 10**9, "us": 10**6, "ms": 10**3, "s": 1}[f.index.unit])
        f = f[minute % step == 0].rename(columns={f"y_{h}": "ret"})
        f = f[f["ret"].notna() & (f["ret"] != 0)]
        f["sym"] = sym
        parts.append(f)
    xc = pd.read_parquet(XR / f"{COINS[0]}.parquet").columns
    return pd.concat(parts).sort_index(), cols, [c for c in xc if c.startswith("x_")], [c for c in xc if c.startswith("r_")]


def summary(pr):
    c = pr[pr["sym"].isin(COINS)]
    y, p = (c["ret"] > 0).to_numpy(), c["p"].to_numpy()
    sel = (p >= 0.55) | (p <= 0.45)
    q = pd.qcut(p, 10, labels=False, duplicates="drop")
    cal = pd.DataFrame({"p": p, "y": y, "q": q}).groupby("q").agg(p=("p", "mean"), y=("y", "mean"), n=("p", "size"))
    return {"auc": round(float(roc_auc_score(y, p)), 4), "accuracy": round(float(((p > 0.5) == y).mean()), 4),
            "brier_skill": round(float(1 - np.mean((p - y) ** 2) / 0.25), 5),
            "calibration_gap_pts": round(float((np.abs(cal.p - cal.y) * cal.n).sum() / cal.n.sum() * 100), 3),
            "conf55": [round(float(sel.mean()), 4), round(float(((p[sel] > 0.5) == y[sel]).mean()), 4) if sel.any() else None],
            "flips_per_hour": None,
            "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in c.groupby("fold")}}


def main():
    if sys.argv[1] == "build":
        return build()
    for h in sys.argv[1:]:
        df, base, xcols, rcols = load(h)
        res = {}
        for name, cols in (("base", base), ("ema", base + xcols), ("regime", base + rcols), ("both", base + xcols + rcols)):
            pr, imp = walk_forward(df, cols, h, label=f"{h} {name}")
            res[name] = summary(pr)
            if name != "base":
                res[name]["folds_better"] = sum(res[name]["by_fold"][f] > res["base"]["by_fold"][f] for f in res["base"]["by_fold"])
                res[name]["top_new"] = {k: int(v) for k, v in imp[[c for c in imp.index if c[:2] in ("x_", "r_")]].head(8).items()}
            pr.to_parquet(PRED / f"xr_{name}_{h}.parquet")
            print(h, name, json.dumps(res[name]), flush=True)
        (PRED / f"xr_{h}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

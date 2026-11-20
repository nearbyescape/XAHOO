"""Minute-by-minute out-of-sample forecasts for 5m / 15m / 1h / 4h (docs/RESEARCH.md section 15).

The production recipe per timeframe (research/train_ema.py: inputs, seeds, bagging; train_eval.walk_forward:
calibration with earlier out-of-sample predictions plus the 90-day window), fitted per fold on earlier data only,
then applied to EVERY minute of the fold for the 8 coins, 2024-01 → 2026-10. Lets the strong-alert rules be tested
the way the live server runs them (checked each minute), not only on the hourly grid.

  python research/minute_oos.py      -> data/preds/minute/{SYM}.parquet
"""
from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
from ema_regime_eval import load  # noqa: E402
from train_eval import CAL_DAYS, COINS, FOLDS, make_model  # noqa: E402
from xahoo.features import HORIZONS  # noqa: E402

FEAT, XR, OUT = ROOT / "data/features", ROOT / "data/features_xr", ROOT / "data/preds/minute"
PLAN = {"5m": ("ema", 1), "15m": ("both", 5), "1h": ("ema", 5), "4h": ("base", 1)}      # as in production
CONTEXT = ["a_vol_1h_1d", "a_vol_1d_7d", "c_funding_z", "r_d20", "r_er1h", "r_er4h", "y_15m", "y_1h"]


def fit_folds(h: str):
    """Per fold: the models and the calibration map, exactly as the walk-forward test builds them."""
    variant, seeds = PLAN[h]
    df, base, xcols, rcols = load(h)
    df = df.sort_index()
    cols = base + (xcols if variant in ("ema", "both") else []) + (rcols if variant == "both" else [])
    hz = pd.Timedelta(minutes=HORIZONS[h])
    pool = df[df["sym"].isin(COINS)]
    out, past_raw, past_y = [], [], []
    for a, b in FOLDS:
        t0 = time.time()
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        cs = a - pd.Timedelta(days=CAL_DAYS)
        train = pool[pool.index < cs - hz]
        cal = pool[(pool.index >= cs) & (pool.index < a - hz)]
        test = pool[(pool.index >= a) & (pool.index < b)]
        boosters = []
        for s in range(1, seeds + 1):
            m = make_model(len(train), h, seed=s)
            m.fit(train[cols], (train["ret"] > 0).astype(int))
            boosters.append(m.booster_)
        rc = np.mean([bo.predict(cal[cols]) for bo in boosters], axis=0)
        rt = np.mean([bo.predict(test[cols]) for bo in boosters], axis=0)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98).fit(
            np.concatenate(past_raw + [rc]), np.concatenate(past_y + [(cal["ret"] > 0).to_numpy().astype(int)]))
        past_raw.append(rt)
        past_y.append((test["ret"] > 0).to_numpy().astype(int))
        out.append((a, b, boosters, iso))
        print(f"  {h} fold {a:%Y-%m}: {seeds} model(s) on {len(train):,} rows ({time.time() - t0:.0f}s)", flush=True)
    del df, pool
    gc.collect()
    return cols, out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fitted = {}
    for h in PLAN:
        fitted[h] = fit_folds(h)
    start, end = pd.Timestamp(FOLDS[0][0], tz="UTC"), pd.Timestamp(FOLDS[-1][1], tz="UTC")
    for sym in COINS:
        t0 = time.time()
        need = sorted({c for cols, _ in fitted.values() for c in cols if c[:2] in ("a_", "b_", "c_", "d_")} | {c for c in CONTEXT if c[:2] != "r_"})
        f = pd.read_parquet(FEAT / f"{sym}.parquet", columns=need)
        f = f[(f.index >= start) & (f.index < end)]
        f = f.join(pd.read_parquet(XR / f"{sym}.parquet"))
        res = pd.DataFrame(index=f.index)
        for h, (cols, folds) in fitted.items():
            p = np.full(len(f), np.nan, dtype="float32")
            for a, b, boosters, iso in folds:
                k = (f.index >= a) & (f.index < b)
                if not k.any():
                    continue
                X = f.loc[k, cols]
                raw = np.mean([bo.predict(X) for bo in boosters], axis=0)
                p[k] = iso.predict(raw).astype("float32")
            res[f"p_{h}"] = p
        for c in CONTEXT:
            res[c] = f[c].astype("float32")
        res.to_parquet(OUT / f"{sym}.parquet")
        print(f"{sym}: {len(res):,} minutes ({time.time() - t0:.0f}s)", flush=True)
        del f, res
        gc.collect()


if __name__ == "__main__":
    main()

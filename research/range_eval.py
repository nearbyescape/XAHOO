"""Walk-forward test of the expected-range bands (docs/RESEARCH.md).

For each horizon the model predicts how large the move will be: the 68% and 95% quantiles of |return|, in units of
recent volatility. Scored on later data by coverage (does the "68% band" contain the move 68% of the time?) and by
pinball loss against a naive band (a constant multiple of the last day's volatility).

  python research/range_eval.py 1h
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from xahoo.features import HORIZONS   # noqa: E402

FEAT, PRED = ROOT / "data" / "features", ROOT / "data" / "preds"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
METALS = ["XAUUSDT", "XAGUSDT"]
STEP = {"1m": 12, "5m": 20, "15m": 30, "1h": 60, "4h": 120, "1d": 240}
FOLDS = [("2025-01-01", "2025-07-01"), ("2025-07-01", "2026-01-01"), ("2026-01-01", "2026-11-01")]
QS = (0.68, 0.95)


def pinball(u, q, tau):
    d = u - q
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))


def load(hname):
    step, n, parts = STEP[hname], HORIZONS[hname], []
    for sym in COINS + METALS:
        f = pd.read_parquet(FEAT / f"{sym}.parquet")
        cols = [c for c in f.columns if c[:2] in ("a_", "b_", "c_", "d_")]
        unit = {"ns": 9, "us": 6, "ms": 3, "s": 0}[f.index.unit]
        f = f[(f.index.asi8 // (60 * 10 ** unit)) % step == 0]
        f = f[f[f"y_{hname}"].notna() & (f["sig1d"] > 0)]
        f["u"] = (f[f"y_{hname}"].abs() / (f["sig1d"] * np.sqrt(n))).astype("float32")
        f["sym"] = sym
        parts.append(f[cols + ["u", "sym"]])
    return pd.concat(parts), cols


def main():
    hname = sys.argv[1]
    df, cols = load(hname)
    h = pd.Timedelta(minutes=HORIZONS[hname])
    coins = df[df["sym"].isin(COINS)]
    out = []
    for a, b in FOLDS:
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        cal0 = a - pd.Timedelta(days=90)
        train = coins[coins.index < cal0 - h]
        cal = coins[(coins.index >= cal0) & (coins.index < a - h)]
        test = df[(df.index >= a) & (df.index < b)]
        res = pd.DataFrame({"sym": test["sym"].to_numpy(), "u": test["u"].to_numpy()}, index=test.index)
        for tau in QS:
            m = LGBMRegressor(objective="quantile", alpha=tau, n_estimators=200, learning_rate=0.05, num_leaves=31,
                              max_bin=63, min_child_samples=int(np.clip(len(train) // 1000, 100, 3000)), subsample=0.7,
                              subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
            m.fit(train[cols], train["u"])
            # conformal scaling: make the band hit its target coverage on the calibration window
            qc = np.maximum(m.predict(cal[cols]), 1e-6)
            scale = float(np.quantile(cal["u"].to_numpy() / qc, tau))
            res[f"q{int(tau * 100)}"] = np.maximum(m.predict(test[cols]), 1e-6) * scale
            res[f"naive{int(tau * 100)}"] = float(np.quantile(pd.concat([train["u"], cal["u"]]), tau))
        out.append(res)
        print(f"  fold {a:%Y-%m}: train {len(train):,} test {len(test):,}", flush=True)
    pr = pd.concat(out)
    rep = {"horizon": hname}
    for name, g in (("coins", pr[pr["sym"].isin(COINS)]), ("metals", pr[pr["sym"].isin(METALS)])):
        if len(g) < 500:
            continue
        r = {"n": int(len(g))}
        for tau in QS:
            t = int(tau * 100)
            u, q, nv = g["u"].to_numpy(), g[f"q{t}"].to_numpy(), g[f"naive{t}"].to_numpy()
            r[f"coverage{t}"] = round(float((u <= q).mean()), 4)
            r[f"naive_coverage{t}"] = round(float((u <= nv).mean()), 4)
            r[f"pinball_gain{t}_pct"] = round((1 - pinball(u, q, tau) / pinball(u, nv, tau)) * 100, 1)
            # is the band informative? coverage when the model says "narrow" vs "wide"
            lo, hi = q <= np.quantile(q, 1 / 3), q >= np.quantile(q, 2 / 3)
            r[f"cov{t}_narrow_wide"] = [round(float((u[lo] <= q[lo]).mean()), 3), round(float((u[hi] <= q[hi]).mean()), 3)]
            r[f"naive_cov{t}_narrow_wide"] = [round(float((u[lo] <= nv[lo]).mean()), 3), round(float((u[hi] <= nv[hi]).mean()), 3)]
        r["band_width_ratio_wide_to_narrow"] = round(float(np.quantile(g["q68"], 0.9) / np.quantile(g["q68"], 0.1)), 2)
        rep[name] = r
    (PRED / f"range_{hname}.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

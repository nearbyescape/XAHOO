"""Walk-forward test of direction probabilities (docs/RESEARCH.md).

  python research/train_eval.py 1h            # one horizon, all features
  python research/train_eval.py 1h --ablate   # also each feature layer alone (last two folds)

For each test block the model is trained only on earlier data from the eight coins, calibrated on the 90 days
before the block, then scored on the block. Gold and silver are never trained on: their scores are pure transfer.
Predictions are saved to data/preds/{horizon}.parquet.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from xahoo.features import HORIZONS, feature_groups   # noqa: E402

FEAT, PRED = ROOT / "data" / "features", ROOT / "data" / "preds"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
METALS = ["XAUUSDT", "XAGUSDT"]
STEP = {"1m": 6, "5m": 10, "15m": 15, "1h": 30, "4h": 60, "1d": 240}          # sample every N minutes
FOLDS = [("2024-01-01", "2024-07-01"), ("2024-07-01", "2025-01-01"), ("2025-01-01", "2025-07-01"),
         ("2025-07-01", "2026-01-01"), ("2026-01-01", "2026-11-01")]
CAL_DAYS = 90


def load(hname: str) -> tuple[pd.DataFrame, list[str]]:
    step, parts = STEP[hname], []
    for sym in COINS + METALS:
        f = pd.read_parquet(FEAT / f"{sym}.parquet")
        cols = [c for c in f.columns if c[:2] in ("a_", "b_", "c_", "d_")]
        minute = (f.index.asi8 // 60_000_000_000) if f.index.unit == "ns" else (f.index.asi8 // (60 * 10 ** {"us": 6, "ms": 3, "s": 0}[f.index.unit]))
        f = f[minute % step == 0][cols + [f"y_{hname}"]].rename(columns={f"y_{hname}": "ret"})
        f = f[f["ret"].notna() & (f["ret"] != 0)]
        f["sym"] = sym
        parts.append(f)
    return pd.concat(parts), cols


def make_model(n: int, hname: str, seed: int = 1) -> LGBMClassifier:
    """Long horizons have far fewer independent samples, so they get a simpler model."""
    long = HORIZONS[hname] >= 240
    return LGBMClassifier(n_estimators=150 if long else 300, learning_rate=0.05, num_leaves=15 if long else 31, max_bin=63,
                          min_child_samples=int(np.clip(n // 1000, 300 if long else 100, 3000)), subsample=0.7,
                          subsample_freq=1, colsample_bytree=0.5 if long else 0.7, reg_lambda=10.0, n_jobs=4,
                          random_state=seed, verbose=-1)


def calibrate(raw_cal, y_cal, raw_test):
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98)
    iso.fit(raw_cal, y_cal)
    return iso.predict(raw_test)


def walk_forward(df, cols, hname, folds=FOLDS, label="all", train_syms=COINS):
    """Each fold: fit on data before the block (minus a 90-day calibration window), then calibrate with every
    out-of-sample prediction made so far (earlier folds + the calibration window). Nothing from the block or later
    is used. This mirrors live use, where the scoreboard's own history calibrates the next forecasts."""
    h = pd.Timedelta(minutes=HORIZONS[hname])
    out, imps, past_raw, past_y = [], [], [], []
    pool = df[df["sym"].isin(train_syms)]
    for a, b in folds:
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        cal_start = a - pd.Timedelta(days=CAL_DAYS)
        train = pool[pool.index < cal_start - h]
        cal = pool[(pool.index >= cal_start) & (pool.index < a - h)]
        test = df[(df.index >= a) & (df.index < b)]
        t0 = time.time()
        m = make_model(len(train), hname)
        m.fit(train[cols], (train["ret"] > 0).astype(int))
        raw_cal, raw_test = m.predict_proba(cal[cols])[:, 1], m.predict_proba(test[cols])[:, 1]
        cr = np.concatenate(past_raw + [raw_cal])
        cy = np.concatenate(past_y + [(cal["ret"] > 0).to_numpy().astype(int)])
        p = calibrate(cr, cy, raw_test)
        in_pool = test["sym"].isin(train_syms).to_numpy()
        past_raw.append(raw_test[in_pool])
        past_y.append((test["ret"].to_numpy()[in_pool] > 0).astype(int))
        out.append(pd.DataFrame({"sym": test["sym"].to_numpy(), "p": p.astype("float32"), "raw": raw_test.astype("float32"),
                                 "ret": test["ret"].to_numpy(), "fold": a.strftime("%Y-%m")}, index=test.index))
        imps.append(pd.Series(m.booster_.feature_importance("gain"), index=cols))
        print(f"  [{label}] fold {a:%Y-%m}: train {len(train):,} cal {len(cr):,} test {len(test):,} "
              f"auc {roc_auc_score(test['ret'] > 0, p):.4f} ({time.time() - t0:.0f}s)", flush=True)
    return pd.concat(out), pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)


def score(pr: pd.DataFrame) -> dict:
    y = (pr["ret"] > 0).to_numpy().astype(float)
    p = pr["p"].to_numpy().astype(float)
    base = y.mean()
    brier = float(np.mean((p - y) ** 2))
    side = np.sign(p - 0.5)
    res = {"n": int(len(pr)), "up_rate": round(float(base), 4), "auc": round(float(roc_auc_score(y, p)), 4),
           "brier": round(brier, 5), "brier_skill_vs_50": round(1 - brier / 0.25, 5),
           "brier_skill_vs_base": round(1 - brier / float(np.mean((base - y) ** 2)), 5),
           "accuracy": round(float(((p > 0.5) == (y == 1)).mean()), 4),
           "abs_move_bp": round(float(np.abs(pr["ret"]).mean() * 1e4), 2)}
    for lo in (0.55, 0.60, 0.65):
        sel = (p >= lo) | (p <= 1 - lo)
        if sel.sum() > 50:
            res[f"conf{int(lo * 100)}"] = {"coverage": round(float(sel.mean()), 4),
                                           "hit_rate": round(float(((p[sel] > 0.5) == (y[sel] == 1)).mean()), 4),
                                           "edge_bp": round(float((side[sel] * pr["ret"].to_numpy()[sel]).mean() * 1e4), 2)}
    bins = [0, .35, .40, .45, .48, .52, .55, .60, .65, 1.0]
    cal = pr.assign(y=y, bin=pd.cut(p, bins, include_lowest=True)).groupby("bin", observed=True).agg(
        n=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    res["calibration"] = [{"bin": str(i), "share": round(float(r.n / len(pr)), 4), "predicted": round(float(r.predicted), 4),
                           "actual": round(float(r.actual), 4)} for i, r in cal.iterrows()]
    return res


def main():
    hname = sys.argv[1]
    PRED.mkdir(parents=True, exist_ok=True)
    df, cols = load(hname)
    print(f"{hname}: {len(df):,} rows, {len(cols)} features, sampled every {STEP[hname]} min", flush=True)
    pr, imp = walk_forward(df, cols, hname)
    pr.to_parquet(PRED / f"{hname}.parquet")
    coins, metals = pr[pr["sym"].isin(COINS)], pr[pr["sym"].isin(METALS)]
    y_prev = None
    rep = {"horizon": hname, "coins": score(coins), "metals": score(metals) if len(metals) > 500 else None,
           "by_market": {s: {"n": int(len(g)), "auc": round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4),
                             "accuracy": round(float(((g["p"] > 0.5) == (g["ret"] > 0)).mean()), 4)}
                         for s, g in pr.groupby("sym")},
           "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in coins.groupby("fold")},
           "top_features": {k: int(v) for k, v in imp.head(12).items()}}
    if "--ablate" in sys.argv:
        groups = feature_groups(cols)
        rep["layers_auc"] = {}
        for g, gc in groups.items():
            pg, _ = walk_forward(df, gc, hname, FOLDS[-2:], label=f"layer {g}")
            rep["layers_auc"][g] = round(float(roc_auc_score(pg[pg["sym"].isin(COINS)]["ret"] > 0, pg[pg["sym"].isin(COINS)]["p"])), 4)
        last2 = coins[coins["fold"].isin([f[0][:7] for f in FOLDS[-2:]])]
        rep["layers_auc"]["all"] = round(float(roc_auc_score(last2["ret"] > 0, last2["p"])), 4)
    (PRED / f"{hname}.json").write_text(json.dumps(rep, indent=1))
    c = rep["coins"]
    print(json.dumps({k: v for k, v in c.items() if k != "calibration"}, indent=None))
    print(pd.DataFrame(c["calibration"]).to_string(index=False))
    print("by fold:", rep["by_fold"]); print("by market:", {k: v["auc"] for k, v in rep["by_market"].items()})
    if rep["metals"]:
        print("METALS:", {k: v for k, v in rep["metals"].items() if k != "calibration"})
    if "layers_auc" in rep:
        print("layers (AUC, last two folds):", rep["layers_auc"])
    print("top features:", list(rep["top_features"])[:10])


if __name__ == "__main__":
    main()

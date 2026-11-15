"""Train the production models and write models/ (manifest + LightGBM files).

  coin family    direction models for all six horizons, trained on the eight coins through Oct 2026;
                 calibration map from every walk-forward out-of-sample prediction (2024-01 → 2026-10)
  metal family   1m: the coin model (it transferred to gold in testing); 15m/1h/4h: trend-only models trained on
                 17 years of spot gold/silver; each is validated on Binance gold/silver data from 2026
  range bands    68% / 95% quantile models (shared), with a separate scale for coins and metals

Every market × horizon gets a skill tier from out-of-sample results: 2 = shown, 1 = shown as weak, 0 = "no edge".
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
import range_eval   # noqa: E402
import train_eval   # noqa: E402
from train_eval import COINS, METALS, make_model   # noqa: E402
from xahoo.features import HORIZONS   # noqa: E402
from xahoo.model import apply_cal, binned_isotonic   # noqa: E402

OUT, PRED = ROOT / "models", ROOT / "data" / "preds"
VERSION = "2026.11.15"
CAL_START = pd.Timestamp("2026-08-01", tz="UTC")
TREND_H = ("15m", "1h", "4h")


def tier(auc: float) -> int:
    return 2 if auc >= 0.53 else (1 if auc >= 0.515 else 0)


def stats(y, p) -> dict:
    y = np.asarray(y, dtype=bool)
    sel = (p >= 0.55) | (p <= 0.45)
    return {"n": int(len(y)), "auc": round(float(roc_auc_score(y, p)), 4), "accuracy": round(float(((p > 0.5) == y).mean()), 4),
            "conf55_share": round(float(sel.mean()), 4),
            "conf55_hit": round(float(((p[sel] > 0.5) == y[sel]).mean()), 4) if sel.sum() > 50 else None}


def main():
    OUT.mkdir(exist_ok=True)
    fam = {"coin": {}, "metal": {}}
    skill = {s: {} for s in COINS + METALS}
    features = None
    for h, n in HORIZONS.items():
        df, cols = train_eval.load(h)
        features = cols
        coins = df[df["sym"].isin(COINS)]
        metals26 = df[df["sym"].isin(METALS)]
        # ---- direction, coin family
        m = make_model(len(coins), h)
        m.fit(coins[cols], (coins["ret"] > 0).astype(int))
        m.booster_.save_model(str(OUT / f"coin_dir_{h}.txt"))
        oos = pd.read_parquet(PRED / f"{h}.parquet")
        oc = oos[oos["sym"].isin(COINS)]
        cal = binned_isotonic(oc["raw"].to_numpy(dtype=float), (oc["ret"] > 0).to_numpy(dtype=float), 30)
        rep = json.loads((PRED / f"{h}.json").read_text())
        pooled = rep["coins"]
        for s in COINS:
            g = oc[oc["sym"] == s]
            st = stats(g["ret"] > 0, g["p"].to_numpy(dtype=float))
            skill[s][h] = {**st, "tier": tier(pooled["auc"]), "show": tier(pooled["auc"]) > 0, "basis": "walk-forward 2024-01 → 2026-10"}
        # ---- range bands (shared models; scale per family)
        rdf, rcols = range_eval.load(h)
        rtrain = rdf[rdf["sym"].isin(COINS) & (rdf.index < CAL_START - pd.Timedelta(minutes=n))]
        scales = {}
        qfiles = {}
        for tau in (0.68, 0.95):
            q = LGBMRegressor(objective="quantile", alpha=tau, n_estimators=200, learning_rate=0.05, num_leaves=31, max_bin=63,
                              min_child_samples=int(np.clip(len(rtrain) // 1000, 100, 3000)), subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.7, n_jobs=4, verbose=-1)
            q.fit(rtrain[rcols], rtrain["u"])
            name = f"q{int(tau * 100)}_{h}.txt"
            q.booster_.save_model(str(OUT / name))
            qfiles[f"q{int(tau * 100)}"] = name
            for f, syms in (("coin", COINS), ("metal", METALS)):
                c = rdf[rdf["sym"].isin(syms) & (rdf.index >= CAL_START)]
                scales[(f, tau)] = float(np.quantile(c["u"].to_numpy() / np.maximum(q.predict(c[rcols]), 1e-6), tau))
        fam["coin"][h] = {"files": {"dir": f"coin_dir_{h}.txt", **qfiles}, "calibration": cal,
                          "q68_scale": round(scales[("coin", 0.68)], 4), "q95_scale": round(scales[("coin", 0.95)], 4)}
        mspec = {"files": dict(qfiles), "q68_scale": round(scales[("metal", 0.68)], 4), "q95_scale": round(scales[("metal", 0.95)], 4)}
        for s in METALS:
            skill[s][h] = {"tier": 0, "show": False, "basis": "no out-of-sample skill"}
        # ---- direction, metal family
        if h == "1m":
            om = oos[oos["sym"] == "XAUUSDT"]
            st = stats(om["ret"] > 0, om["p"].to_numpy(dtype=float))
            if tier(st["auc"]) > 0:
                mspec["files"]["dir"] = f"coin_dir_{h}.txt"
                mspec["calibration"] = binned_isotonic(om["raw"].to_numpy(dtype=float), (om["ret"] > 0).to_numpy(dtype=float), 15)
                skill["XAUUSDT"][h] = {**st, "tier": min(tier(st["auc"]), 1), "show": True,
                                       "basis": "coin model applied to Binance gold, 2026 (limited history)"}
        if h in TREND_H:
            tr = pd.read_parquet(PRED / f"metals_trend_train_{h}.parquet")
            acols = [c for c in tr.columns if c.startswith("a_")]
            tm = LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=15, max_bin=63, min_child_samples=500,
                                subsample=0.7, subsample_freq=1, colsample_bytree=0.5, reg_lambda=10.0, n_jobs=4, verbose=-1)
            tm.fit(tr[acols], (tr["ret"] > 0).astype(int))
            too = pd.read_parquet(PRED / f"metals_trend_{h}.parquet")
            too = too[too["year"] < 2026]
            tcal = binned_isotonic(too["p"].to_numpy(dtype=float), (too["ret"] > 0).to_numpy(dtype=float), 20)
            # validation on Binance gold/silver (2026, mark-price target): never used for fitting
            p = apply_cal(tcal, tm.predict_proba(metals26[acols])[:, 1])
            ok = False
            for s in METALS:
                k = (metals26["sym"] == s).to_numpy()
                st = stats(metals26["ret"].to_numpy()[k] > 0, p[k])
                t = min(tier(st["auc"]), 1)
                skill[s][h] = {**st, "tier": t, "show": t > 0, "basis": "trend model (17y spot) validated on Binance 2026"}
                ok = ok or t > 0
                print(f"  metal trend {h} {s}: {st}", flush=True)
            if ok:
                tm.booster_.save_model(str(OUT / f"metal_dir_{h}.txt"))
                mspec["files"]["dir"] = f"metal_dir_{h}.txt"
                mspec["calibration"] = tcal
                mspec["features_dir"] = acols
        fam["metal"][h] = mspec
        print(f"{h}: coin AUC {pooled['auc']} tier {tier(pooled['auc'])} | cal map {cal['y'][0]:.3f} … {cal['y'][-1]:.3f} | "
              f"scales {fam['coin'][h]['q68_scale']}/{fam['coin'][h]['q95_scale']} metal {mspec['q68_scale']}/{mspec['q95_scale']}", flush=True)
    manifest = {"version": VERSION, "trained_through": "2026-10-31", "features": features, "families": fam, "skill": skill,
                "target": "Binance mark price higher at the end of the horizon than at forecast time"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()

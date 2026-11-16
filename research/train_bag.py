"""Bagged direction models (5 seeds averaged) for the horizons where bagging tested better in every fold
(research/improve2_eval.py). Rewrites the coin family's files, calibration map and skill figures for those
horizons in models/manifest.json; everything else is left as train_final.py wrote it.

  python research/train_bag.py 1h [15m ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
from train_eval import CAL_DAYS, COINS, FOLDS, PRED, calibrate, load, make_model  # noqa: E402
from train_final import stats, tier  # noqa: E402
from xahoo.features import HORIZONS  # noqa: E402
from xahoo.model import binned_isotonic  # noqa: E402

OUT = ROOT / "models"
SEEDS = (1, 2, 3, 4, 5)


def oos_bagged(df, cols, h):
    """Walk-forward out-of-sample predictions with the bagged model (raw and calibrated), coins only."""
    hz = pd.Timedelta(minutes=HORIZONS[h])
    pool = df[df["sym"].isin(COINS)]
    out, past_raw, past_y = [], [], []
    for a, b in FOLDS:
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        cs = a - pd.Timedelta(days=CAL_DAYS)
        train, cal = pool[pool.index < cs - hz], pool[(pool.index >= cs) & (pool.index < a - hz)]
        test = pool[(pool.index >= a) & (pool.index < b)]
        rc, rt = np.zeros(len(cal)), np.zeros(len(test))
        for s in SEEDS:
            m = make_model(len(train), h, seed=s)
            m.fit(train[cols], (train["ret"] > 0).astype(int))
            rc += m.predict_proba(cal[cols])[:, 1] / len(SEEDS)
            rt += m.predict_proba(test[cols])[:, 1] / len(SEEDS)
        p = calibrate(np.concatenate(past_raw + [rc]), np.concatenate(past_y + [(cal["ret"] > 0).to_numpy().astype(int)]), rt)
        past_raw.append(rt); past_y.append((test["ret"] > 0).to_numpy().astype(int))
        out.append(pd.DataFrame({"sym": test["sym"].to_numpy(), "p": p, "raw": rt, "ret": test["ret"].to_numpy(),
                                 "fold": a.strftime("%Y-%m")}, index=test.index))
        print(f"  {h} fold {a:%Y-%m} done", flush=True)
    return pd.concat(out)


def main():
    man = json.loads((OUT / "manifest.json").read_text())
    for h in sys.argv[1:]:
        df, cols = load(h)
        df = df.sort_index()
        assert cols == man["features"]
        oos = oos_bagged(df, cols, h)
        oos.to_parquet(PRED / f"bag_{h}.parquet")
        coins = df[df["sym"].isin(COINS)]
        files = []
        for s in SEEDS:
            m = make_model(len(coins), h, seed=s)
            m.fit(coins[cols], (coins["ret"] > 0).astype(int))
            name = f"coin_dir_{h}.txt" if s == 1 else f"coin_dir_{h}_s{s}.txt"     # seed 1 keeps the old name
            m.booster_.save_model(str(OUT / name))
            files.append(name)
        spec = man["families"]["coin"][h]
        spec["files"]["dir"] = files
        spec["calibration"] = binned_isotonic(oos["raw"].to_numpy(float), (oos["ret"] > 0).to_numpy(float), 30)
        spec["bagged"] = len(SEEDS)
        pooled = stats(oos["ret"] > 0, oos["p"].to_numpy(float))
        for s in COINS:
            g = oos[oos["sym"] == s]
            st = stats(g["ret"] > 0, g["p"].to_numpy(float))
            man["skill"][s][h] = {**st, "tier": tier(pooled["auc"]), "show": tier(pooled["auc"]) > 0,
                                  "basis": f"walk-forward 2024-01 → 2026-10, {len(SEEDS)} models averaged"}
        print(h, "pooled", pooled, flush=True)
    man["version"] = "2026.11.16"
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print("manifest updated")


if __name__ == "__main__":
    main()

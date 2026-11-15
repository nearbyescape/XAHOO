"""Gold and silver: which model to use? (docs/RESEARCH.md)

Binance lists gold since Dec 2025 and silver since Jan 2026. Test block: Aug-Oct 2026. Three options, all trained on
data up to 30 Apr 2026 and calibrated on May-Jul 2026:
  transfer  trained on the eight coins only
  pooled    coins + gold + silver, with an is_metal flag
  metals    gold + silver only
  python research/metals_eval.py 1m 5m 15m 1h
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import COINS, METALS, calibrate, load, make_model   # noqa: E402

T_END, C_END, X_END = (pd.Timestamp(x, tz="UTC") for x in ("2026-05-01", "2026-08-01", "2026-11-01"))
rows = []
for hname in sys.argv[1:]:
    df, cols = load(hname)
    df["is_metal"] = df["sym"].isin(METALS).astype("float32")
    test = df[(df.index >= C_END) & (df.index < X_END) & df["sym"].isin(METALS)]
    for name, syms, fc in (("transfer", COINS, cols), ("pooled", COINS + METALS, cols + ["is_metal"]), ("metals", METALS, cols)):
        pool = df[df["sym"].isin(syms)]
        train = pool[pool.index < T_END]
        cal = df[(df.index >= T_END) & (df.index < C_END) & df["sym"].isin(METALS if name != "transfer" else COINS)]
        m = make_model(len(train), hname)
        m.fit(train[fc], (train["ret"] > 0).astype(int))
        p = calibrate(m.predict_proba(cal[fc])[:, 1], (cal["ret"] > 0).astype(int), m.predict_proba(test[fc])[:, 1])
        y = (test["ret"] > 0).to_numpy()
        row = {"horizon": hname, "model": name, "n": len(test), "auc": round(roc_auc_score(y, p), 4),
               "accuracy": round(float(((p > 0.5) == y).mean()), 4)}
        for s in METALS:
            k = (test["sym"] == s).to_numpy()
            row[f"auc {s[:3]}"] = round(roc_auc_score(y[k], p[k]), 4)
        sel = (p >= 0.55) | (p <= 0.45)
        row["conf55 cover"] = round(float(sel.mean()), 3)
        row["conf55 hit"] = round(float(((p[sel] > 0.5) == y[sel]).mean()), 4) if sel.sum() > 30 else None
        row["brier skill"] = round(1 - float(np.mean((p - y) ** 2)) / 0.25, 5)
        rows.append(row)
        print(row, flush=True)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).to_string(index=False))

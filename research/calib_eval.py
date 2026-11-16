"""Are the probabilities right per market? Expected calibration error (ECE: average gap between the stated
probability and how often it happened, in percentage points) for the pooled calibration used now, versus a
per-market correction fitted only on EARLIER folds (so the test stays out-of-sample).
  python research/calib_eval.py  -> data/preds/calib.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import COINS, PRED  # noqa: E402

FILES = {"1m": "1m", "5m": "5m", "15m": "bag_15m", "1h": "bag_1h", "4h": "4h", "1d": "1d"}


def ece(p, y, bins=10):
    q = pd.qcut(p, bins, labels=False, duplicates="drop")
    d = pd.DataFrame({"p": p, "y": y, "q": q}).groupby("q").agg(p=("p", "mean"), y=("y", "mean"), n=("p", "size"))
    return float((np.abs(d["p"] - d["y"]) * d["n"]).sum() / d["n"].sum() * 100)


out = {}
for h, fn in FILES.items():
    pr = pd.read_parquet(PRED / f"{fn}.parquet")
    pr = pr[pr["sym"].isin(COINS)]
    folds = sorted(pr["fold"].unique())
    rows = []
    for i, f in enumerate(folds[1:], 1):
        past, test = pr[pr["fold"].isin(folds[:i])], pr[pr["fold"] == f]
        for s in COINS:
            a, b = past[past["sym"] == s], test[test["sym"] == s]
            lp = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
            m = LogisticRegression(C=1.0).fit(lp(a["p"].to_numpy())[:, None], (a["ret"] > 0).to_numpy())
            q = m.predict_proba(lp(b["p"].to_numpy())[:, None])[:, 1]
            rows.append(pd.DataFrame({"sym": s, "fold": f, "p": b["p"].to_numpy(), "q": q, "y": (b["ret"] > 0).to_numpy().astype(float)}))
    r = pd.concat(rows)
    res = {"pooled_ece": round(ece(r["p"].to_numpy(), r["y"].to_numpy()), 3),
           "per_market_ece": round(ece(r["q"].to_numpy(), r["y"].to_numpy()), 3),
           "brier_pooled": round(float(((r["p"] - r["y"]) ** 2).mean()), 6), "brier_per_market": round(float(((r["q"] - r["y"]) ** 2).mean()), 6),
           "by_market_ece": {s: [round(ece(g["p"].to_numpy(), g["y"].to_numpy()), 2), round(ece(g["q"].to_numpy(), g["y"].to_numpy()), 2)] for s, g in r.groupby("sym")}}
    out[h] = res
    print(h, json.dumps(res), flush=True)
(PRED / "calib.json").write_text(json.dumps(out, indent=1))

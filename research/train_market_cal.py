"""Per-market calibration on top of the pooled map (research/calib_eval.py): q = sigmoid(a + b * logit(p)),
one (a, b) per coin and horizon, fitted on all out-of-sample forecasts 2024-01 → 2026-10. Skill figures shown
on screen are replaced by the walk-forward evaluation of this step (each fold corrected with earlier folds only).
1d is left out: the correction made it worse there.
  python research/train_market_cal.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import COINS, PRED  # noqa: E402
from train_final import stats  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "models"
FILES = {"1m": "1m", "5m": "ema_5m", "15m": "ema_15m", "1h": "ema_1h", "4h": "4h"}     # out-of-sample predictions of the production recipe
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731

man = json.loads((OUT / "manifest.json").read_text())
for h, fn in FILES.items():
    pr = pd.read_parquet(PRED / f"{fn}.parquet")
    pr = pr[pr["sym"].isin(COINS)]
    folds = sorted(pr["fold"].unique())
    cal, test_q = {}, []
    for s in COINS:
        g = pr[pr["sym"] == s]
        m = LogisticRegression().fit(lg(g["p"].to_numpy())[:, None], (g["ret"] > 0).to_numpy())
        cal[s] = [round(float(m.intercept_[0]), 5), round(float(m.coef_[0][0]), 5)]
        for i, f in enumerate(folds[1:], 1):                    # honest evaluation: earlier folds only
            a, b = g[g["fold"].isin(folds[:i])], g[g["fold"] == f]
            mm = LogisticRegression().fit(lg(a["p"].to_numpy())[:, None], (a["ret"] > 0).to_numpy())
            test_q.append(pd.DataFrame({"sym": s, "q": mm.predict_proba(lg(b["p"].to_numpy())[:, None])[:, 1],
                                        "y": (b["ret"] > 0).to_numpy()}))
    man["families"]["coin"][h]["market_cal"] = cal
    tq = pd.concat(test_q)
    for s in COINS:
        g = tq[tq["sym"] == s]
        old = man["skill"][s][h]
        note = "; per-market calibration (tested 2024-07 → 2026-10)"
        basis = old.get("basis", "walk-forward")
        man["skill"][s][h] = {**old, **stats(g["y"].to_numpy(), g["q"].to_numpy()),
                              "basis": basis if note in basis else basis + note}
    pooled = stats(tq["y"].to_numpy(), tq["q"].to_numpy())
    print(h, "per-market calibrated, out-of-sample:", pooled, "| BTC a,b =", cal["BTCUSDT"], flush=True)
(OUT / "manifest.json").write_text(json.dumps(man, indent=1))
print("manifest updated")

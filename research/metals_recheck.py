"""Gold and silver, re-checked with per-market calibration (2026-11-17).

Predictions: the walk-forward coin models (data/preds/{h}.parquet), whose 2026 fold was trained only on coin data
before 2025-10 -- gold and silver never appear in training. Calibration: a gold- (or silver-) specific
sigmoid(a + b*logit(p)) fitted on Jan-May 2026 only. Test: Jun-Oct 2026. A horizon is shown (as "weak") only if
AUC >= 0.515 in BOTH halves of 2026 and the calibrated forecast beats a coin flip on Brier score in Jun-Oct.
  python research/metals_recheck.py   -> data/preds/metals_recheck.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

PRED = Path(__file__).resolve().parents[1] / "data/preds"
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
out = {}
for h in ("1m", "5m", "15m", "1h", "4h", "1d"):
    pr = pd.read_parquet(PRED / f"{h}.parquet")
    for s in ("XAUUSDT", "XAGUSDT"):
        g = pr[pr["sym"] == s]
        a, b = g[g.index < SPLIT], g[g.index >= SPLIT]
        if len(a) < 200 or len(b) < 200:
            continue
        ya, yb = (a["ret"] > 0).to_numpy(), (b["ret"] > 0).to_numpy()
        m = LogisticRegression().fit(lg(a["raw"].to_numpy())[:, None], ya)
        q = m.predict_proba(lg(b["raw"].to_numpy())[:, None])[:, 1]
        auc_a, auc_b = roc_auc_score(ya, a["raw"]), roc_auc_score(yb, b["raw"])
        bs = 1 - np.mean((q - yb) ** 2) / 0.25
        sel = (q >= 0.55) | (q <= 0.45)
        ok = auc_a >= 0.515 and auc_b >= 0.515 and bs > 0
        out[f"{s} {h}"] = {"n_jan_may": len(a), "n_jun_oct": len(b), "auc_jan_may": round(auc_a, 4), "auc_jun_oct": round(auc_b, 4),
                           "acc_jun_oct": round(float(((q > 0.5) == yb).mean()), 4), "brier_skill_jun_oct": round(float(bs), 5),
                           "conf55": [round(float(sel.mean()), 3), round(float(((q[sel] > 0.5) == yb[sel]).mean()), 4) if sel.sum() > 30 else None],
                           "cal": [round(float(m.intercept_[0]), 5), round(float(m.coef_[0][0]), 5)], "pass": bool(ok)}
        print(s, h, out[f"{s} {h}"], flush=True)
(PRED / "metals_recheck.json").write_text(json.dumps(out, indent=1))

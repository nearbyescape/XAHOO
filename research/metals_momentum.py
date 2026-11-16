"""Gold / silver: add recent momentum to the metal calibration (2026-11-17).

The coin model misses that gold continues short moves (after a 15-minute fall the next minute was up only ~45%
of the time). Here the metal-specific calibration gets the momentum inputs as well:
  P(up) = sigmoid(a + b*logit(raw) + c1*a_ret5 + c2*a_ret15 + c3*a_ret60 + c4*b_imb15)
fitted on Jan-May 2026, tested on Jun-Oct 2026. Same pass rule as metals_recheck.py: AUC >= 0.515 in both halves
(the Jan-May figure is in-sample for the 6 weights, so the Jun-Oct test decides) and Brier better than a coin flip.
  python research/metals_momentum.py   -> data/preds/metals_momentum.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
PRED, FEAT = ROOT / "data/preds", ROOT / "data/features"
COLS = ["a_ret5", "a_ret15", "a_ret60", "b_imb15"]
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731


def design(d):
    return np.column_stack([lg(d["raw"].to_numpy())] + [np.clip(d[c].to_numpy(), -5, 5) for c in COLS])


out = {}
for s in ("XAUUSDT", "XAGUSDT"):
    f = pd.read_parquet(FEAT / f"{s}.parquet", columns=COLS)
    for h in ("1m", "5m", "15m", "1h", "4h"):
        pr = pd.read_parquet(PRED / f"{h}.parquet")
        d = pr[pr["sym"] == s].join(f, how="inner").dropna(subset=COLS)
        a, b = d[d.index < SPLIT], d[d.index >= SPLIT]
        ya, yb = (a["ret"] > 0).to_numpy(), (b["ret"] > 0).to_numpy()
        m = LogisticRegression(C=0.5).fit(design(a), ya)
        qa, qb = m.predict_proba(design(a))[:, 1], m.predict_proba(design(b))[:, 1]
        base = LogisticRegression().fit(lg(a["raw"].to_numpy())[:, None], ya).predict_proba(lg(b["raw"].to_numpy())[:, None])[:, 1]
        auc_a, auc_b = roc_auc_score(ya, qa), roc_auc_score(yb, qb)
        bs = 1 - np.mean((qb - yb) ** 2) / 0.25
        sel = (qb >= 0.55) | (qb <= 0.45)
        ok = auc_a >= 0.515 and auc_b >= 0.515 and bs > 0
        r = {"n_test": int(len(b)), "auc_jan_may_in_sample": round(auc_a, 4), "auc_jun_oct": round(auc_b, 4),
             "auc_jun_oct_without_momentum": round(roc_auc_score(yb, base), 4), "acc_jun_oct": round(float(((qb > 0.5) == yb).mean()), 4),
             "brier_skill": round(float(bs), 5), "conf55": [round(float(sel.mean()), 3), round(float(((qb[sel] > 0.5) == yb[sel]).mean()), 4) if sel.sum() > 30 else None],
             "coef": dict(zip(["a", "raw"] + COLS, [round(float(m.intercept_[0]), 4)] + [round(float(x), 4) for x in m.coef_[0]])),
             "pass": bool(ok)}
        out[f"{s} {h}"] = r
        print(s, h, {k: r[k] for k in ("auc_jun_oct_without_momentum", "auc_jun_oct", "acc_jun_oct", "brier_skill", "conf55", "pass")}, flush=True)
(PRED / "metals_momentum.json").write_text(json.dumps(out, indent=1))

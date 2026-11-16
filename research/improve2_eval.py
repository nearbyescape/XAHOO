"""More accuracy tests (same folds as train_eval.py): recency weighting, rolling window, seed bagging.
  python research/improve2_eval.py 1h 4h 15m      -> data/preds/improve2_{h}.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import CAL_DAYS, COINS, FOLDS, PRED, calibrate, load, make_model  # noqa: E402
from xahoo.features import HORIZONS  # noqa: E402


def wf(df, cols, h, half_life=None, window_days=None, seeds=(1,)):
    hz = pd.Timedelta(minutes=HORIZONS[h])
    pool = df[df["sym"].isin(COINS)]
    out, past_raw, past_y = [], [], []
    for a, b in FOLDS:
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        cs = a - pd.Timedelta(days=CAL_DAYS)
        train = pool[pool.index < cs - hz]
        if window_days:
            train = train[train.index >= cs - pd.Timedelta(days=window_days)]
        cal = pool[(pool.index >= cs) & (pool.index < a - hz)]
        test = df[(df.index >= a) & (df.index < b) & df["sym"].isin(COINS)]
        w = None
        if half_life:
            age = (cs - train.index).total_seconds().to_numpy() / 86400
            w = 0.5 ** (age / half_life)
        rc, rt = np.zeros(len(cal)), np.zeros(len(test))
        for s in seeds:
            m = make_model(len(train), h, seed=s)
            m.fit(train[cols], (train["ret"] > 0).astype(int), sample_weight=w)
            rc += m.predict_proba(cal[cols])[:, 1] / len(seeds)
            rt += m.predict_proba(test[cols])[:, 1] / len(seeds)
        cr = np.concatenate(past_raw + [rc]); cy = np.concatenate(past_y + [(cal["ret"] > 0).to_numpy().astype(int)])
        p = calibrate(cr, cy, rt)
        past_raw.append(rt); past_y.append((test["ret"] > 0).to_numpy().astype(int))
        out.append(pd.DataFrame({"p": p, "ret": test["ret"].to_numpy(), "fold": a.strftime("%Y-%m")}, index=test.index))
    pr = pd.concat(out)
    sel = (pr["p"] >= 0.55) | (pr["p"] <= 0.45)
    return {"auc": round(float(roc_auc_score(pr["ret"] > 0, pr["p"])), 4),
            "accuracy": round(float(((pr["p"] > 0.5) == (pr["ret"] > 0)).mean()), 4),
            "conf55": [round(float(sel.mean()), 4), round(float(((pr["p"][sel] > 0.5) == (pr["ret"][sel] > 0)).mean()), 4)],
            "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in pr.groupby("fold")}}


def main():
    for h in [a for a in sys.argv[1:]] or ["1h"]:
        df, cols = load(h)
        df = df.sort_index()
        res = {}
        for name, kw in {"base": {}, "recency_hl180": {"half_life": 180}, "recency_hl365": {"half_life": 365},
                         "window_365d": {"window_days": 365}, "bag5": {"seeds": (1, 2, 3, 4, 5)},
                         "bag5_hl365": {"seeds": (1, 2, 3, 4, 5), "half_life": 365}}.items():
            res[name] = wf(df, cols, h, **kw)
            print(h, name, json.dumps(res[name]), flush=True)
        (PRED / f"improve2_{h}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

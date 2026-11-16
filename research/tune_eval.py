"""Model settings, chosen honestly: candidates are compared on the 2024 folds only; the winner is then checked
against the current settings on the 2025-07 and 2026 folds, which played no part in choosing it.

  python research/tune_eval.py 1h 15m     -> data/preds/tune_{h}.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import CAL_DAYS, COINS, FOLDS, PRED, calibrate, load, make_model  # noqa: E402
from xahoo.features import HORIZONS  # noqa: E402

SELECT, CONFIRM = FOLDS[:2], FOLDS[3:]


def variant(name, n, h):
    base = make_model(n, h)
    p = base.get_params()
    if name == "slow":
        p.update(n_estimators=p["n_estimators"] * 2, learning_rate=p["learning_rate"] / 2)
    elif name == "small":
        p.update(num_leaves=max(7, p["num_leaves"] // 2), n_estimators=int(p["n_estimators"] * 1.5))
    elif name == "big":
        p.update(num_leaves=p["num_leaves"] * 2, min_child_samples=p["min_child_samples"] * 2)
    elif name == "narrow":
        p.update(colsample_bytree=0.4, n_estimators=int(p["n_estimators"] * 1.3))
    elif name == "extra":
        p.update(extra_trees=True, n_estimators=int(p["n_estimators"] * 1.7))
    elif name == "reg":
        p.update(reg_lambda=50.0, min_child_samples=p["min_child_samples"] * 3)
    return LGBMClassifier(**p)


def wf(df, cols, h, folds, name):
    hz = pd.Timedelta(minutes=HORIZONS[h])
    pool = df[df["sym"].isin(COINS)]
    aucs = {}
    past_raw, past_y = [], []
    for a, b in FOLDS:                         # every fold runs so calibration history matches production
        a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        if (str(a.date()), str(b.date())) not in [(x, y) for x, y in folds] and a.strftime("%Y-%m-%d") > folds[-1][0]:
            break
        cs = a - pd.Timedelta(days=CAL_DAYS)
        train, cal = pool[pool.index < cs - hz], pool[(pool.index >= cs) & (pool.index < a - hz)]
        test = pool[(pool.index >= a) & (pool.index < b)]
        m = variant(name, len(train), h)
        m.fit(train[cols], (train["ret"] > 0).astype(int))
        rc, rt = m.predict_proba(cal[cols])[:, 1], m.predict_proba(test[cols])[:, 1]
        p = calibrate(np.concatenate(past_raw + [rc]), np.concatenate(past_y + [(cal["ret"] > 0).to_numpy().astype(int)]), rt)
        past_raw.append(rt); past_y.append((test["ret"] > 0).to_numpy().astype(int))
        if (a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) in folds:
            aucs[a.strftime("%Y-%m")] = round(float(roc_auc_score(test["ret"] > 0, p)), 4)
    return aucs


def main():
    for h in sys.argv[1:]:
        df, cols = load(h)
        df = df.sort_index()
        sel = {}
        for name in ("base", "slow", "small", "big", "narrow", "extra", "reg"):
            sel[name] = wf(df, cols, h, SELECT, name)
            print(h, "select", name, sel[name], flush=True)
        best = max((n for n in sel if n != "base"), key=lambda n: np.mean(list(sel[n].values())))
        conf = {n: wf(df, cols, h, CONFIRM, n) for n in ("base", best)}
        rep = {"select_2024": sel, "best": best, "confirm_2025_26": conf,
               "verdict": "better" if all(conf[best][f] > conf["base"][f] for f in conf["base"]) else "not better"}
        print(h, "best", best, "confirm", conf, rep["verdict"], flush=True)
        (PRED / f"tune_{h}.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

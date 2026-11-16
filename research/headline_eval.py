"""One headline direction from 5m / 15m / 1h / 4h, and steadier labels (strategy plan steps 3 and 4, 2026-11-18).

Uses the walk-forward out-of-sample probabilities of the production recipe (data/preds/ema_5m, ema_15m, ema_1h, 4h),
aligned on the hourly grid where all four exist (each made from the same moment's data). Coins only.

A. Headline ("overall") candidates, each scored on the 1h outcome and also on the 15m and 4h outcomes:
     avg     equal-weight average of the four leans in log-odds
     learn   logistic regression on the four log-odds, fitted on earlier folds only (expanding window)
   The learned version is kept only if it beats the plain average on unseen folds.
B. Cross-timeframe help: does adding the other timeframes' log-odds improve each timeframe's own probability?
   Same expanding-window fit; kept per timeframe only if better in at least 3 of the 4 later folds.
C. Steady labels: hysteresis bands vs today's fixed 2-point neutral band, on the 5m series (every 10 minutes):
   label flips per hour, and the hit rate of the UP / DOWN labels shown.

  python research/headline_eval.py        -> data/preds/headline.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
from train_eval import COINS, PRED  # noqa: E402

FILES = {"5m": "ema_5m", "15m": "ema_15m", "1h": "ema_1h", "4h": "4h"}
HS = list(FILES)
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731


def aligned() -> pd.DataFrame:
    parts = []
    for h, fn in FILES.items():
        p = pd.read_parquet(PRED / f"{fn}.parquet")
        p = p[p["sym"].isin(COINS)]
        p = p.set_index("sym", append=True)[["p", "ret", "fold"]].rename(columns={"p": f"p_{h}", "ret": f"r_{h}", "fold": f"f_{h}"})
        parts.append(p)
    df = parts[0]
    for p in parts[1:]:
        df = df.join(p, how="inner")
    df["fold"] = df["f_1h"]
    return df.drop(columns=[f"f_{h}" for h in HS]).dropna()


def score(p, y) -> dict:
    y = np.asarray(y, bool)
    sel = (p >= 0.52) | (p <= 0.48)
    return {"auc": round(float(roc_auc_score(y, p)), 4), "acc": round(float(((p > 0.5) == y).mean()), 4),
            "brier_skill": round(float(1 - np.mean((p - y) ** 2) / 0.25), 5),
            "shown_share": round(float(sel.mean()), 3), "shown_hit": round(float(((p[sel] > 0.5) == y[sel]).mean()), 4)}


def expanding(df, X, y, cal=True):
    """Fit on all earlier folds, predict the next; isotonic calibration on the earlier folds' fitted scores."""
    folds = sorted(df["fold"].unique())
    out = pd.Series(np.nan, index=df.index)
    for i, f in enumerate(folds[1:], 1):
        tr, te = df["fold"].isin(folds[:i]).to_numpy(), (df["fold"] == f).to_numpy()
        m = LogisticRegression(C=1.0).fit(X[tr], y[tr])
        s_tr, s_te = m.predict_proba(X[tr])[:, 1], m.predict_proba(X[te])[:, 1]
        if cal:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98).fit(s_tr, y[tr])
            s_te = iso.predict(s_te)
        out[te] = s_te
    return out


def labels(p: np.ndarray, enter: float, leave: float) -> np.ndarray:
    """+1 / 0 / -1 with hysteresis: a side starts at |p - .5| >= enter and holds until |p - .5| < leave."""
    lab = np.zeros(len(p), int)
    cur = 0
    for i, x in enumerate(p):
        d = x - 0.5
        if cur == 0:
            cur = 1 if d >= enter else -1 if d <= -enter else 0
        elif cur == 1:
            cur = -1 if d <= -enter else 1 if d >= leave else 0
        else:
            cur = 1 if d >= enter else -1 if d <= -leave else 0
        lab[i] = cur
    return lab


def main():
    global FILES
    if "--old" in sys.argv:                                   # the models before the EMA inputs, for comparison
        FILES = {"5m": "5m", "15m": "bag_15m", "1h": "bag_1h", "4h": "4h"}
    df = aligned()
    print("aligned hourly rows:", len(df), "folds:", sorted(df["fold"].unique()), flush=True)
    L = np.column_stack([lg(df[f"p_{h}"].to_numpy()) for h in HS])
    later = df["fold"] != sorted(df["fold"].unique())[0]
    res = {"rows": int(len(df)), "note": "coins; hourly grid; folds 2024-07 → 2026-10 scored (the first fold only trains)"}

    # ---- A. headline
    avg = 1 / (1 + np.exp(-L.mean(axis=1)))
    y1h = (df["r_1h"] > 0).to_numpy().astype(int)
    learn = expanding(df, L, y1h).to_numpy()
    A = {}
    for name, p in (("avg", avg), ("learn", learn), ("1h_alone", df["p_1h"].to_numpy())):
        A[name] = {h: score(p[later.to_numpy()], (df.loc[later, f"r_{h}"] > 0).to_numpy()) for h in HS}
    full = LogisticRegression(C=1.0).fit(L, y1h)
    A["learned_weights"] = dict(zip(HS, [round(float(w), 3) for w in full.coef_[0]]))
    sides = np.sign(L)
    agree = np.abs(sides.sum(axis=1)) == 4
    y = (df["r_1h"] > 0).to_numpy()
    A["all_four_agree"] = {"share": round(float(agree[later].mean()), 3),
                           "hit_1h": round(float(((L[:, 2] > 0) == y)[agree & later.to_numpy()].mean()), 4),
                           "hit_1h_when_not": round(float(((L[:, 2] > 0) == y)[~agree & later.to_numpy()].mean()), 4)}
    folds = sorted(df.loc[later, "fold"].unique())
    A["learn_vs_avg_folds_better"] = int(sum(
        roc_auc_score(y[(df["fold"] == f).to_numpy()], learn[(df["fold"] == f).to_numpy()])
        > roc_auc_score(y[(df["fold"] == f).to_numpy()], avg[(df["fold"] == f).to_numpy()]) for f in folds))
    A["avg_vs_own_folds_better"] = {h: int(sum(
        roc_auc_score((df.loc[df["fold"] == f, f"r_{h}"] > 0), avg[(df["fold"] == f).to_numpy()])
        > roc_auc_score((df.loc[df["fold"] == f, f"r_{h}"] > 0), df.loc[df["fold"] == f, f"p_{h}"]) for f in folds)) for h in HS}
    # the headline shown as a probability: the average calibrated to the 1h outcome (isotonic, earlier folds only)
    avg_cal = expanding(df, lg(avg)[:, None], y1h).to_numpy()
    A["avg_calibrated_1h"] = {h: score(avg_cal[later.to_numpy()], (df.loc[later, f"r_{h}"] > 0).to_numpy()) for h in ("15m", "1h")}
    res["headline"] = A
    print("A", json.dumps(A), flush=True)

    # ---- B. cross-timeframe help
    B = {}
    for j, h in enumerate(HS):
        yh = (df[f"r_{h}"] > 0).to_numpy().astype(int)
        st = expanding(df, L, yh).to_numpy()
        own = df[f"p_{h}"].to_numpy()
        better = sum(roc_auc_score(yh[m], st[m]) > roc_auc_score(yh[m], own[m])
                     for m in ((df["fold"] == f).to_numpy() for f in folds))
        B[h] = {"own": score(own[later.to_numpy()], yh[later.to_numpy()]), "stacked": score(st[later.to_numpy()], yh[later.to_numpy()]),
                "folds_better": int(better), "of": len(folds)}
        print("B", h, json.dumps(B[h]), flush=True)
    res["cross_timeframe"] = B

    # ---- C. steady labels on the 5m series
    p5 = pd.read_parquet(PRED / f"{FILES['5m']}.parquet")
    p5 = p5[p5["sym"].isin(COINS)].sort_index()
    C = {}
    for name, (enter, leave) in {"fixed_2pt": (0.02, 0.02), "hyst_2_1": (0.02, 0.01), "hyst_2_05": (0.02, 0.005),
                                 "hyst_3_1": (0.03, 0.01), "hyst_25_15": (0.025, 0.015), "hyst_3_2": (0.03, 0.02)}.items():
        flips, hours, hit, n = 0, 0.0, 0, 0
        for s, g in p5.groupby("sym"):
            lab = labels(g["p"].to_numpy(), enter, leave)
            gaps = np.diff(g.index.asi8) / 6e10                      # minutes between rows; restart on gaps
            cont = np.r_[False, gaps <= 10.5]
            flips += int(((lab[1:] != lab[:-1]) & cont[1:]).sum())
            hours += float(cont.sum() * 10 / 60)
            yy = (g["ret"] > 0).to_numpy()
            k = lab != 0
            hit += int(((lab[k] > 0) == yy[k]).sum()); n += int(k.sum())
        C[name] = {"label_changes_per_hour": round(flips / hours, 3), "shown_share": round(n / len(p5), 3),
                   "shown_hit": round(hit / n, 4)}
        print("C", name, json.dumps(C[name]), flush=True)
    res["steady_labels_5m"] = C
    (PRED / ("headline_old.json" if "--old" in sys.argv else "headline.json")).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

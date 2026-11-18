"""Strong direction alerts (2026-11-18): when should the screen flag a direction as strongly backed?

Rule tested on the walk-forward out-of-sample forecasts (coins, hourly grid, 2024-07 → 2026-10; see headline_eval.py):
all four timeframes (5m / 15m / 1h / 4h) lean the same way AND the strength of their average, |mean log-odds|, is in
the top 5% of all readings. Stricter cuts were checked too (top 2%, top 1%): accuracy stopped improving and became
unstable between periods, so the top-5% cut is kept.

Each alert is scored at two checkpoints, 15 minutes and 1 hour after it fires (mark price higher / lower).

Two corrections found when the live engine was run over past data:
  1. the walk-forward test probabilities leaned towards "up" (1h median 51.2%), so their strongest 5% was 83% longs.
     The figures shown on screen come from a balanced re-test: each timeframe centred on earlier periods only,
     the 5% level also from earlier periods.
  2. the final production models give less extreme readings than the walk-forward models (median |z| 0.06 vs
     0.09), so a level taken from the test would almost never be reached live (0.12 alerts per coin per day
     instead of ~1.2). The live level is the production models' own 95th percentile of |z| over 2026.
Writes models/manifest.json["alerts"] (the live level and the tested figures) and data/preds/alerts.json.

  python research/alerts_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
from headline_eval import HS, aligned, lg  # noqa: E402
from train_eval import PRED  # noqa: E402

OUT = ROOT / "models"


def balanced(df, L):
    """Strongest 5%, all four agree, with each timeframe centred on earlier periods (no look-ahead)."""
    fold = df["fold"].to_numpy()
    folds = sorted(set(fold))
    t = df.index.get_level_values(0)
    rows = []
    for i, f in enumerate(folds[1:], 1):
        prev, cur = np.isin(fold, folds[:i]), fold == f
        Lc = L - np.median(L[prev], axis=0)
        zc = Lc.mean(axis=1)
        cut = np.quantile(np.abs(zc[prev]), 1 - 0.05)
        s = cur & (np.abs(np.sign(Lc).sum(axis=1)) == len(HS)) & (np.abs(zc) >= cut)
        d = np.sign(zc[s])
        rows.append({"fold": f, "n": int(s.sum()), "per_coin_day": s.sum() / (t[cur].max() - t[cur].min()).days / 8,
                     "long_share": float(np.mean(d > 0)),
                     "hit15": float(np.mean(df["r_15m"].to_numpy()[s] * d > 0)), "hit60": float(np.mean(df["r_1h"].to_numpy()[s] * d > 0))})
    r = pd.DataFrame(rows).set_index("fold")
    w = r["n"] / r["n"].sum()
    return {"hit15": round(float((r["hit15"] * w).sum()), 4), "hit60": round(float((r["hit60"] * w).sum()), 4),
            "long_share": round(float((r["long_share"] * w).sum()), 3),
            "by_period": {f: {"hit15": round(v["hit15"], 4), "hit60": round(v["hit60"], 4), "n": int(v["n"])} for f, v in r.iterrows()}}


def production_level(top: float = 0.05) -> dict:
    """95th percentile of |z| from the production models (pooled probabilities) on hourly coin rows of 2026."""
    sys.path.insert(0, str(ROOT / "server"))
    from xahoo.model import Models
    from train_eval import COINS
    M = Models(OUT)
    parts = []
    for s in COINS:
        f = pd.read_parquet(ROOT / "data/features" / f"{s}.parquet").join(pd.read_parquet(ROOT / "data/features_xr" / f"{s}.parquet"))
        f = f[(f.index >= "2026-01-01") & (f.index.minute == 0)].copy()
        f["sym"] = s
        parts.append(f)
    df = pd.concat(parts)
    out = M.predict(df, ["coin"] * len(df), df["sym"].tolist())
    P = np.array([[o[h]["p_pool"] for h in HS] for o in out])
    L = np.log(P / (1 - P))
    z = L.mean(axis=1)
    cut = float(np.quantile(np.abs(z), 1 - top))
    s = (np.abs(np.sign(L).sum(axis=1)) == len(HS)) & (np.abs(z) >= cut)
    days = (df.index.max() - df.index.min()).days
    return {"z_min": round(cut, 4), "per_coin_day": round(float(s.sum() / days / 8), 2), "long_share": round(float(np.mean(z[s] > 0)), 3),
            "median_abs_z": round(float(np.median(np.abs(z))), 4)}


def main():
    df = aligned()
    L = np.column_stack([lg(df[f"p_{h}"].to_numpy()) for h in HS])
    res = {"balanced": balanced(df, L)}
    print("balanced re-test:", json.dumps(res["balanced"]), flush=True)
    res["production"] = production_level()
    print("production level:", json.dumps(res["production"]), flush=True)
    (PRED / "alerts.json").write_text(json.dumps(res, indent=1))
    b, p = res["balanced"], res["production"]
    man = json.loads((OUT / "manifest.json").read_text())
    man["alerts"] = {"z_min": p["z_min"], "agree": len(HS), "window_min": 60, "checks": [15, 60],
                     "skill": {"hit15": b["hit15"], "hit60": b["hit60"], "per_coin_day": p["per_coin_day"], "long_share": p["long_share"],
                               "basis": "strongest 5% with all four timeframes agreeing; walk-forward 2024-07 → 2026-10, coins, "
                                        "balanced re-test; mark price after 15 min / 1 h"}}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print("manifest alerts:", man["alerts"])


if __name__ == "__main__":
    main()

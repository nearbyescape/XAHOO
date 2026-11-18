"""Strong direction alerts (2026-11-18): when should the screen flag a direction as strongly backed?

Rule tested on the walk-forward out-of-sample forecasts (coins, hourly grid, 2024-07 → 2026-10; see headline_eval.py):
all four timeframes (5m / 15m / 1h / 4h) lean the same way AND the strength of their average, |mean log-odds|, is in
the top 5% of all readings. Stricter cuts were checked too (top 2%, top 1%): accuracy stopped improving and became
unstable between periods, so the top-5% cut is kept.

Each alert is scored at two checkpoints, 15 minutes and 1 hour after it fires (mark price higher / lower).
Writes models/manifest.json["alerts"] (the cut and the tested figures) and data/preds/alerts.json.

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
TOP = 0.95


def main():
    df = aligned()
    L = np.column_stack([lg(df[f"p_{h}"].to_numpy()) for h in HS])
    z = L.mean(axis=1)
    later = (df["fold"] != sorted(df["fold"].unique())[0]).to_numpy()      # same scored periods as the headline test
    agree = np.abs(np.sign(L).sum(axis=1)) == len(HS)
    res = {}
    for q in (0.95, 0.98, 0.99):
        cut = float(np.quantile(np.abs(z[later]), q))
        s = later & agree & (np.abs(z) >= cut)
        d = np.sign(z[s])
        t = df.index.get_level_values(0)
        days = (t[later].max() - t[later].min()).days
        fold = df["fold"].to_numpy()[s]
        r = {}
        for h in ("15m", "1h", "4h"):
            ok = df[f"r_{h}"].to_numpy()[s] * d > 0
            r[h] = {"hit": round(float(ok.mean()), 4),
                    "by_period": {f: round(float(v), 4) for f, v in pd.Series(ok).groupby(fold).mean().items()}}
        res[f"top{round((1 - q) * 100)}"] = {
            "cut_z": round(cut, 4), "cut_avg_p": round(float(1 / (1 + np.exp(-cut))), 4), "n": int(s.sum()),
            "per_coin_day": round(float(s.sum() / days / 8), 2), "long_share": round(float((d > 0).mean()), 3), **r}
        print(f"top {round((1 - q) * 100)}%:", json.dumps(res[f"top{round((1 - q) * 100)}"]), flush=True)
    (PRED / "alerts.json").write_text(json.dumps(res, indent=1))
    k = res["top5"]
    man = json.loads((OUT / "manifest.json").read_text())
    man["alerts"] = {"z_min": k["cut_z"], "avg_p": k["cut_avg_p"], "agree": len(HS), "window_min": 60, "checks": [15, 60],
                     "skill": {"hit15": k["15m"]["hit"], "hit60": k["1h"]["hit"], "per_coin_day": k["per_coin_day"],
                               "long_share": k["long_share"],
                               "basis": "walk-forward 2024-07 → 2026-10, coins, hourly checks; mark price after 15 min / 1 h"}}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print("manifest alerts:", man["alerts"])


if __name__ == "__main__":
    main()

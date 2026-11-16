"""Write the overall direction (headline) and the steady-label band into models/manifest.json, from the out-of-sample
results of research/headline_eval.py (run that first).

  headline   equal-weight average of the 5m / 15m / 1h / 4h log-odds, calibrated to the 1h outcome with a binned
             isotonic map fitted on every out-of-sample row; skill figures are the walk-forward ones (each fold
             calibrated with earlier folds only)
  labels     hysteresis band chosen by a rule fixed before the results were seen: the fewest label changes per hour
             among the bands whose UP/DOWN hit rate is within 0.1 point of today's fixed 2-point band and which still
             show a side at least 85% as often

  python research/train_headline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
from headline_eval import HS, aligned, lg  # noqa: E402
from train_eval import PRED  # noqa: E402
from xahoo.model import binned_isotonic  # noqa: E402

OUT = ROOT / "models"
BANDS = {"fixed_2pt": (0.02, 0.02), "hyst_2_1": (0.02, 0.01), "hyst_2_05": (0.02, 0.005), "hyst_3_1": (0.03, 0.01),
         "hyst_25_15": (0.025, 0.015), "hyst_3_2": (0.03, 0.02)}


def main():
    res = json.loads((PRED / "headline.json").read_text())
    man = json.loads((OUT / "manifest.json").read_text())
    df = aligned()
    L = np.column_stack([lg(df[f"p_{h}"].to_numpy()) for h in HS])
    raw = 1 / (1 + np.exp(-L.mean(axis=1)))
    cal = binned_isotonic(raw, (df["r_1h"] > 0).to_numpy(float), 30)
    sk = res["headline"]["avg_calibrated_1h"]["1h"]
    agree = res["headline"]["all_four_agree"]
    man["headline"] = {
        "horizons": HS, "target": "1h", "calibration": cal,
        "skill": {"acc": sk["acc"], "auc": sk["auc"], "shown_hit": sk["shown_hit"], "shown_share": sk["shown_share"],
                  "agree_share": agree["share"], "agree_hit": agree["hit_1h"],
                  "basis": "walk-forward 2024-07 → 2026-10, coins; scored on the next hour"}}
    C = res["steady_labels_5m"]
    base = C["fixed_2pt"]
    ok = {k: v for k, v in C.items() if v["shown_hit"] >= base["shown_hit"] - 0.001 and v["shown_share"] >= 0.85 * base["shown_share"]}
    pick = min(ok, key=lambda k: ok[k]["label_changes_per_hour"])
    man["labels"] = {"enter": BANDS[pick][0], "leave": BANDS[pick][1], "rule": pick, "tested": C[pick],
                     "basis": "5m forecasts every 10 minutes, coins, 2024-01 → 2026-10"}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print("headline cal", cal["y"][0], "…", cal["y"][-1], "| skill", man["headline"]["skill"])
    print("labels:", pick, BANDS[pick], C[pick], "vs fixed", base)


if __name__ == "__main__":
    main()

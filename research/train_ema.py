"""Production direction models with the EMA 9/26 (x_) and market-state (r_) inputs, for the horizons where they
tested better in at least 4 of 5 walk-forward folds (research/ema_regime_eval.py, 2026-11-17):

  5m   + EMA           single model (as before)            5 of 5 folds better
  15m  + EMA + state   5 models averaged (as before)       4 of 5
  1h   + EMA           5 models averaged (as before)       4 of 5
  4h, 1m, 1d and the metal family are unchanged.

For each horizon: walk-forward out-of-sample predictions with exactly the production recipe -> calibration map and
skill figures; then the final model(s) on all coin data through Oct 2026; the manifest entry gets the files, the
input list (features_dir) and the calibration. Run train_market_cal.py afterwards for the per-market correction.

  python research/train_ema.py 5m      (one horizon per process keeps memory low)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
from ema_regime_eval import load  # noqa: E402
from train_bag import oos_bagged  # noqa: E402
from train_eval import COINS, PRED, make_model, walk_forward  # noqa: E402
from train_final import stats, tier  # noqa: E402
from xahoo.model import binned_isotonic  # noqa: E402

OUT = ROOT / "models"
PLAN = {"5m": ("ema", 1), "15m": ("both", 5), "1h": ("ema", 5)}
VERSION = "2026.11.18"


def main():
    man = json.loads((OUT / "manifest.json").read_text())
    for h in sys.argv[1:]:
        variant, seeds = PLAN[h]
        df, base, xcols, rcols = load(h)
        df = df.sort_index()
        assert base == man["features"], "base inputs differ from the production list"
        cols = base + xcols + (rcols if variant == "both" else [])
        if seeds == 1:
            oos, _ = walk_forward(df, cols, h, label=f"{h} {variant}")
            oos = oos[oos["sym"].isin(COINS)]
        else:
            oos = oos_bagged(df, cols, h)
        oos.to_parquet(PRED / f"ema_{h}.parquet")
        coins = df[df["sym"].isin(COINS)]
        files = []
        for s in range(1, seeds + 1):
            m = make_model(len(coins), h, seed=s)
            m.fit(coins[cols], (coins["ret"] > 0).astype(int))
            name = f"coin_dir_{h}.txt" if s == 1 else f"coin_dir_{h}_s{s}.txt"
            m.booster_.save_model(str(OUT / name))
            files.append(name)
        spec = man["families"]["coin"][h]
        spec["files"]["dir"] = files if seeds > 1 else files[0]
        spec["features_dir"] = cols
        spec["calibration"] = binned_isotonic(oos["raw"].to_numpy(float), (oos["ret"] > 0).to_numpy(float), 30)
        spec.pop("market_cal", None)                     # refitted by train_market_cal.py on the new predictions
        if seeds > 1:
            spec["bagged"] = seeds
        else:
            spec.pop("bagged", None)
        pooled = stats(oos["ret"] > 0, oos["p"].to_numpy(float))
        extra = "EMA 9/26" + (" + market state" if variant == "both" else "")
        for s in COINS:
            g = oos[oos["sym"] == s]
            st = stats(g["ret"] > 0, g["p"].to_numpy(float))
            man["skill"][s][h] = {**st, "tier": tier(pooled["auc"]), "show": tier(pooled["auc"]) > 0,
                                  "basis": f"walk-forward 2024-01 → 2026-10, with {extra}" + (f", {seeds} models averaged" if seeds > 1 else "")}
        print(h, variant, "pooled out-of-sample:", pooled, flush=True)
        man["version"] = VERSION
        (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
        print("manifest updated for", h, flush=True)


if __name__ == "__main__":
    main()

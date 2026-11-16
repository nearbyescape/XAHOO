"""Do spot-market flow (f_) and the futures premium index (g_) make the forecasts more accurate?

  python research/extra_eval.py build            # data/features_extra/{SYM}.parquet
  python research/extra_eval.py 1h 4h ...        # walk-forward: base vs +spot vs +premium vs +both

Same folds, coins and model settings as train_eval.py. Writes data/preds/extra_{h}.json and, for each variant,
data/preds/extra_{variant}_{h}.parquet.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server")); sys.path.insert(0, str(ROOT / "research"))
from train_eval import COINS, METALS, PRED, STEP, walk_forward  # noqa: E402
from xahoo.features import extra  # noqa: E402

BN, FEAT, XF = ROOT / "data/binance", ROOT / "data/features", ROOT / "data/features_extra"


def build():
    XF.mkdir(exist_ok=True)
    for sym in COINS + METALS:
        t0 = time.time()
        k = pd.read_parquet(BN / f"{sym}_1m.parquet")
        sp = pd.read_parquet(BN / f"{sym}_spot.parquet") if (BN / f"{sym}_spot.parquet").exists() else None
        pr = pd.read_parquet(BN / f"{sym}_prem.parquet") if (BN / f"{sym}_prem.parquet").exists() else None
        x = extra(k, sp, pr)
        idx = pd.read_parquet(FEAT / f"{sym}.parquet", columns=["y_1m"]).index
        x = x.reindex(idx)
        x.to_parquet(XF / f"{sym}.parquet")
        print(f"{sym}: {x.shape} missing {x.isna().mean().round(3).max()} ({time.time() - t0:.0f}s)", flush=True)


def load(h: str):
    step, parts = STEP[h], []
    for sym in COINS + METALS:
        f = pd.read_parquet(FEAT / f"{sym}.parquet")
        cols = [c for c in f.columns if c[:2] in ("a_", "b_", "c_", "d_")]
        x = pd.read_parquet(XF / f"{sym}.parquet")
        f = f[cols + [f"y_{h}"]].join(x)
        minute = f.index.asi8 // (60 * {"ns": 10**9, "us": 10**6, "ms": 10**3, "s": 1}[f.index.unit])
        f = f[minute % step == 0].rename(columns={f"y_{h}": "ret"})
        f = f[f["ret"].notna() & (f["ret"] != 0)]
        f["sym"] = sym
        parts.append(f)
    df = pd.concat(parts).sort_index()
    xc = pd.read_parquet(XF / f"{COINS[0]}.parquet").columns          # coins have every extra column
    return df, cols, [c for c in xc if c.startswith("f_")], [c for c in xc if c.startswith("g_")]


def summary(pr):
    c = pr[pr["sym"].isin(COINS)]
    y, p = (c["ret"] > 0).to_numpy(), c["p"].to_numpy()
    sel = (p >= 0.55) | (p <= 0.45)
    return {"auc": round(float(roc_auc_score(y, p)), 4), "accuracy": round(float(((p > 0.5) == y).mean()), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 5),
            "conf55": [round(float(sel.mean()), 4), round(float(((p[sel] > 0.5) == y[sel]).mean()), 4) if sel.any() else None],
            "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in c.groupby("fold")}}


def main():
    if sys.argv[1] == "build":
        return build()
    for h in sys.argv[1:]:
        df, base, fcols, gcols = load(h)
        res = {}
        for name, cols in (("base", base), ("spot", base + fcols), ("premium", base + gcols), ("both", base + fcols + gcols)):
            pr, imp = walk_forward(df, cols, h, label=f"{h} {name}")
            res[name] = summary(pr)
            if name != "base":
                res[name]["folds_better"] = sum(res[name]["by_fold"][f] > res["base"]["by_fold"][f] for f in res["base"]["by_fold"])
                res[name]["top_new"] = {k: int(v) for k, v in imp[[c for c in imp.index if c[:2] in ("f_", "g_")]].head(6).items()}
            pr.to_parquet(PRED / f"extra_{name}_{h}.parquet")
            print(h, name, json.dumps(res[name]), flush=True)
        (PRED / f"extra_{h}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

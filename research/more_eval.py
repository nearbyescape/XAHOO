"""Does training on 16 coins (the 8 on screen + 8 more liquid ones) beat training on the 8?
Scored only on the 8 screen coins, same folds and settings as train_eval.py.
  python research/more_eval.py 1h 15m ...     -> data/preds/more_{h}.json, more_{h}.parquet
"""
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_eval as te  # noqa: E402

MORE = ["LTCUSDT", "BCHUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "ATOMUSDT", "ETCUSDT", "NEARUSDT"]


def load(h):
    step, parts = te.STEP[h], []
    for sym in te.COINS + MORE:
        f = pd.read_parquet(te.FEAT / f"{sym}.parquet")
        cols = [c for c in f.columns if c[:2] in ("a_", "b_", "c_", "d_")]
        minute = f.index.asi8 // (60 * {"ns": 10**9, "us": 10**6, "ms": 10**3, "s": 1}[f.index.unit])
        f = f[minute % step == 0][cols + [f"y_{h}"]].rename(columns={f"y_{h}": "ret"})
        f = f[f["ret"].notna() & (f["ret"] != 0)]
        f["sym"] = sym
        parts.append(f)
    return pd.concat(parts).sort_index(), cols


def summary(pr):
    c = pr[pr["sym"].isin(te.COINS)]
    y, p = (c["ret"] > 0).to_numpy(), c["p"].to_numpy()
    sel = (p >= 0.55) | (p <= 0.45)
    return {"auc": round(float(roc_auc_score(y, p)), 4), "accuracy": round(float(((p > 0.5) == y).mean()), 4),
            "conf55": [round(float(sel.mean()), 4), round(float(((p[sel] > 0.5) == y[sel]).mean()), 4)],
            "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in c.groupby("fold")}}


if __name__ == "__main__":
    for h in sys.argv[1:]:
        df, cols = load(h)
        res = {}
        for name, syms in (("8 coins", te.COINS), ("16 coins", te.COINS + MORE)):
            pr, _ = te.walk_forward(df, cols, h, label=f"{h} {name}", train_syms=syms)
            res[name] = summary(pr)
            if name == "16 coins":
                pr.to_parquet(te.PRED / f"more_{h}.parquet")
            print(h, name, json.dumps(res[name]), flush=True)
        res["folds_better"] = sum(res["16 coins"]["by_fold"][f] > res["8 coins"]["by_fold"][f] for f in res["8 coins"]["by_fold"])
        print(h, "folds better:", res["folds_better"], flush=True)
        (te.PRED / f"more_{h}.json").write_text(json.dumps(res, indent=1))

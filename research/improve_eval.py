"""Can the probabilities be made more accurate? Two honest tests on the same walk-forward folds.

1. Market-wide layer ("e_"): at each minute, the average of key trend / flow / positioning inputs across the
   eight coins, and each coin's distance from that average. The idea: a coin moving with the whole market
   behaves differently from one moving alone. Compared fold by fold against the current 62 inputs.
2. Agreement: does the forecast get more accurate when other horizons, the market as a whole, or the order
   flow agree with it? Measured from the saved out-of-sample predictions (data/preds).

  python research/improve_eval.py 1h 4h 15m
Writes data/preds/improve_{h}.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_eval import COINS, PRED, load, walk_forward  # noqa: E402

MKT_COLS = ["a_ret15", "a_ret60", "a_ret240", "a_ret1440", "a_sma240", "b_imb5", "b_imb15", "b_imb60",
            "c_oi_1h", "c_taker_1h", "c_funding_z", "c_ls_acct_z"]


def add_market(df: pd.DataFrame) -> list[str]:
    coins = df[df["sym"].isin(COINS)]
    mean = coins.groupby(level=0)[MKT_COLS].mean()
    new = []
    for c in MKT_COLS:
        m = mean[c].reindex(df.index).to_numpy()
        df[f"e_m_{c[2:]}"] = m.astype("float32")
        new.append(f"e_m_{c[2:]}")
        if c.startswith(("a_ret", "b_imb")):
            df[f"e_r_{c[2:]}"] = (df[c].to_numpy() - m).astype("float32")
            new.append(f"e_r_{c[2:]}")
    up = coins.assign(u=(coins["a_ret60"] > 0).astype("float32")).groupby(level=0)["u"].mean()
    df["e_breadth60"] = up.reindex(df.index).to_numpy().astype("float32")
    new.append("e_breadth60")
    return new


def test_market_layer(h: str) -> dict:
    df, cols = load(h)
    df = df.sort_index()
    new = add_market(df)
    base, _ = walk_forward(df, cols, h, label="base")
    plus, imp = walk_forward(df, cols + new, h, label="+market")
    out = {}
    for name, pr in (("base", base), ("plus", plus)):
        c = pr[pr["sym"].isin(COINS)]
        out[name] = {"auc": round(float(roc_auc_score(c["ret"] > 0, c["p"])), 4),
                     "accuracy": round(float(((c["p"] > 0.5) == (c["ret"] > 0)).mean()), 4),
                     "by_fold": {f: round(float(roc_auc_score(g["ret"] > 0, g["p"])), 4) for f, g in c.groupby("fold")}}
        sel = (c["p"] >= 0.55) | (c["p"] <= 0.45)
        out[name]["conf55"] = {"share": round(float(sel.mean()), 4),
                               "hit": round(float(((c["p"][sel] > 0.5) == (c["ret"][sel] > 0)).mean()), 4)}
    out["folds_better"] = sum(out["plus"]["by_fold"][f] > out["base"]["by_fold"][f] for f in out["base"]["by_fold"])
    out["top_market_features"] = {k: int(v) for k, v in imp[[c for c in imp.index if c.startswith("e_")]].head(8).items()}
    plus.to_parquet(PRED / f"plus_{h}.parquet")
    return out


def agreement(h: str, others=("15m", "1h", "4h")) -> dict:
    """Hit rate of horizon h's forecast, split by whether other horizons and the market lean the same way."""
    main = pd.read_parquet(PRED / f"{h}.parquet")
    main = main[main["sym"].isin(COINS)].reset_index().rename(columns={"index": "t", "open_time": "t"})
    tcol = main.columns[0]
    main = main.rename(columns={tcol: "t"})
    for o in others:
        if o == h:
            continue
        x = pd.read_parquet(PRED / f"{o}.parquet")
        x = x[x["sym"].isin(COINS)].reset_index()
        x = x.rename(columns={x.columns[0]: "t"})[["t", "sym", "p"]].rename(columns={"p": f"p_{o}"})
        main = pd.merge_asof(main.sort_values("t"), x.sort_values("t"), on="t", by="sym", direction="backward",
                             tolerance=pd.Timedelta(minutes=60))
    mkt = main.groupby("t")["p"].mean().rename("p_mkt")
    main = main.join(mkt, on="t")
    main["side"] = np.sign(main["p"] - 0.5)
    main["hit"] = (main["p"] > 0.5) == (main["ret"] > 0)
    oth = [c for c in main.columns if c.startswith("p_") and c != "p_mkt"]
    agree_h = np.all([np.sign(main[c] - 0.5) == main["side"] for c in oth], axis=0)
    agree_m = np.sign(main["p_mkt"] - 0.5) == main["side"]
    strong = (main["p"] - 0.5).abs() >= 0.05
    res = {}
    for name, mask in {"all": np.ones(len(main), bool), "strong (>=55%)": strong.to_numpy(),
                       "other horizons agree": agree_h, "market agrees": agree_m.to_numpy(),
                       "horizons + market agree": agree_h & agree_m.to_numpy(),
                       "strong + horizons + market agree": strong.to_numpy() & agree_h & agree_m.to_numpy(),
                       "strong + disagreement": strong.to_numpy() & ~agree_h}.items():
        g = main[mask]
        res[name] = {"share": round(float(mask.mean()), 4), "n": int(mask.sum()),
                     "hit": round(float(g["hit"].mean()), 4) if len(g) else None,
                     "by_fold": {f: round(float(x["hit"].mean()), 4) for f, x in g.groupby("fold")}}
    return res


def main():
    hs = [a for a in sys.argv[1:] if not a.startswith("-")] or ["1h"]
    for h in hs:
        rep = {"agreement": agreement(h)}
        print(h, "agreement:", json.dumps({k: (v["share"], v["hit"]) for k, v in rep["agreement"].items()}), flush=True)
        if "--no-market" not in sys.argv:
            rep["market_layer"] = test_market_layer(h)
            m = rep["market_layer"]
            print(h, "market layer:", json.dumps({k: m[k] for k in ("base", "plus", "folds_better")}), flush=True)
        (PRED / f"improve_{h}.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

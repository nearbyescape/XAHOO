"""Gold/silver trend-only direction model on 17 years of spot prices (HistData 1m, 2009-2026).

Binance has under a year of metals data, so this tests whether the trend layer alone (a_ features, which need only
prices) gives usable direction probabilities at 1h / 4h / 1d. Walk-forward by year from 2017.
  python research/metals_trend.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from xahoo.features import build   # noqa: E402

HD = ROOT / "data" / "histdata"
H = {"15m": (15, 15), "1h": (60, 30), "4h": (240, 60), "1d": (1440, 240)}      # horizon minutes, sampling step
OUT = ROOT / "data" / "preds"


def load(sym):
    files = sorted((HD / sym).glob("*.csv.gz"))
    files = [f for f in files if not (len(f.name.split(".")[0]) == 6 and (HD / sym / f"{f.name[:4]}.csv.gz").exists())]
    m = pd.concat(pd.read_csv(f, index_col=0, parse_dates=True)[["open", "high", "low", "close"]] for f in files).sort_index()
    m = m[~m.index.duplicated()]
    m["volume"], m["count"], m["taker_buy_volume"] = 1.0, 1.0, 0.5
    return m


frames = {}
for sym in ("XAUUSD", "XAGUSD"):
    k = load(sym)
    f = build(k)                                   # price-only: metrics, funding and leader omitted
    cols = [c for c in f.columns if c.startswith("a_")]
    lc = np.log(k["close"])
    for name, (n, _) in H.items():
        f[f"y_{name}"] = (np.log(k["close"].reindex(k.index + pd.Timedelta(minutes=n))).to_numpy() - lc.to_numpy())
    f["sym"] = sym
    frames[sym] = f.iloc[10080:]
    print(sym, len(f), "rows", flush=True)

rows = []
for name, (n, step) in H.items():
    parts = []
    for f in frames.values():
        minute = f.index.asi8 // (60 * 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[f.index.unit])
        g = f[minute % step == 0][cols + [f"y_{name}", "sym"]].rename(columns={f"y_{name}": "ret"})
        parts.append(g[g["ret"].notna() & (g["ret"] != 0)])
    df = pd.concat(parts).sort_index()
    preds = []
    for year in range(2017, 2027):
        a, b = pd.Timestamp(f"{year}-01-01", tz="UTC"), pd.Timestamp(f"{year + 1}-01-01", tz="UTC")
        train = df[df.index < a - pd.Timedelta(minutes=n)]
        test = df[(df.index >= a) & (df.index < b)]
        m = LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=15, max_bin=63, min_child_samples=500,
                           subsample=0.7, subsample_freq=1, colsample_bytree=0.5, reg_lambda=10.0, n_jobs=4, verbose=-1)
        m.fit(train[cols], (train["ret"] > 0).astype(int))
        preds.append(pd.DataFrame({"p": m.predict_proba(test[cols])[:, 1], "ret": test["ret"].to_numpy(),
                                   "sym": test["sym"].to_numpy(), "year": year}))
    pr = pd.concat(preds)
    pr.to_parquet(OUT / f"metals_trend_{name}.parquet")
    df[df.index < pd.Timestamp("2026-01-01", tz="UTC")].to_parquet(OUT / f"metals_trend_train_{name}.parquet")
    y = pr["ret"] > 0
    yr = {int(k): round(roc_auc_score(g["ret"] > 0, g["p"]), 3) for k, g in pr.groupby("year")}
    sel = (pr["p"] >= 0.55) | (pr["p"] <= 0.45)
    rows.append({"horizon": name, "n": len(pr), "auc": round(roc_auc_score(y, pr["p"]), 4),
                 "accuracy": round(float(((pr["p"] > 0.5) == y).mean()), 4),
                 "auc gold": round(roc_auc_score(y[pr.sym == "XAUUSD"], pr["p"][pr.sym == "XAUUSD"]), 4),
                 "auc silver": round(roc_auc_score(y[pr.sym == "XAGUSD"], pr["p"][pr.sym == "XAGUSD"]), 4),
                 "years above 0.5": f"{sum(v > 0.5 for v in yr.values())}/{len(yr)}",
                 "raw conf55 cover": round(float(sel.mean()), 3),
                 "raw conf55 hit": round(float(((pr['p'][sel] > 0.5) == y[sel]).mean()), 4) if sel.sum() > 50 else None})
    print(rows[-1], yr, flush=True)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).to_string(index=False))

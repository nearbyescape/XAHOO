"""Build long-history bars for swing research from HistData 1m files (2009 →): daily (trading day ends 22:00 UTC =
17:00 New York), 1h and 5m. Cached as pickles under data/swing/. Usage: python research/swing_data.py"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from histdata import ROOT as HD

OUT = HD.parent / "swing"
AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def build(sym: str):
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((HD / sym).glob("*.csv.gz"))
    files = [f for f in files if not (len(f.name.split(".")[0]) == 6 and (HD / sym / f"{f.name[:4]}.csv.gz").exists())]
    parts = [pd.read_csv(f, index_col=0, parse_dates=True)[["open", "high", "low", "close"]] for f in files]
    m1 = pd.concat(parts).sort_index()
    m1 = m1[~m1.index.duplicated()]
    for name, rule in (("5m", "5min"), ("1h", "1h")):
        df = m1.resample(rule).agg(AGG).dropna()
        df.to_pickle(OUT / f"{sym}_{name}.pkl")
        print(sym, name, len(df), df.index[0], "→", df.index[-1], flush=True)
    sh = m1.copy()
    sh.index = sh.index + pd.Timedelta(hours=2)            # 22:00 UTC becomes midnight: index = trading date
    d = sh.resample("1D").agg(AGG).dropna()
    n = sh["close"].resample("1D").count().reindex(d.index)
    d = d[(n > 300) & (d.index.dayofweek < 5)]             # drop stub sessions
    d.to_pickle(OUT / f"{sym}_1d.pkl")
    print(sym, "1d", len(d), d.index[0].date(), "→", d.index[-1].date(), flush=True)

if __name__ == "__main__":
    for s in ("XAUUSD", "XAGUSD"):
        build(s)

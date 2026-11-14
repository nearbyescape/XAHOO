"""The current live strategy (StrategyParams.trader()) on 2009-2026 HistData 1m bars, year by year. Unchanged rules.
(docs/BACKTEST.md run 20). HistData has no volume: constant 1 (the strategy doesn't use volume)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from histdata import ROOT as HD
from xahoo.config import StrategyParams
from xahoo.engine import generate, run_backtest, stats

def load(sym):
    files = sorted((HD / sym).glob("*.csv.gz"))
    files = [f for f in files if not (len(f.name.split(".")[0]) == 6 and (HD / sym / f"{f.name[:4]}.csv.gz").exists())]
    m = pd.concat(pd.read_csv(f, index_col=0, parse_dates=True) for f in files).sort_index()
    return m[~m.index.duplicated()]

full = {s: load(s) for s in ("XAUUSD", "XAGUSD")}
p = StrategyParams.trader()
rows = []
for y in range(2010, 2027):
    a, b = pd.Timestamp(f"{y}-01-01", tz="UTC"), pd.Timestamp(f"{y}-12-31 23:59", tz="UTC")
    data = {s: m[(m.index >= a - pd.Timedelta(days=100)) & (m.index <= b)] for s, m in full.items()}
    c = generate(data, p, p.exec_tfs)
    c = c[c["close_time"] >= a].reset_index(drop=True) if len(c) else c
    bt = run_backtest(data, p, p.exec_tfs, cand=c)
    s = stats(bt)
    g = bt.groupby("symbol").r.sum().round(1).to_dict() if len(bt) else {}
    rows.append({"year": y, "trades": s["signals"], "win%": s.get("win_rate"), "avg R": s.get("avg_r"),
                 "net R": s.get("total_r"), "maxDD R": s.get("max_dd_r"), "gold R": g.get("XAUUSD"), "silver R": g.get("XAGUSD")})
    print(rows[-1], flush=True)
df = pd.DataFrame(rows)
print(df.to_string(index=False))
print("total net R", round(df["net R"].sum(), 1), "| losing years", int((df["net R"] < 0).sum()), "of", len(df))

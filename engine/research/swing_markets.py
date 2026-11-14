"""Does the daily trend strategy (50/200 trend + 20-day breakout + 3-ATR trail, untuned) work on other markets?
Builds daily bars for each market from HistData and runs the identical rules. (docs/BACKTEST.md run 19)"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import swing
from swing_data import build
from swing import PERIODS, load, s_ma_trend, simulate, summarize

MARKETS = {"XAUUSD": 0.30, "XAGUSD": 0.03, "EURUSD": 0.00008, "GBPUSD": 0.00012, "USDJPY": 0.012,
           "SPXUSD": 0.5, "NSXUSD": 1.5, "WTIUSD": 0.04}
swing.SPREAD.update(MARKETS)
rows, allt = [], []
for m in MARKETS:
    if not (swing.SW / f"{m}_1d.pkl").exists():
        build(m)
    d = load(m)
    ent, ex, kw = s_ma_trend(d, 20, 3.0)
    t = simulate(d, m, ent, ex, **kw)
    allt.append(t)
    row = {"market": m, **summarize(t)}
    for pn, (a, b) in PERIODS.items():
        row[pn.split()[0]] = round(t[(t.t >= a) & (t.t <= f"{b}-12-31")].r.mean(), 3)
    rows.append(row)
t = pd.concat(allt).sort_values("exit")
row = {"market": "ALL 8 (portfolio)", **summarize(t)}
for pn, (a, b) in PERIODS.items():
    row[pn.split()[0]] = round(t[(t.t >= a) & (t.t <= f"{b}-12-31")].r.mean(), 3)
rows.append(row)
pd.set_option("display.width", 230)
print(pd.DataFrame(rows).to_string(index=False))
yr = t.groupby(t.exit.dt.year).r.sum().round(1)
print("\nportfolio net R by year:", yr.to_dict())
print("losing years:", int((yr < 0).sum()), "of", len(yr))

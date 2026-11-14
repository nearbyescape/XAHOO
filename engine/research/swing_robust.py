"""T2 (trend + breakout + ATR trail): parameter neighbourhood on daily bars, and the same rules on 4h and 1h bars."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from swing import PERIODS, load, s_ma_trend, simulate, summarize

rows = []
for tf in ("1d", "4h", "1h"):
    data = {s: load(s, tf) for s in ("XAUUSD", "XAGUSD")}
    grid = [(b, k) for b in (10, 20, 40, 55) for k in (2.0, 3.0, 4.0)] if tf == "1d" else [(20, 3.0), (55, 3.0), (55, 4.0)]
    for brk, k in grid:
        ts = []
        for sym, d in data.items():
            ent, ex, kw = s_ma_trend(d, brk, k)
            ts.append(simulate(d, sym, ent, ex, **kw))
        t = pd.concat(ts).sort_values("t")
        row = {"tf": tf, "breakout": brk, "trail ATR": k, **{k2: v for k2, v in summarize(t).items() if k2 in ("trades", "per yr", "win%", "avg R", "R/yr", "PF", "maxDD R", "avg days")}}
        for pn, (a, b) in PERIODS.items():
            row[pn.split()[0] + " avgR"] = round(t[(t.t >= a) & (t.t <= f"{b}-12-31")].r.mean(), 3)
        g = t.groupby("sym").r.mean().round(3)
        row["gold avgR"], row["silver avgR"] = g.get("XAUUSD"), g.get("XAGUSD")
        rows.append(row)
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))

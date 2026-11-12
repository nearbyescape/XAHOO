"""Win rate vs return: same entries, different stop/target placement (docs/BACKTEST.md run 6)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import generate, run_backtest
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
a, b = date(2026, 2, 10), date(2026, 11, 11)
data = {s: dukascopy.load(s, CACHE, a - timedelta(days=40), b) for s in ("XAUUSD", "XAGUSD")}
p = StrategyParams()
base = generate(data, p, p.exec_tfs)
base = base[base["close_time"] >= pd.Timestamp(a, tz="UTC")].reset_index(drop=True)
rows = []
for k in (1.0, 2.0, 3.0):              # stop distance, x original stop
    for x in (0.25, 0.5, 0.75, 1.0, 1.5):   # single take-profit, x original stop
        c = base.copy()
        d, r0 = c["dir"], c["risk"]
        c["sl"] = c["entry"] - d * k * r0
        for t in ("tp1", "tp2", "tp3"):
            c[t] = c["entry"] + d * x * r0
        p.partials = (1.0, 0.0, 0.0)
        bt = run_backtest(data, p, p.exec_tfs, cand=c)
        rr = bt["r"]                    # in units of the money risked (k * r0)
        rows.append({"stop": f"{k:.0f}x", "target": f"{x}x", "reward:risk": f"1:{k/x:.1f}",
                     "trades": len(bt), "win%": round((rr > 0).mean() * 100, 1),
                     "avg R/trade": round(rr.mean(), 3), "net R": round(rr.sum(), 1),
                     "worst DD R": round((rr.cumsum() - rr.cumsum().cummax()).min(), 1)})
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).to_string(index=False))

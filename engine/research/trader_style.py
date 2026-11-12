"""Trader-style management (from his posted trades) vs XAHOO v1, all 2026, both metals.
Variants were fixed before running (docs/BACKTEST.md run 7)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import generate, run_backtest, stats
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
a, b = date(2026, 2, 10), date(2026, 11, 11)
data = {s: dukascopy.load(s, CACHE, a - timedelta(days=40), b) for s in ("XAUUSD", "XAGUSD")}
start = pd.Timestamp(a, tz="UTC")
TRADER = dict(partials=(1.0, 0.0, 0.0), move_sl_to_be_at_tp1=False, be_at_r=1.0)
VARIANTS = {
    "v1 baseline (partials 0.75/1.5/2.5R)": {},
    "trader: BE@1R, single TP 3R": {**TRADER, "tp_r": (3.0, 3.0, 3.0)},
    "trader: BE@1R, single TP 5R": {**TRADER, "tp_r": (5.0, 5.0, 5.0)},
    "trader: BE@1R, TP at liquidity (3-10R)": {**TRADER, "target_mode": "liquidity", "min_rr": 3.0},
    "trader: BE@1R, TP at liquidity (2-10R)": {**TRADER, "target_mode": "liquidity", "min_rr": 2.0},
    "trader: liquidity 3-10R + EMA200 retest": {**TRADER, "target_mode": "liquidity", "min_rr": 3.0,
                                                 "enabled_setups": ("sweep", "ema12_pullback", "ema200_retest", "range")},
}
rows = []
for name, kw in VARIANTS.items():
    for asia in (False, True):
        p = StrategyParams()
        for k, v in kw.items():
            setattr(p, k, v)
        p.trade_asia = asia
        c = generate(data, p, p.exec_tfs)
        c = c[c["close_time"] >= start].reset_index(drop=True) if len(c) else c
        bt = run_backtest(data, p, p.exec_tfs, cand=c)
        s = stats(bt)
        rows.append({"variant": name, "asia": asia, "trades": s["signals"], "per_day": s["per_day"],
                     "green% (win+BE)": s["green_rate"], "real win%": s["win_rate"], "avg R": s["avg_r"],
                     "net R": s["total_r"], "PF": s["profit_factor"], "max DD R": s["max_dd_r"]})
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).to_string(index=False))

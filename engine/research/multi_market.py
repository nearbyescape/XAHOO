"""Run the live strategy UNCHANGED (StrategyParams.trader()) on other markets (docs/BACKTEST.md run 16).
No parameter is tuned here, so every year is out-of-sample for these markets."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from histdata import load
from xahoo.config import StrategyParams
from xahoo.engine import generate, run_backtest, stats

YEARS = {"2024": ("2024-03-01", "2024-12-31"), "2025": ("2025-02-10", "2025-12-31"), "2026": ("2026-02-10", "2026-10-31")}
rows = []
for mkt in ("NSXUSD", "SPXUSD", "EURUSD"):
    full = load(mkt)
    for y, (a, b) in YEARS.items():
        data = {mkt: full[(full.index >= pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=60)) &
                          (full.index < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1))]}
        p = StrategyParams.trader()
        c = generate(data, p, p.exec_tfs)
        c = c[c["close_time"] >= pd.Timestamp(a, tz="UTC")].reset_index(drop=True) if len(c) else c
        bt = run_backtest(data, p, p.exec_tfs, cand=c)
        s = stats(bt)
        rows.append({"market": mkt, "year": y, "trades": s["signals"], "win%": s.get("win_rate"),
                     "avg R": s.get("avg_r"), "net R": s.get("total_r"), "PF": s.get("profit_factor"),
                     "max DD": s.get("max_dd_r")})
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).to_string(index=False))

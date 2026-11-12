"""Liquidity sweep + buyer/seller pressure setup. Develop on 2025, test once on 2026 (docs/BACKTEST.md run 8).
usage: python research/liquidity_pressure.py dev|test [variant-name]"""
import sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import breakdown, generate, run_backtest, stats
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
TRADER = dict(partials=(1.0, 0.0, 0.0), move_sl_to_be_at_tp1=False, be_at_r=1.0)
BASE = dict(enabled_setups=("liquidity_pressure",), trade_asia=True)
VARIANTS = {
    "A liq-target 2-10R, BE@1R": {**TRADER, "target_mode": "liquidity", "min_rr": 2.0},
    "B liq-target 3-10R, BE@1R": {**TRADER, "target_mode": "liquidity", "min_rr": 3.0},
    "C partials 0.75/1.5/2.5R": {},
    "D fixed 2R, BE@1R": {**TRADER, "tp_r": (2.0, 2.0, 2.0)},
}
WINDOWS = {
    "dev": {"XAUUSD": (date(2025, 2, 10), date(2025, 12, 31)), "XAGUSD": (date(2025, 2, 10), date(2025, 8, 31))},
    "test": {"XAUUSD": (date(2026, 2, 10), date(2026, 11, 11)), "XAGUSD": (date(2026, 2, 10), date(2026, 11, 11))},
}
mode = sys.argv[1]
only = sys.argv[2:] or None
rows, detail = [], {}
data = {s: dukascopy.load(s, CACHE, a - timedelta(days=40), b) for s, (a, b) in WINDOWS[mode].items()}
starts = {s: pd.Timestamp(a, tz="UTC") for s, (a, b) in WINDOWS[mode].items()}
for name, kw in VARIANTS.items():
    for bias in (False, True):
        tag = f"{name} | bias={'on' if bias else 'off'}"
        if only and tag not in only:
            continue
        p = StrategyParams()
        for k, v in {**BASE, **kw}.items():
            setattr(p, k, v)
        p.lp_require_bias = bias
        c = generate(data, p, p.exec_tfs)
        if len(c):
            c = c[c["close_time"] >= c["symbol"].map(starts)].reset_index(drop=True)
        bt = run_backtest(data, p, p.exec_tfs, cand=c)
        s = stats(bt)
        rows.append({"variant": tag, "trades": s["signals"], "per_day": s.get("per_day"),
                     "green%": s.get("green_rate"), "win%": s.get("win_rate"), "avg R": s.get("avg_r"),
                     "net R": s.get("total_r"), "PF": s.get("profit_factor"), "max DD": s.get("max_dd_r")})
        detail[tag] = bt
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).to_string(index=False))
if only:
    bt = detail[only[0]]
    for by in (["symbol"], ["tf"], ["session"], ["result"]):
        print(); print(breakdown(bt, by).to_string())

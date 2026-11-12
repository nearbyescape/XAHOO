"""The trader's live-stream setup (impulse -> EMA12 pullback -> breakdown close), 5m. Dev 2025, test 2026 once.
usage: python research/trader_setup.py dev | test "<variant>" """
import sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from trend_pullback import daily_context
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import breakdown, generate, run_backtest, stats
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
WIN = {"dev": (date(2025, 2, 10), date(2025, 12, 31)), "test": (date(2026, 2, 10), date(2026, 11, 11)),
       "y2024": (date(2024, 2, 10), date(2024, 12, 31))}
MGMT = {
    "liq 3-10R, BE@1R": dict(partials=(1, 0, 0), move_sl_to_be_at_tp1=False, be_at_r=1.0, target_mode="liquidity", min_rr=3.0),
    "fixed 2R, BE@1R": dict(partials=(1, 0, 0), move_sl_to_be_at_tp1=False, be_at_r=1.0, tp_r=(2.0, 2.0, 2.0)),
    "fixed 3R, BE@1R": dict(partials=(1, 0, 0), move_sl_to_be_at_tp1=False, be_at_r=1.0, tp_r=(3.0, 3.0, 3.0)),
    "partials .75/1.5/2.5R": dict(),
}
mode = sys.argv[1]; only = sys.argv[2] if len(sys.argv) > 2 else None
a, b = WIN[mode]
data = {s: dukascopy.load(s, CACHE, a - timedelta(days=40), b) for s in ("XAUUSD", "XAGUSD")}
dtrend = {s: daily_context(m)["trend"] for s, m in data.items()}
rows, keep = [], {}
for k_imp in (3.0, 4.0, 5.0):
    for mname, mk in MGMT.items():
        p = StrategyParams()
        p.enabled_setups, p.exec_tfs, p.trade_asia, p.ip_impulse_atr = ("impulse_pullback",), ("5m",), True, k_imp
        for k, v in mk.items():
            setattr(p, k, v)
        c = generate(data, p, p.exec_tfs)
        c = c[c["close_time"] >= pd.Timestamp(a, tz="UTC")].reset_index(drop=True) if len(c) else c
        for dfilter in (False, True):
            name = f"impulse {k_imp:.0f}ATR | {mname} | daily-trend {'on' if dfilter else 'off'}"
            if only and name != only:
                continue
            cc = c
            if dfilter and len(c):
                tr = [dtrend[s].reindex([t.normalize()]).iloc[0] for s, t in zip(c["symbol"], c["close_time"])]
                cc = c[np.array(tr) == c["dir"].to_numpy()].reset_index(drop=True)
            bt = run_backtest(data, p, p.exec_tfs, cand=cc)
            s = stats(bt)
            rows.append({"variant": name, "trades": s["signals"], "per_day": s.get("per_day"), "green%": s.get("green_rate"),
                         "win%": s.get("win_rate"), "avg R": s.get("avg_r"), "net R": s.get("total_r"),
                         "PF": s.get("profit_factor"), "maxDD": s.get("max_dd_r")})
            keep[name] = bt
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))
if only and keep.get(only) is not None and len(keep[only]):
    for by in (["symbol"], ["session"], ["result"]):
        print(); print(breakdown(keep[only], by).to_string())

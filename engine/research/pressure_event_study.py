"""Does volume-based buyer/seller pressure predict the next move? Event study on 5m bars (dev data only)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo import features
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
p = StrategyParams()
win = {"XAUUSD": (date(2025, 2, 10), date(2025, 12, 31)), "XAGUSD": (date(2025, 2, 10), date(2025, 9, 30))}
frames = []
for sym, (a, b) in win.items():
    m1 = dukascopy.load(sym, CACHE, a - timedelta(days=40), b)
    f = features.build(m1, "5m", p)
    f = f[f.index >= pd.Timestamp(a, tz="UTC")].copy()
    for h in (6, 12):   # 30 and 60 minutes ahead, in ATR units
        f[f"fwd{h}"] = (f["close"].shift(-h) - f["close"]) / f["atr"]
    n = p.lp_sweep_bars
    hi_n, lo_n = f["high"].rolling(n).max(), f["low"].rolling(n).min()
    sw_hi = pd.Series(False, index=f.index); sw_lo = pd.Series(False, index=f.index)
    for lvl in ("eq_high", "pdh", "asia_h", "last_sh"):
        ref = f[lvl].shift(n); sw_hi |= ((hi_n > ref) & (f["close"] < ref)).fillna(False)
    for lvl in ("eq_low", "pdl", "asia_l", "last_sl"):
        ref = f[lvl].shift(n); sw_lo |= ((lo_n < ref) & (f["close"] > ref)).fillna(False)
    f["sweep"] = np.where(sw_hi & ~sw_lo, "swept high", np.where(sw_lo & ~sw_hi, "swept low", "none"))
    f["symbol"] = sym
    frames.append(f)
f = pd.concat(frames).dropna(subset=["press3", "fwd12"])
f["pressure"] = pd.cut(f["press3"], [-1.01, -0.5, -0.15, 0.15, 0.5, 1.01],
                       labels=["strong sell", "sell", "neutral", "buy", "strong buy"])
pd.set_option("display.width", 200)
g = lambda df: df.groupby("pressure", observed=True).agg(n=("fwd12", "size"), fwd30m_atr=("fwd6", "mean"),
        fwd60m_atr=("fwd12", "mean"), up_60m_pct=("fwd12", lambda x: round((x > 0).mean() * 100, 1))).round(3)
print("ALL 5m BARS — next move by pressure of the last 3 bars"); print(g(f).to_string())
for sw in ("swept high", "swept low"):
    print(f"\nAFTER '{sw}' of a liquidity pool"); print(g(f[f["sweep"] == sw]).to_string())

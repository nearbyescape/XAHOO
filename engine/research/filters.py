"""Volatility-regime and news-impulse filters on the live strategy (docs/BACKTEST.md run 17).
Variants fixed in advance; dev 2025, check 2024 and 2026. Filters are applied to the backtest's trade list
(removing trades doesn't re-open the one-trade-at-a-time slot; small approximation)."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo import features
from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import generate, run_backtest

CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
PERIODS = {"2024": (date(2024, 2, 10), date(2024, 12, 31)), "2025 (dev)": (date(2025, 2, 10), date(2025, 12, 31)),
           "2026": (date(2026, 2, 10), date(2026, 11, 11))}
WIN5 = 20 * 288          # 20 days of 5m bars
WIN1 = 20 * 1440         # 20 days of 1m bars


def vol_context(m1, p):
    f = features.tf_frame(m1, "5m", p)
    atr = f.set_index("close_time")["atr"]
    prev = atr.shift(1)                                      # compare with the PREVIOUS 20 days only
    return pd.DataFrame({"atr": atr, "q50": prev.rolling(WIN5, min_periods=WIN5 // 2).quantile(0.5),
                         "q70": prev.rolling(WIN5, min_periods=WIN5 // 2).quantile(0.7),
                         "q95": prev.rolling(WIN5, min_periods=WIN5 // 2).quantile(0.95)})


def news_events(m1):
    rng = m1["high"] - m1["low"]
    med = rng.shift(1).rolling(WIN1, min_periods=WIN1 // 2).median()
    t = m1.index
    window = ((t.minute == 0) | (t.minute == 30)) & (t.hour >= 12) & ((t.hour < 19) | ((t.hour == 19) & (t.minute <= 30)))
    spike = (rng >= 5 * med) & window
    return pd.DatetimeIndex(t[spike.to_numpy()]) + pd.Timedelta(minutes=1)    # known when the spike bar closes


def main():
    p = StrategyParams.trader()
    rows = []
    for label, (a, b) in PERIODS.items():
        data = {s: dukascopy.load(s, CACHE, a - timedelta(days=60), b) for s in ("XAUUSD", "XAGUSD")}
        c = generate(data, p, p.exec_tfs)
        c = c[c["close_time"] >= pd.Timestamp(a, tz="UTC")].reset_index(drop=True)
        bt = run_backtest(data, p, p.exec_tfs, cand=c)
        parts = []
        for sym, m1 in data.items():
            t = bt[bt.symbol == sym].copy()
            v = vol_context(m1, p).reindex(t["close_time"])
            t[["atr5", "q50", "q70", "q95"]] = v[["atr", "q50", "q70", "q95"]].to_numpy()
            ev = news_events(m1)
            ct = pd.DatetimeIndex(t["close_time"])
            pos = ev.searchsorted(ct, side="right") - 1
            if len(ev):
                last = ev[np.clip(pos, 0, None)]
                mins = (ct - last).total_seconds() / 60
                t["post_news"] = (pos >= 0) & (np.asarray(mins) <= 90)
            else:
                t["post_news"] = False
            print(sym, label, "news spikes:", len(ev), "trades after news:", int(t["post_news"].sum()), "/", len(t))
            parts.append(t)
        t = pd.concat(parts)
        variants = {
            "none": np.ones(len(t), bool),
            "V1 ATR >= median": t.atr5 >= t.q50,
            "V2 ATR >= 70th pct": t.atr5 >= t.q70,
            "V3 skip ATR > 95th pct": t.atr5 <= t.q95,
            "V4 median..95th": (t.atr5 >= t.q50) & (t.atr5 <= t.q95),
            "N1 only <=90 min after news spike": t.post_news,
            "N2 never <=90 min after news spike": ~t.post_news,
        }
        for name, mask in variants.items():
            r = t.loc[np.asarray(mask, bool)].sort_values("close_time")["r"]
            rows.append({"variant": name, "period": label, "trades": len(r),
                         "win%": round((r > 0.05).mean() * 100, 1) if len(r) else None,
                         "avg R": round(r.mean(), 3) if len(r) else None, "net R": round(r.sum(), 1),
                         "max DD": round((r.cumsum() - r.cumsum().cummax()).min(), 1) if len(r) else None})
    df = pd.DataFrame(rows).set_index(["variant", "period"])
    pd.set_option("display.width", 200)
    print(df.to_string())


if __name__ == "__main__":
    main()

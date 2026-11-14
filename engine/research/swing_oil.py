"""Crude oil in the v3 swing plan (docs/BACKTEST.md run 22): S1 (daily) and S2 (4h, daily-filtered), unchanged rules,
on WTI and Brent, with a financing-cost sensitivity; then the gold + silver + WTI portfolio."""
import sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import swing
from swing_data import build
from swing import load, s_ma_trend, simulate, summarize

swing.SPREAD.update({"WTIUSD": 0.04, "BCOUSD": 0.04})
PER = {"2010-2014": ("2010", "2014"), "2015-2019": ("2015", "2019"), "2020-2026": ("2020", "2026")}


def run(sym):
    dd = load(sym, "1d")
    ent, ex, kw = s_ma_trend(dd, 20, 3.0)
    s1 = simulate(dd, sym, ent, ex, **kw); s1["sys"] = "S1 daily"
    d4 = load(sym, "4h")
    ent, ex, kw = s_ma_trend(d4, 55, 3.0)
    st = pd.Series(np.where((dd.close > dd.sma200) & (dd.sma50 > dd.sma200), 1,
                            np.where((dd.close < dd.sma200) & (dd.sma50 < dd.sma200), -1, 0)), index=dd.index)
    st.index = st.index + pd.Timedelta(hours=22)
    ent = ent.where(ent == st.reindex(d4.index, method="ffill"), 0)
    s2 = simulate(d4, sym, ent, ex, **kw); s2["sys"] = "S2 4h"
    return s1, s2


def line(label, t):
    sm = summarize(t)
    row = {"": label, **{k: sm.get(k) for k in ("trades", "per yr", "win%", "avg R", "R/yr", "PF", "maxDD R", "avg days")}}
    for pn, (a, b) in PER.items():
        x = t[(t.t >= a) & (t.t <= f"{b}-12-31")]
        row[pn] = round(x.r.mean(), 3) if len(x) else None
    return row


if __name__ == "__main__":
    if not (swing.SW / "BCOUSD_1d.pkl").exists():
        build("BCOUSD")
    d = pd.read_pickle(swing.SW / "WTIUSD_1d.pkl")
    print("WTI data:", d.index[0].date(), "→", d.index[-1].date(), "| min close", round(d.close.min(), 2), "on", d.close.idxmin().date(),
          "| biggest 1-day close-to-close move %:", round(d.close.pct_change().abs().max() * 100, 1))
    rows, keep = [], {}
    for fin_l, fin_s, tag in ((0.05, 0.01, "base financing 5%/1%"), (0.12, 0.06, "harsh financing 12%/6%")):
        swing.FIN_LONG, swing.FIN_SHORT = fin_l, fin_s
        for sym in ("WTIUSD", "BCOUSD"):
            s1, s2 = run(sym)
            rows += [line(f"{sym} S1 daily | {tag}", s1), line(f"{sym} S2 4h | {tag}", s2)]
            if tag.startswith("base"):
                keep[sym] = pd.concat([s1, s2])
    swing.FIN_LONG, swing.FIN_SHORT = 0.05, 0.01
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))
    metals = pd.concat([pd.concat(run(s)) for s in ("XAUUSD", "XAGUSD")])
    for label, t in (("gold + silver", metals), ("gold + silver + WTI", pd.concat([metals, keep["WTIUSD"]]))):
        t = t[t.t >= "2011-06-01"].sort_values("exit")          # common period (oil indicators ready mid-2011)
        r = t.r; yr = t.groupby(t.exit.dt.year).r.sum().round(1)
        streak = max((len(list(g)) for k, g in itertools.groupby(r < 0) if k), default=0)
        print(f"\n{label} (2011-06 → 2026): {summarize(t)}")
        print("  by year:", yr.to_dict(), "| losing years", int((yr < 0).sum()), "of", len(yr), "| worst", yr.min(), "| longest losing streak", streak)
    w = keep["WTIUSD"]
    print("\nWTI long vs short:", w.groupby("dir").r.agg(["count", "mean", "sum"]).round(2).to_dict("index"))
    print("WTI 2020 trades:", w[(w.t >= "2020-01-01") & (w.t <= "2020-12-31")][["t", "exit", "dir", "r", "sys"]].round(2).to_string(index=False))

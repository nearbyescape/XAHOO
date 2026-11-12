"""Signal engine: candles in -> graded, risk-managed signals out.

`generate()` runs the full pipeline for every symbol x execution timeframe.
`run_backtest()` passes the candidates through the stateful gate (one open
signal per symbol/TF, cooldown, daily stop-loss guard) and resolves each
accepted signal on 1m bars with the tracker.

The live service calls the same `generate()` on a rolling window and keeps
the gate state in the database, so live and backtest behave identically.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from . import features
from .config import EXEC_TFS, SYMBOLS, TF_MINUTES, StrategyParams
from .strategy import scoring, setups
from .tracker import simulate


def generate(data: dict[str, pd.DataFrame], p: StrategyParams, tfs=EXEC_TFS) -> pd.DataFrame:
    """All scored candidates (before the gate). `data` maps symbol -> 1m BID candles."""
    ctx = {s: {h: features.tf_frame(m1, h, p) for h in ("1h", "4h")} for s, m1 in data.items()}
    out = []
    for sym, m1 in data.items():
        others = [o for o in data if o != sym]
        for tf in tfs:
            f = features.build(m1, tf, p, ctx[sym])
            other = None
            if others:
                from .data.resample import align_closed
                other = align_closed(ctx[others[0]]["1h"], f["close_time"], ["bias"], "o_")["o_bias"]
            cand = setups.detect(f, p)
            sig = scoring.finalize(cand, f, p, SYMBOLS[sym], other)
            if len(sig):
                sig = sig.assign(symbol=sym, tf=tf)
                out.append(sig)
    if not out:
        return pd.DataFrame()
    res = pd.concat(out).reset_index().rename(columns={"index": "ts"})
    return res.sort_values(["close_time", "symbol", "tf"]).reset_index(drop=True)


class _Row(dict):
    __getattr__ = dict.__getitem__


def run_backtest(data: dict[str, pd.DataFrame], p: StrategyParams, tfs=EXEC_TFS,
                 cand: pd.DataFrame | None = None) -> pd.DataFrame:
    cand = generate(data, p, tfs) if cand is None else cand
    if cand.empty:
        return cand
    arrays = {s: (m1["low"].to_numpy(), m1["high"].to_numpy(), m1["close"].to_numpy(), m1.index)
              for s, m1 in data.items()}
    open_until: dict[tuple, pd.Timestamp] = {}
    last_sig: dict[tuple, pd.Timestamp] = {}
    sl_log: dict[tuple, list] = defaultdict(list)   # (symbol, day) -> exit times of SL trades
    rows = []
    for rec in cand.to_dict("records"):     # dicts, not itertuples: keeps keys like "1h_bias"
        c = _Row(rec)
        t = c.close_time
        key = (c.symbol, c.tf)
        if key in open_until and open_until[key] > t:
            continue
        if key in last_sig and t - last_sig[key] < pd.Timedelta(minutes=p.cooldown_bars * TF_MINUTES[c.tf]):
            continue
        day = t.normalize()
        if sum(1 for x in sl_log[(c.symbol, day)] if x <= t) >= p.max_sl_per_day:
            continue
        lo, hi, cl, idx = arrays[c.symbol]
        start = idx.searchsorted(t)                 # first 1m bar opening at/after signal close
        stop_t = t + pd.Timedelta(minutes=p.max_hold_minutes[c.tf])
        end = idx.searchsorted(stop_t)
        if start >= len(idx):
            continue
        o = simulate(lo, hi, cl, start, end, c.dir, c.entry, c.sl, (c.tp1, c.tp2, c.tp3),
                     p.partials, SYMBOLS[c.symbol].spread, p.move_sl_to_be_at_tp1)
        exit_t = idx[o.exit_idx] + pd.Timedelta(minutes=1)
        open_until[key] = exit_t
        last_sig[key] = t
        if o.result == "SL":
            sl_log[(c.symbol, day)].append(exit_t)
        r = dict(rec)
        r.update(result=o.result, r=o.r, tp_hits=o.tp_hits, exit_time=exit_t, exit_price=o.exit_price,
                 mfe_r=o.mfe_r, mae_r=o.mae_r, minutes=int((exit_t - t).total_seconds() // 60))
        rows.append(r)
    return pd.DataFrame(rows)


def stats(bt: pd.DataFrame) -> dict:
    if bt.empty:
        return {"signals": 0}
    r = bt["r"]
    wins, losses = r[r > 0.05], r[r < -0.05]
    eq = r.cumsum()
    dd = (eq - eq.cummax()).min()
    days = bt["close_time"].dt.normalize().nunique()
    return {
        "signals": int(len(bt)),
        "per_day": round(len(bt) / max(days, 1), 2),
        "tp1_hit_rate": round(float((bt["tp_hits"] >= 1).mean()) * 100, 1),
        "win_rate": round(len(wins) / len(bt) * 100, 1),
        "loss_rate": round(len(losses) / len(bt) * 100, 1),
        "breakeven_rate": round((len(bt) - len(wins) - len(losses)) / len(bt) * 100, 1),
        "avg_r": round(float(r.mean()), 3),
        "total_r": round(float(r.sum()), 1),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) else float("inf"),
        "max_dd_r": round(float(dd), 1),
        "avg_minutes": int(bt["minutes"].mean()),
    }


def breakdown(bt: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    if bt.empty:
        return pd.DataFrame()
    g = bt.groupby(by)
    return pd.DataFrame({
        "n": g.size(),
        "tp1_hit%": g["tp_hits"].apply(lambda s: round((s >= 1).mean() * 100, 1)),
        "win%": g["r"].apply(lambda s: round((s > 0.05).mean() * 100, 1)),
        "avg_r": g["r"].mean().round(3),
        "total_r": g["r"].sum().round(1),
    })

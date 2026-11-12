"""Feature pipeline: one row per bar of an execution timeframe, holding every
value the strategy needs, with higher timeframes aligned look-ahead free."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from .config import StrategyParams
from .data.resample import align_closed, resample


def bias(df: pd.DataFrame, p: StrategyParams) -> pd.Series:
    """+1 bull / -1 bear / 0 neutral, from price vs EMA200, EMA200 slope and EMA12 vs EMA200 (PLAN §2.1)."""
    e12, e200 = ind.ema(df["close"], p.ema_fast), ind.ema(df["close"], p.ema_slow)
    slope = e200 - e200.shift(p.slope_lookback)
    c = df["close"]
    bull = (c > e200) & (slope > 0) & (e12 > e200)
    bear = (c < e200) & (slope < 0) & (e12 < e200)
    out = pd.Series(np.where(bull, 1, np.where(bear, -1, 0)), index=df.index)
    out[e200.isna() | slope.isna()] = 0
    return out


def tf_frame(m1: pd.DataFrame, tf: str, p: StrategyParams) -> pd.DataFrame:
    df = resample(m1, tf)
    df["ema_fast"] = ind.ema(df["close"], p.ema_fast)
    df["ema_slow"] = ind.ema(df["close"], p.ema_slow)
    df["atr"] = ind.atr(df, p.atr_len)
    df["adx"] = ind.adx(df, p.adx_len)
    df["bias"] = bias(df, p)
    return df


def daily_levels(m1: pd.DataFrame) -> pd.DataFrame:
    """Previous UTC day's high/low and today's Asian range (00:00-06:00 UTC), per 1m bar.
    Asian levels only become available once the Asian window has closed."""
    day = m1.index.normalize()
    d = m1.groupby(day).agg(dh=("high", "max"), dl=("low", "min"))
    prev = d.shift(1)
    asia = m1[m1.index.hour < 6].groupby(m1[m1.index.hour < 6].index.normalize()).agg(ah=("high", "max"), al=("low", "min"))
    out = pd.DataFrame(index=m1.index)
    out["pdh"] = prev["dh"].reindex(day).values
    out["pdl"] = prev["dl"].reindex(day).values
    a = asia.reindex(day)
    after = m1.index.hour >= 6
    out["asia_h"] = np.where(after, a["ah"].values, np.nan)
    out["asia_l"] = np.where(after, a["al"].values, np.nan)
    return out


def session_label(ts: pd.DatetimeIndex, p: StrategyParams) -> tuple[np.ndarray, np.ndarray]:
    mins = ts.hour * 60 + ts.minute
    label = np.full(len(ts), "off", dtype=object)
    for a, b, name in p.sessions.windows:
        label[(mins >= a) & (mins < b)] = name
    o0, o1 = p.sessions.overlap
    overlap = (mins >= o0) & (mins < o1)
    return label, overlap


def build(m1: pd.DataFrame, tf: str, p: StrategyParams, ctx: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Return the feature frame for execution timeframe `tf`.

    `ctx` may hold pre-built 1h/4h frames (to share across exec TFs)."""
    ctx = ctx or {}
    f = tf_frame(m1, tf, p)
    f = f.join(ind.structure(f, k=2))
    f = f.join(ind.fvg(f))
    f = f.join(ind.candle_shape(f, p.pin_wick_body))
    f["e12_slope"] = f["ema_fast"] - f["ema_fast"].shift(3)
    f["e200_slope_atr"] = (f["ema_slow"] - f["ema_slow"].shift(p.slope_lookback)) / f["atr"]

    for htf in ("15m", "1h", "4h"):
        if htf == tf:
            continue
        h = ctx.get(htf)
        if h is None:
            h = tf_frame(m1, htf, p)
        a = align_closed(h, f["close_time"], ["bias", "ema_slow", "close"], f"{htf}_")
        f = f.join(a)

    # Daily / Asian liquidity levels, sampled at the last 1m bar inside each exec bar.
    lv = daily_levels(m1)
    last_min = f["close_time"] - pd.Timedelta(minutes=1)
    f = f.join(lv.reindex(pd.DatetimeIndex(last_min)).set_axis(f.index))

    label, overlap = session_label(pd.DatetimeIndex(f["close_time"]), p)
    f["session"] = label
    f["overlap"] = overlap
    return f

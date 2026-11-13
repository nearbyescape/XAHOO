"""Feature pipeline: one row per bar of an execution timeframe, holding every
value the strategy needs, with higher timeframes aligned look-ahead free."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from .config import TF_MINUTES, StrategyParams
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


def daily_trend(m1: pd.DataFrame) -> pd.Series:
    """Yesterday's daily trend state per calendar day: +1 if the daily close is above its 50-day EMA and the
    20-day return is positive, -1 for the mirror case, else 0. Indexed by day (UTC midnight); known at the open."""
    d = m1["close"].resample("1D").last().dropna()
    d = d[d.index.dayofweek < 5]
    ema50 = d.ewm(span=50, adjust=False).mean()
    mom20 = d / d.shift(20) - 1
    t = np.where((d > ema50) & (mom20 > 0), 1, np.where((d < ema50) & (mom20 < 0), -1, 0))
    t = pd.Series(t, index=d.index).shift(1)
    full = pd.date_range(d.index.min(), d.index.max() + pd.Timedelta(days=3), freq="1D", tz="UTC")
    return t.reindex(full).ffill()   # weekends/holidays carry the last known state


def session_label(ts: pd.DatetimeIndex, p: StrategyParams) -> tuple[np.ndarray, np.ndarray]:
    mins = ts.hour * 60 + ts.minute
    label = np.full(len(ts), "off", dtype=object)
    for a, b, name in p.sessions.windows:
        label[(mins >= a) & (mins < b)] = name
    if p.trade_asia:
        a, b = p.sessions.asia
        label[(mins >= a) & (mins < b)] = "asia"
    o0, o1 = p.sessions.overlap
    overlap = (mins >= o0) & (mins < o1)
    return label, overlap


def pressure(m1: pd.DataFrame, f: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    """Buyer/seller pressure from 1m volume.

    Each 1m bar's volume is split into buying and selling by where it closed in its range
    (close at the high = all buying, at the low = all selling). Summed per exec bar:
      delta     buy minus sell volume
      rvol      volume / average volume of the same time-of-day slot over the previous 20 days
      press3    net pressure of the last 3 bars, -1 (all selling) .. +1 (all buying)
    """
    rng = (m1["high"] - m1["low"]).replace(0, np.nan)
    clv = ((m1["close"] - m1["low"]) / rng).fillna(0.5)
    d1 = m1["volume"] * (2 * clv - 1)
    delta = d1.resample(f"{tf_minutes}min", label="left", closed="left").sum().reindex(f.index).fillna(0)
    vol = f["volume"]
    slot = f.index.hour * 60 + f.index.minute
    base = vol.groupby(slot).transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean())
    out = pd.DataFrame(index=f.index)
    out["delta"] = delta
    out["rvol"] = (vol / base).replace([np.inf, -np.inf], np.nan)
    out["press3"] = (delta.rolling(3).sum() / vol.rolling(3).sum()).clip(-1, 1)
    return out


def build(m1: pd.DataFrame, tf: str, p: StrategyParams, ctx: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Return the feature frame for execution timeframe `tf`.

    `ctx` may hold pre-built 1h/4h frames (to share across exec TFs)."""
    ctx = ctx or {}
    f = tf_frame(m1, tf, p)
    f = f.join(ind.structure(f, k=2))
    f = f.join(ind.fvg(f))
    f = f.join(ind.candle_shape(f, p.pin_wick_body))
    f = f.join(pressure(m1, f, TF_MINUTES[tf]))
    tol = p.lp_eq_tol_atr * f["atr"]
    f["eq_high"] = np.where((f["last_sh"] - f["prev_sh"]).abs() <= tol, np.maximum(f["last_sh"], f["prev_sh"]), np.nan)
    f["eq_low"] = np.where((f["last_sl"] - f["prev_sl"]).abs() <= tol, np.minimum(f["last_sl"], f["prev_sl"]), np.nan)
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

    dt = daily_trend(m1)
    f["d_trend"] = dt.reindex(pd.DatetimeIndex(f["close_time"] - pd.Timedelta(minutes=1)).normalize()).values

    label, overlap = session_label(pd.DatetimeIndex(f["close_time"]), p)
    f["session"] = label
    f["overlap"] = overlap
    return f

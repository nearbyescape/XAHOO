"""Causal technical indicators. Every value at row i uses only rows <= i,
so the same code is valid live (last row) and in backtests (all rows)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    """Standard EMA (alpha = 2/(n+1)), seeded with the first value — matches MT5/TradingView after warm-up."""
    return s.ewm(span=n, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ATR."""
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ADX."""
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def swing_points(df: pd.DataFrame, k: int = 2) -> tuple[pd.Series, pd.Series]:
    """Fractal swing highs/lows with k bars each side.

    A swing at bar j is only *known* at bar j+k. The returned series are
    aligned to the confirmation bar (j+k) and carry the swing price, so they
    contain no look-ahead.
    """
    h, l = df["high"], df["low"]
    win = 2 * k + 1
    is_sh = h.rolling(win, center=True).max() == h
    is_sl = l.rolling(win, center=True).min() == l
    sh = h.where(is_sh).shift(k)
    sl = l.where(is_sl).shift(k)
    return sh, sl


def structure(df: pd.DataFrame, k: int = 2) -> pd.DataFrame:
    """Market structure from confirmed swings.

    Columns:
      last_sh / last_sl  – most recent confirmed swing high / low price
      prev_sh / prev_sl  – the one before it
      trend              – +1 HH&HL, -1 LH&LL, 0 mixed
      bos_up / bos_dn    – close breaks the last swing high / low on this bar
    """
    sh, sl = swing_points(df, k)
    last_sh = sh.ffill()
    last_sl = sl.ffill()
    prev_sh = sh.dropna().shift(1).reindex(df.index).ffill()
    prev_sl = sl.dropna().shift(1).reindex(df.index).ffill()
    hh = last_sh > prev_sh
    hl = last_sl > prev_sl
    trend = np.where(hh & hl, 1, np.where(~hh & ~hl & prev_sh.notna() & prev_sl.notna(), -1, 0))
    c, pc = df["close"], df["close"].shift(1)
    bos_up = (c > last_sh) & (pc <= last_sh)
    bos_dn = (c < last_sl) & (pc >= last_sl)
    return pd.DataFrame({"last_sh": last_sh, "last_sl": last_sl, "prev_sh": prev_sh, "prev_sl": prev_sl,
                         "trend": trend, "bos_up": bos_up, "bos_dn": bos_dn}, index=df.index)


def fvg(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Most recent fair value gap (3-candle imbalance) known at each bar.

    Bullish FVG at bar i: low[i] > high[i-2]; zone = (high[i-2], low[i]).
    Bearish FVG at bar i: high[i] < low[i-2]; zone = (high[i], low[i-2]).
    Zones are forward-filled for `lookback` bars.
    """
    h2, l2 = df["high"].shift(2), df["low"].shift(2)
    bull = df["low"] > h2
    bear = df["high"] < l2
    out = pd.DataFrame(index=df.index)
    out["bull_lo"] = h2.where(bull).ffill(limit=lookback)
    out["bull_hi"] = df["low"].where(bull).ffill(limit=lookback)
    out["bear_lo"] = df["high"].where(bear).ffill(limit=lookback)
    out["bear_hi"] = l2.where(bear).ffill(limit=lookback)
    return out


def candle_shape(df: pd.DataFrame, wick_body: float = 2.0) -> pd.DataFrame:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    po, pc = o.shift(1), c.shift(1)
    return pd.DataFrame({
        "bull": c > o,
        "bear": c < o,
        "bull_pin": (lower >= wick_body * body) & (lower >= 0.5 * rng),
        "bear_pin": (upper >= wick_body * body) & (upper >= 0.5 * rng),
        "bull_engulf": (c > o) & (pc < po) & (c >= po) & (o <= pc),
        "bear_engulf": (c < o) & (pc > po) & (c <= po) & (o >= pc),
        "body_frac": body / rng,
    }, index=df.index)

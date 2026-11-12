"""Setup detection (PLAN §2.2-2.3). Vectorised over a feature frame; every
condition at row i uses only data available at that bar's close.

Each detector returns a frame of candidate rows with:
  dir (+1/-1), setup, entry_ref (bid close), sl, tp (list or None -> R multiples),
  and score components in [0, 1]: setup_quality, confluence, trigger, liquidity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import StrategyParams


def _roll_any(s: pd.Series, n: int) -> pd.Series:
    return s.astype(float).rolling(n, min_periods=1).max().astype(bool)


def _side(f: pd.DataFrame, d: int):
    """Mirror helpers so long/short share one implementation."""
    if d == 1:
        return dict(lo=f["low"], hi=f["high"], ext=lambda a, b: a - b, beyond=lambda a, b: a > b,
                    bull=f["bull"], pin=f["bull_pin"], engulf=f["bull_engulf"], bos=f["bos_up"],
                    fvg_near=f["bull_hi"], fvg_far=f["bull_lo"], pd_level=f["pdl"], asia=f["asia_l"])
    return dict(lo=-f["high"], hi=-f["low"], ext=lambda a, b: b - a, beyond=lambda a, b: a < b,
                bull=f["bear"], pin=f["bear_pin"], engulf=f["bear_engulf"], bos=f["bos_dn"],
                fvg_near=-f["bear_lo"], fvg_far=-f["bear_hi"], pd_level=-f["pdh"], asia=-f["asia_h"])


def trigger(f: pd.DataFrame, d: int) -> tuple[pd.Series, pd.Series]:
    """Rejection candle / micro-break confirming entry. Returns (fires, strength 0-1)."""
    s = _side(f, d)
    c = f["close"] if d == 1 else -f["close"]
    prev_hi = s["hi"].shift(1)
    e12 = f["ema_fast"] if d == 1 else -f["ema_fast"]
    brk = c > prev_hi
    fires = s["bull"] & (c > e12) & (brk | s["pin"] | s["engulf"])
    strength = np.select([s["engulf"], s["pin"], brk], [1.0, 0.8, 0.6], 0.0)
    strength = pd.Series(strength, index=f.index) + 0.2 * _roll_any(s["bos"], 3)
    return fires, strength.clip(0, 1)


def _liquidity(f: pd.DataFrame, d: int, n: int = 10) -> pd.Series:
    """Was the previous-day or Asian extreme swept in the last n bars (and price back inside)?"""
    s = _side(f, d)
    lo_n = s["lo"].rolling(n, min_periods=1).min()
    c = f["close"] if d == 1 else -f["close"]
    hit = pd.Series(False, index=f.index)
    for lvl in (s["pd_level"], s["asia"]):
        hit |= (lo_n < lvl) & (c > lvl)
    return hit


def _fib_or_fvg(f: pd.DataFrame, d: int, pull_lo: pd.Series, tol: pd.Series) -> pd.Series:
    """Confluence: pullback extreme inside a 0.5-0.618 retracement of the last swing leg and/or an FVG."""
    if d == 1:
        a, b = f["last_sl"], f["last_sh"]
        leg = b - a
        z_hi, z_lo = b - 0.5 * leg, b - 0.618 * leg
        fib = (leg > 0) & (pull_lo <= z_hi + tol) & (pull_lo >= z_lo - tol)
    else:
        a, b = -f["last_sh"], -f["last_sl"]
        leg = b - a
        z_hi, z_lo = b - 0.5 * leg, b - 0.618 * leg
        fib = (leg > 0) & (pull_lo <= z_hi + tol) & (pull_lo >= z_lo - tol)
    s = _side(f, d)
    in_fvg = (pull_lo <= s["fvg_near"] + tol) & (pull_lo >= s["fvg_far"] - tol)
    return 0.6 * fib.astype(float) + 0.6 * in_fvg.fillna(False).astype(float)


def _pack(f, mask, d, setup, sl, quality, confl, trig_strength, liq, tps=None):
    idx = f.index[mask.fillna(False).values]
    if len(idx) == 0:
        return pd.DataFrame()
    out = pd.DataFrame(index=idx)
    out["dir"] = d
    out["setup"] = setup
    out["entry_ref"] = f.loc[idx, "close"]
    out["sl"] = (sl if d == 1 else -sl).loc[idx]
    out["setup_quality"] = quality.loc[idx].clip(0, 1)
    out["confluence"] = confl.loc[idx].clip(0, 1)
    out["trigger"] = trig_strength.loc[idx]
    out["liquidity"] = liq.loc[idx].astype(float)
    if tps is not None:
        for i, t in enumerate(tps):
            out[f"tp{i + 1}_fixed"] = (t if d == 1 else -t).loc[idx]
    return out


def ema12_pullback(f: pd.DataFrame, p: StrategyParams, d: int) -> pd.DataFrame:
    s = _side(f, d)
    sg = 1 if d == 1 else -1
    c, e12, e200 = sg * f["close"], sg * f["ema_fast"], sg * f["ema_slow"]
    atr = f["atr"]
    n = p.pullback_lookback
    trend = (c > e200) & (e12 > e200) & (sg * f["e12_slope"] > 0)
    touched = _roll_any(s["lo"] - e12 <= p.pullback_tol_atr * atr, n)
    pull_lo = s["lo"].rolling(n, min_periods=1).min()
    held = pull_lo > e200
    not_ext = (c - e12) <= p.max_extension_atr * atr
    fires, strength = trigger(f, d)
    mask = trend & touched & held & not_ext & fires
    sl = pull_lo - p.sl_buffer_atr * atr
    slope = (sg * f["e200_slope_atr"]).clip(lower=0)
    quality = 0.4 + 0.3 * (f["trend"] == sg) + 0.3 * (slope / 0.5).clip(0, 1)
    confl = _fib_or_fvg(f, d, pull_lo, 0.1 * atr)
    return _pack(f, mask, d, "ema12_pullback", sl, quality, confl, strength, _liquidity(f, d))


def ema200_retest(f: pd.DataFrame, p: StrategyParams, d: int) -> pd.DataFrame:
    s = _side(f, d)
    sg = 1 if d == 1 else -1
    c, e12, e200 = sg * f["close"], sg * f["ema_fast"], sg * f["ema_slow"]
    atr = f["atr"]
    n = p.pullback_lookback
    spread = e12 - e200
    crossed = (spread > 0) & (spread.rolling(p.retest_cross_lookback, min_periods=1).min() < 0)
    pull_lo = s["lo"].rolling(n, min_periods=1).min()
    touched = (pull_lo - e200 <= p.retest_tol_atr * atr) & (c > e200)
    fires, strength = trigger(f, d)
    mask = crossed & touched & fires
    sl = np.minimum(pull_lo, e200) - p.sl_buffer_atr * atr
    quality = 0.5 + 0.5 * (f["trend"] == sg)
    confl = _fib_or_fvg(f, d, pull_lo, 0.1 * atr)
    return _pack(f, mask, d, "ema200_retest", sl, quality, confl, strength, _liquidity(f, d))


def range_fade(f: pd.DataFrame, p: StrategyParams, d: int) -> pd.DataFrame:
    sg = 1 if d == 1 else -1
    atr = f["atr"]
    rh = f["high"].rolling(p.range_len).max().shift(1)
    rl = f["low"].rolling(p.range_len).min().shift(1)
    width = rh - rl
    w_atr = width / atr
    is_range = (f["adx"] < p.range_adx_max) & (w_atr >= p.range_min_width_atr) & \
               (w_atr <= p.range_max_width_atr) & (f["e200_slope_atr"].abs() < 0.3)
    s = _side(f, d)
    c = sg * f["close"]
    edge = sg * (rl if d == 1 else rh)          # the edge we fade from, in mirrored space
    far = sg * (rh if d == 1 else rl)
    zone = s["lo"] <= edge + p.range_edge_frac * width
    back_inside = c > edge
    fires = s["bull"] & (s["pin"] | s["engulf"] | (c > s["hi"].shift(1)))
    strength = pd.Series(np.select([s["engulf"], s["pin"]], [1.0, 0.8], 0.6), index=f.index)
    mask = is_range & zone & back_inside & fires
    sl = np.minimum(s["lo"].rolling(3, min_periods=1).min(), edge) - p.sl_buffer_atr * atr
    mid = (edge + far) / 2
    tp2 = far - 0.5 * p.range_edge_frac * width
    quality = 0.5 + 0.5 * (1 - (f["adx"] / p.range_adx_max)).clip(0, 1)
    confl = pd.Series(0.5, index=f.index)  # tested range edge is itself a level
    return _pack(f, mask, d, "range", sl, quality, confl, strength, _liquidity(f, d), tps=[mid, tp2, tp2])


def liquidity_sweep(f: pd.DataFrame, p: StrategyParams, d: int) -> pd.DataFrame:
    s = _side(f, d)
    sg = 1 if d == 1 else -1
    c = sg * f["close"]
    atr = f["atr"]
    n = p.sweep_lookback
    lo_n = s["lo"].rolling(n, min_periods=1).min()
    swept = pd.Series(False, index=f.index)
    for lvl in (s["pd_level"], s["asia"]):
        swept |= (lo_n < lvl) & (c > lvl)
    choch = _roll_any(s["bos"], n + 1)
    fires, strength = trigger(f, d)
    mask = swept & choch & fires
    sl = lo_n - p.sl_buffer_atr * atr
    quality = pd.Series(0.7, index=f.index) + 0.3 * (f["trend"] == sg)
    confl = _fib_or_fvg(f, d, lo_n, 0.1 * atr)
    return _pack(f, mask, d, "sweep", sl, quality, confl, strength, pd.Series(1.0, index=f.index))


DETECTORS = {
    "ema12_pullback": ema12_pullback,
    "ema200_retest": ema200_retest,
    "range": range_fade,
    "sweep": liquidity_sweep,
}


def detect(f: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    parts = []
    for name in p.enabled_setups:
        for d in (1, -1):
            r = DETECTORS[name](f, p, d)
            if len(r):
                parts.append(r)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    # one candidate per bar: keep the highest-priority setup (order of enabled_setups)
    prio = {n: i for i, n in enumerate(p.enabled_setups)}
    out["_prio"] = out["setup"].map(prio)
    out = out.reset_index().sort_values(["ts", "_prio"]).drop_duplicates("ts").set_index("ts")
    return out.drop(columns="_prio")

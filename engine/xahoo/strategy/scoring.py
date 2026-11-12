"""Bias/session filters, risk levels (SL/TP) and confidence score (PLAN §2.4-2.6)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import StrategyParams, SymbolSpec, grade


def _agree(b: pd.Series, d: pd.Series) -> pd.Series:
    """1 if bias agrees with direction, 0.5 neutral, 0 against."""
    return np.where(b == d, 1.0, np.where(b == 0, 0.5, 0.0))


def finalize(cand: pd.DataFrame, f: pd.DataFrame, p: StrategyParams, spec: SymbolSpec,
             other_bias_1h: pd.Series | None = None) -> pd.DataFrame:
    """Attach filters, entry/SL/TP and score to raw setup candidates. Drops rejected rows."""
    if cand.empty:
        return cand
    cols = ["close_time", "atr", "close", "1h_bias", "4h_bias", "session", "overlap"] + (["15m_bias"] if "15m_bias" in f else [])
    c = cand.join(f[cols], how="left")
    d = c["dir"]

    # --- filters ---
    keep = pd.Series(True, index=c.index)
    if p.require_1h_bias:
        trend_setup = c["setup"] != "range"
        keep &= np.where(trend_setup, c["1h_bias"] == d, c["1h_bias"] != -d)
    if p.require_15m_bias and "15m_bias" in c:
        trend_setup = c["setup"] != "range"
        keep &= np.where(trend_setup, c["15m_bias"] == d, True)
    if p.use_sessions:
        keep &= c["session"] != "off"
    keep &= c["atr"] >= p.min_atr_frac * c["close"]
    c = c[keep].copy()
    if c.empty:
        return c
    d = c["dir"]

    # --- entry & risk (long fills at ask = bid + spread; short at bid) ---
    c["entry"] = c["entry_ref"] + np.where(d == 1, spec.spread, 0.0)
    risk = (c["entry"] - c["sl"]) * d
    min_risk = np.maximum(p.sl_min_atr * c["atr"], p.min_sl_spreads * spec.spread)
    c["sl"] = np.where(risk < min_risk, c["entry"] - d * min_risk, c["sl"])
    c["risk"] = (c["entry"] - c["sl"]) * d
    c = c[c["risk"] <= np.maximum(p.sl_max_atr * c["atr"], p.min_sl_spreads * spec.spread * 1.5)].copy()
    if c.empty:
        return c
    d = c["dir"]
    has_fixed = c["tp1_fixed"].notna() if "tp1_fixed" in c else pd.Series(False, index=c.index)
    for i, r in enumerate(p.tp_r):
        col = f"tp{i + 1}"
        c[col] = c["entry"] + d * r * c["risk"]
        fixed = f"{col}_fixed"
        if fixed in c:
            c[col] = np.where(has_fixed, c[fixed], c[col])
    # structural targets (range) must still pay at least 0.8R at TP1
    tp1_r = (c["tp1"] - c["entry"]) * d / c["risk"]
    c = c[~has_fixed | (tp1_r >= 0.8)].copy()
    if c.empty:
        return c
    c = c.drop(columns=[x for x in c.columns if x.endswith("_fixed")])
    d = c["dir"]

    # --- score ---
    comp = pd.DataFrame(index=c.index)
    comp["bias_1h"] = _agree(c["1h_bias"], d)
    comp["bias_4h"] = _agree(c["4h_bias"], d)
    comp["setup_quality"] = c["setup_quality"]
    comp["confluence"] = c["confluence"]
    comp["trigger"] = c["trigger"]
    comp["session"] = np.where(c["overlap"], 1.0, np.where(c["session"] != "off", 0.7, 0.2))
    comp["liquidity"] = c["liquidity"]
    if other_bias_1h is not None:
        ob = other_bias_1h.reindex(c.index)
        comp["metals_agree"] = _agree(ob.fillna(0), d)
    w = {k: v for k, v in p.weights.items() if k in comp.columns}   # unavailable inputs (e.g. DXY) are excluded
    total = sum(w.values())
    c["score"] = (sum(comp[k] * v for k, v in w.items()) / total * 100).round(1)
    c["components"] = comp.round(2).to_dict("records")
    c["grade"] = c["score"].map(grade)
    return c[c["score"] >= p.min_score_dashboard]

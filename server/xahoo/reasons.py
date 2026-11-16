"""Plain-language reasons behind a forecast.

The model reports how much each input pushed the probability up or down (LightGBM contributions, in log-odds).
The inputs with the largest pushes are turned into short sentences from the input's current value, e.g.
"Sellers aggressive, last 15 min" or "Open interest rising while price falls". A reason's `push` says which way
it moved the forecast; `w` is its size (log-odds), so 0.05 is a small nudge and 0.2 a large one.
"""
from __future__ import annotations

import math

SPAN = {"1": "1 min", "5": "5 min", "15": "15 min", "60": "1h", "240": "4h", "1440": "1 day", "4320": "3 days",
        "10080": "7 days", "5m": "5 min", "1h": "1h", "4h": "4h", "1d": "1 day"}
LAYER = {"a": "trend", "b": "flow", "c": "positioning", "d": "leader"}


def _q(z: float, lo: float = 0.5, hi: float = 1.5) -> str:
    a = abs(z)
    return "sharply " if a >= hi else "" if a >= lo else "slightly "


def describe(name: str, v: float, leader: str) -> str | None:
    """One sentence for an input's current value. None for inputs with no useful wording."""
    if v is None or not math.isfinite(v):
        return None
    up = v > 0
    p, _, rest = name.partition("_")
    if name.startswith("a_ret"):
        return f"Price {_q(v)}{'rising' if up else 'falling'}, last {SPAN[name[5:]]}"
    if name.startswith("a_sma"):
        return f"{'Above' if up else 'Below'} its {SPAN[name[5:]]} average"
    if name.startswith("a_pos"):
        where = "top" if v > 0.75 else "bottom" if v < 0.25 else "middle"
        return f"Near the {where} of its {SPAN[name[5:]]} range"
    if name == "a_vol_1h_1d":
        return f"Volatility {'high' if v > 1.15 else 'low' if v < 0.85 else 'normal'} vs the day"
    if name == "a_vol_1d_7d":
        return f"Daily volatility {'above' if v > 1.1 else 'below' if v < 0.9 else 'near'} the weekly norm"
    if name in ("a_tod_sin", "a_tod_cos"):
        return "Typical behaviour at this time of day"
    if name == "a_dow":
        return "Typical behaviour on this weekday"
    if name.startswith("b_imb"):
        side = "Buyers" if up else "Sellers"
        return f"{side} {'dominating' if abs(v) > 0.15 else 'aggressive' if abs(v) > 0.05 else 'slightly ahead'}, last {SPAN[name[5:]]}"
    if name.startswith("b_vol"):
        return f"Volume {'heavy' if v > 1.5 else 'light' if v < 0.7 else 'normal'}, last {SPAN[name[5:]]}"
    if name == "b_cnt5":
        return f"Trading activity {'busy' if v > 1.3 else 'quiet' if v < 0.75 else 'normal'}, last 5 min"
    if name == "b_tsize5":
        return f"{'Large' if v > 1.2 else 'Small' if v < 0.85 else 'Normal'} average trade size, last 5 min"
    if name == "b_ret1":
        return f"Last minute {'up' if up else 'down'}"
    if name in ("b_clv1", "b_clv5"):
        span = "1-min" if name == "b_clv1" else "5-min"
        return f"Closing near the {'high' if v > 0.3 else 'low' if v < -0.3 else 'middle'} of the {span} range"
    if name == "b_range1":
        return f"{'Wide' if v > 1.5 else 'Narrow' if v < 0.7 else 'Normal'} last candle"
    if name in ("b_div15", "b_div60"):
        span = SPAN["15" if name.endswith("15") else "60"]
        return f"{'Buying' if up else 'Selling'} not yet reflected in price, last {span}"
    if name.startswith("c_oi_x_ret"):
        span = "1h" if name.endswith("1h") else "4h"
        return (f"New positions opening with the {span} move" if up else f"Positions closing into the {span} move")
    if name.startswith("c_oi_"):
        return f"Open interest {'rising' if up else 'falling'}, last {SPAN[name[5:]]}"
    if name == "c_ls_acct_z":
        return f"{'More' if up else 'Fewer'} accounts long than usual this week"
    if name == "c_ls_acct_ch1h":
        return f"Accounts turning {'long' if up else 'short'} in the last hour"
    if name in ("c_top_ls_acct_z", "c_top_ls_pos_z"):
        return f"Top traders {'longer' if up else 'shorter'} than usual this week"
    if name in ("c_top_ls_acct_ch1h", "c_top_ls_pos_ch1h"):
        return f"Top traders adding {'longs' if up else 'shorts'} in the last hour"
    if name in ("c_taker", "c_taker_1h"):
        return f"Taker volume favours {'buyers' if up else 'sellers'}{', last hour' if name.endswith('1h') else ''}"
    if name == "c_funding":
        return f"Funding {'positive: longs paying' if up else 'negative: shorts paying'}"
    if name == "c_funding_z":
        return f"Funding {'high' if up else 'low'} vs recent days"
    if name.startswith("d_ret"):
        n = name[5:]
        return f"{leader} {_q(v)}{'rising' if up else 'falling'}, last {SPAN[n]}"
    if name.startswith("d_imb"):
        return f"{'Buyers' if up else 'Sellers'} aggressive in {leader}, last {SPAN[name[5:]]}"
    if name in ("d_lag1", "d_lag5"):
        return f"{leader} moved {'up' if up else 'down'} first; this market lagging"
    if name in ("d_rel60", "d_rel1d"):
        return f"{'Stronger' if up else 'Weaker'} than {leader}, last {'1h' if name == 'd_rel60' else '1 day'}"
    if name == "d_corr1d":
        return f"Moving {'closely' if v > 0.6 else 'loosely'} with {leader}"
    if name.startswith("e_m_"):
        return None                         # market-wide inputs are described by their own wording below
    return None


def market_describe(name: str, v: float) -> str | None:
    """Wording for the optional market-wide layer (e_)."""
    if v is None or not math.isfinite(v):
        return None
    up = v > 0
    if name.startswith("e_m_ret"):
        return f"Whole market {'rising' if up else 'falling'}, last {SPAN[name[7:]]}"
    if name.startswith("e_m_imb"):
        return f"{'Buyers' if up else 'Sellers'} aggressive across the market, last {SPAN[name[7:]]}"
    if name.startswith("e_r_ret"):
        return f"{'Outperforming' if up else 'Underperforming'} the market, last {SPAN[name[7:]]}"
    if name.startswith("e_r_imb"):
        return f"{'More' if up else 'Less'} buying than the rest of the market, last {SPAN[name[7:]]}"
    if name == "e_breadth60":
        return f"{round(v * 8)} of 8 coins up in the last hour"
    if name.startswith("e_m_"):
        base = describe("a_" + name[4:] if not name[4:].startswith(("oi", "taker", "funding", "ls")) else "c_" + name[4:], v, "BTC")
        return f"Market: {base[0].lower() + base[1:]}" if base else None
    return None


def explain(top: list[tuple[str, float]], row, leader: str, n: int = 5) -> list[dict]:
    """top: [(feature, contribution)] sorted by |contribution|. row: mapping feature -> current value."""
    out, seen = [], set()
    for name, w in top:
        v = row.get(name) if hasattr(row, "get") else None
        v = float(v) if v is not None else None
        if name in ("a_tod_sin", "a_tod_cos"):
            text = f"This time of day has tended to {'rise' if w > 0 else 'fall'}"
        elif name == "a_dow":
            text = f"This weekday has tended to {'rise' if w > 0 else 'fall'}"
        else:
            text = market_describe(name, v) if name.startswith("e_") else describe(name, v, leader)
        if not text or text in seen or abs(w) < 0.004:
            continue
        seen.add(text)
        out.append({"t": text, "push": 1 if w > 0 else -1, "w": round(float(w), 3), "layer": LAYER.get(name[0], "market")})
        if len(out) >= n:
            break
    return out

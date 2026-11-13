"""Strategy stop rules ("kill switch") for the live service.

Inputs are CLOSED live trades only (R per trade, in units of the first lot's risk). Levels, from mild to strict:
  DAY_STOP  realised loss today <= -daily_loss_r       -> no new signals until the next UTC day
  HALF      drawdown from equity peak >= half_dd_r     -> signals continue with risk_mult 0.5
  PAUSED    drawdown >= pause_dd_r, or (n >= min_trades and the average R is statistically below the backtest's
            expectation: mean < expect_r - z * sd_r / sqrt(n))  -> no new signals until the owner resumes
Resuming resets the drawdown baseline to the current equity, so an old drawdown doesn't re-trigger at once.
Defaults come from the 2024-2026 backtests (docs/BACKTEST.md runs 12-15): avg ~+0.17R, sd ~1.8R, worst
yearly drawdown ~-15 to -23R.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class GuardConfig:
    daily_loss_r: float = 2.0
    half_dd_r: float = 10.0
    pause_dd_r: float = 20.0
    expect_r: float = 0.15
    sd_r: float = 1.8
    min_trades: int = 30
    z: float = 2.0


def evaluate(closed: list[dict], now: pd.Timestamp, cfg: GuardConfig | None = None,
             baseline_ts: int = 0, manual_pause: str | None = None) -> dict:
    """closed: dicts with 'exit_time' (epoch s) and 'r'. baseline_ts: trades before this don't count toward
    drawdown/edge (set when the owner resumes)."""
    cfg = cfg or GuardConfig()
    tr = sorted((t for t in closed if t.get("r") is not None and t.get("exit_time")), key=lambda t: t["exit_time"])
    rs = [float(t["r"]) for t in tr if t["exit_time"] >= baseline_ts]
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    cur_dd = eq - peak
    day0 = int(now.normalize().timestamp())
    today_r = sum(float(t["r"]) for t in tr if t["exit_time"] >= day0)
    n = len(rs)
    mean = sum(rs) / n if n else 0.0
    edge_floor = cfg.expect_r - cfg.z * cfg.sd_r / math.sqrt(n) if n else None
    reasons, state, mult = [], "ACTIVE", 1.0
    if manual_pause:
        state, mult = "PAUSED", 0.0
        reasons.append(manual_pause)
    else:
        if cur_dd <= -cfg.pause_dd_r:
            state, mult = "PAUSED", 0.0
            reasons.append(f"drawdown {cur_dd:.1f}R reached the pause level (-{cfg.pause_dd_r:.0f}R)")
        elif n >= cfg.min_trades and mean < edge_floor:
            state, mult = "PAUSED", 0.0
            reasons.append(f"average {mean:+.2f}R over {n} trades is below the edge floor {edge_floor:+.2f}R")
        elif today_r <= -cfg.daily_loss_r:
            state, mult = "DAY_STOP", 0.0
            reasons.append(f"today {today_r:+.1f}R reached the daily loss limit (-{cfg.daily_loss_r:.0f}R)")
        elif cur_dd <= -cfg.half_dd_r:
            state, mult = "HALF", 0.5
            reasons.append(f"drawdown {cur_dd:.1f}R: half size until a new equity high")
    return {"state": state, "risk_mult": mult, "reasons": reasons, "equity_r": round(eq, 2),
            "peak_r": round(peak, 2), "drawdown_r": round(cur_dd, 2), "max_drawdown_r": round(dd, 2),
            "today_r": round(today_r, 2), "trades": n, "avg_r": round(mean, 3),
            "edge_floor_r": None if edge_floor is None else round(edge_floor, 3), "config": asdict(cfg)}

"""Strategy parameters and instrument specs.

Every rule in docs/PLAN.md §2 is a parameter here so it can be tuned from the
backtest lab / dashboard without code changes. Each signal stores the params
version that produced it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
EXEC_TFS = ("1m", "5m", "15m")
CONTEXT_TFS = ("1h", "4h")


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    spread: float          # typical spread in price units (cost model / filter)
    max_spread: float      # block signals above this live spread
    digits: int


SYMBOLS = {
    "XAUUSD": SymbolSpec("XAUUSD", spread=0.25, max_spread=0.45, digits=2),
    "XAGUSD": SymbolSpec("XAGUSD", spread=0.025, max_spread=0.045, digits=3),
}


@dataclass
class Sessions:
    """Trading windows in UTC minutes-from-midnight. IST = UTC+5:30.
    London 07:00-11:00 UTC = 12:30-16:30 IST; New York 12:30-17:00 UTC = 18:00-22:30 IST."""
    windows: list[tuple[int, int, str]] = field(default_factory=lambda: [
        (7 * 60, 11 * 60, "london"),
        (12 * 60 + 30, 17 * 60, "newyork"),
    ])
    asia: tuple[int, int] = (1 * 60, 4 * 60)   # 06:30-09:30 IST; enable with StrategyParams.trade_asia
    overlap: tuple[int, int] = (12 * 60 + 30, 16 * 60)  # London/NY overlap gets best session score


@dataclass
class StrategyParams:
    # --- EMAs (the core of the method) ---
    ema_fast: int = 12
    ema_slow: int = 200
    slope_lookback: int = 20          # bars used to judge EMA200 slope
    atr_len: int = 14
    adx_len: int = 14

    # --- Setup 1: pullback to EMA12 ---
    pullback_lookback: int = 4        # bars back to look for the EMA12 touch
    pullback_tol_atr: float = 0.30    # "touch" = within this many ATR of EMA12
    max_extension_atr: float = 1.20   # don't chase: close must be within K*ATR of EMA12

    # --- Setup 2: EMA200 retest ---
    retest_cross_lookback: int = 40   # EMA12 must have crossed EMA200 within N bars
    retest_tol_atr: float = 0.40

    # --- Setup 3: range ---
    range_len: int = 48
    range_adx_max: float = 20.0
    range_min_width_atr: float = 2.5
    range_max_width_atr: float = 8.0
    range_edge_frac: float = 0.15     # entry zone = outer 15% of the range

    # --- Setup 4: liquidity sweep ---
    sweep_lookback: int = 3

    # --- Trigger candle ---
    pin_wick_body: float = 2.0        # pin bar: rejection wick >= 2x body

    # --- Risk ---
    sl_buffer_atr: float = 0.20
    sl_min_atr: float = 0.60
    sl_max_atr: float = 2.50
    min_sl_spreads: float = 8.0       # stop at least N x spread away, so spread stays a small cost
    tp_r: tuple[float, float, float] = (0.75, 1.5, 2.5)        # backtest: 0.75R TP1 beat 1R (docs/BACKTEST.md)
    partials: tuple[float, float, float] = (0.5, 0.25, 0.25)  # size closed at TP1/TP2/TP3
    move_sl_to_be_at_tp1: bool = True                         # "cost to cost"
    be_at_r: float | None = None      # move SL to entry once +x R in profit (trader-style), None = off
    target_mode: str = "r"            # "r": tp_r multiples · "liquidity": nearest swing/PDH-PDL/Asia level >= min_rr
    min_rr: float = 3.0               # liquidity mode: nearest pool at least this many R away
    max_rr: float = 10.0              # liquidity mode: ignore pools further than this
    max_hold_minutes: dict = field(default_factory=lambda: {"1m": 90, "5m": 300, "15m": 720})

    # --- Filters ---
    use_sessions: bool = True
    trade_asia: bool = False          # the trader also enters around 08:00 IST
    require_1h_bias: bool = True
    require_15m_bias: bool = False    # 1m/5m entries also need the 15m trend to agree (top-down)
    min_atr_frac: float = 0.00015     # ATR must be >= this fraction of price (dead-market filter)
    cooldown_bars: int = 6
    max_sl_per_day: int = 2           # per symbol, then quiet for the day
    news_blackout_min: int = 15

    # --- Scoring / grading ---
    weights: dict = field(default_factory=lambda: {
        "bias_1h": 20, "bias_4h": 10, "setup_quality": 15, "confluence": 15,
        "trigger": 10, "session": 10, "liquidity": 10, "metals_agree": 5, "dxy": 5,
    })
    min_score_dashboard: int = 65
    min_score_telegram: int = 75

    # ema200_retest lost money on both metals in every test window (docs/BACKTEST.md run 4): off by default
    enabled_setups: tuple[str, ...] = ("sweep", "ema12_pullback", "range")
    exec_tfs: tuple[str, ...] = ("5m", "15m")   # 1m entries lost money in every test; available but off
    sessions: Sessions = field(default_factory=Sessions)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)

    @property
    def version(self) -> str:
        return hashlib.sha1(self.to_json().encode()).hexdigest()[:10]


def grade(score: float) -> str:
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    return "C"

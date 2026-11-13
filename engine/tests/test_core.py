import numpy as np
import pandas as pd
import pytest

from xahoo import indicators as ind
from xahoo import features
from xahoo.config import StrategyParams
from xahoo.data.resample import align_closed, resample
from xahoo.tracker import simulate


def synth(n=3000, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 00:00", periods=n, freq="1min", tz="UTC")
    c = 2000 + np.cumsum(rng.normal(drift, 0.4, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(n) * 0.3
    l = np.minimum(o, c) - rng.random(n) * 0.3
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)


def test_ema_matches_recursive_definition():
    s = pd.Series([1.0, 2, 3, 4, 5, 6])
    e = ind.ema(s, 3)
    a = 2 / 4
    exp = [1.0]
    for x in s[1:]:
        exp.append(a * x + (1 - a) * exp[-1])
    assert np.allclose(e, exp)


def test_atr_constant_range():
    df = pd.DataFrame({"high": [11.0] * 50, "low": [10.0] * 50, "close": [10.5] * 50})
    assert ind.atr(df, 14).iloc[-1] == pytest.approx(1.0)


def test_resample_ohlc():
    m1 = synth(60)
    m5 = resample(m1, "5m")
    first = m1.iloc[:5]
    assert m5.iloc[0]["open"] == first["open"].iloc[0]
    assert m5.iloc[0]["high"] == first["high"].max()
    assert m5.iloc[0]["low"] == first["low"].min()
    assert m5.iloc[0]["close"] == first["close"].iloc[-1]
    assert m5.iloc[0]["close_time"] == m1.index[0] + pd.Timedelta(minutes=5)


def test_align_closed_has_no_lookahead():
    m1 = synth(600)
    h1 = resample(m1, "1h")
    m5 = resample(m1, "5m")
    a = align_closed(h1, m5["close_time"], ["close"], "h_")
    # 5m bar closing at 01:30 must see the 1h bar that closed at 01:00 (00:00-01:00), not 01:00-02:00
    t = m5.index[m5["close_time"] == pd.Timestamp("2026-03-02 01:30", tz="UTC")][0]
    assert a.loc[t, "h_close"] == h1.loc[pd.Timestamp("2026-03-02 00:00", tz="UTC"), "close"]
    # 5m bar closing exactly at 02:00 may use the 01:00-02:00 bar (it is final at 02:00)
    t2 = m5.index[m5["close_time"] == pd.Timestamp("2026-03-02 02:00", tz="UTC")][0]
    assert a.loc[t2, "h_close"] == h1.loc[pd.Timestamp("2026-03-02 01:00", tz="UTC"), "close"]


def test_swings_confirmed_only_after_k_bars():
    df = pd.DataFrame({"high": [1, 2, 5, 2, 1, 1, 1.0], "low": [0, 1, 4, 1, 0, 0, 0.0]})
    sh, _ = ind.swing_points(df, k=2)
    assert np.isnan(sh.iloc[2])        # not known on the swing bar itself
    assert sh.iloc[4] == 5             # known 2 bars later


def test_features_are_causal():
    """Features computed on a truncated history must equal those on the full history."""
    p = StrategyParams()
    m1 = synth(4000, drift=0.02)
    full = features.build(m1, "5m", p)
    cut = m1.index[3000]
    part = features.build(m1[m1.index < cut], "5m", p)
    common = part.index[part["close_time"] <= cut][-50:]
    cols = ["ema_fast", "ema_slow", "atr", "1h_bias", "4h_bias", "last_sh", "last_sl", "bull_lo"]
    pd.testing.assert_frame_equal(full.loc[common, cols], part.loc[common, cols])


def _bars(path):
    a = np.array(path, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2]   # low, high, close


def test_tracker_stop_loss():
    lo, hi, cl = _bars([[99, 100.5, 99.5], [97, 99.5, 98]])
    o = simulate(lo, hi, cl, 0, 2, 1, 100.0, 98.0, (102, 104, 106), (0.5, 0.25, 0.25), 0.0)
    assert o.result == "SL" and o.r == -1.0


def test_tracker_tp1_then_breakeven():
    lo, hi, cl = _bars([[100, 102.5, 102], [99.5, 101, 100]])
    o = simulate(lo, hi, cl, 0, 2, 1, 100.0, 98.0, (102, 104, 106), (0.5, 0.25, 0.25), 0.0)
    assert o.result == "BE" and o.r == pytest.approx(0.5)


def test_tracker_all_targets():
    lo, hi, cl = _bars([[100, 102.5, 102], [101, 104.5, 104], [103, 106.5, 106]])
    o = simulate(lo, hi, cl, 0, 3, 1, 100.0, 98.0, (102, 104, 106), (0.5, 0.25, 0.25), 0.0)
    assert o.result == "TP3" and o.r == pytest.approx(0.5 * 1 + 0.25 * 2 + 0.25 * 3)


def test_tracker_short_uses_ask():
    # short at 100, stop 102; bid high 101.8 + spread 0.3 = ask 102.1 -> stopped
    lo, hi, cl = _bars([[99.5, 101.8, 101]])
    o = simulate(lo, hi, cl, 0, 1, -1, 100.0, 102.0, (98, 96, 94), (0.5, 0.25, 0.25), 0.3)
    assert o.result == "SL"


def test_tracker_same_bar_stop_first():
    lo, hi, cl = _bars([[97, 103, 100]])
    o = simulate(lo, hi, cl, 0, 1, 1, 100.0, 98.0, (102, 104, 106), (0.5, 0.25, 0.25), 0.0)
    assert o.result == "SL"


def test_telegram_format():
    from xahoo.telegram import format_signal, format_update
    s = dict(symbol="XAUUSD", dir=1, grade="A+", score=88, tf="5m", entry=2384.5, sl=2380.2,
             risk=4.3, tp1=2388.8, tp2=2393.1, tp3=2397.4, setup="ema12_pullback",
             session="newyork", overlap=True, id="SIG-1", **{"1h_bias": 1, "4h_bias": 1})
    msg = format_signal(s)
    assert "BUY" in msg and "2,384.50" in msg and "1.0R" in msg and "2.0R" in msg
    assert "SL to entry" in format_update("TP1", 0.5)


def test_tracker_breakeven_trigger():
    # short 100, stop 102 (risk 2); price moves to 98 (+1R) then back up to 103 -> exits at entry, not at stop
    lo, hi, cl = _bars([[97.9, 100.2, 98.5], [98.5, 103, 102]])
    o = simulate(lo, hi, cl, 0, 2, -1, 100.0, 102.0, (90, 90, 90), (1, 0, 0), 0.0, False, be_at_r=1.0)
    assert o.result == "BE" and o.r == 0.0


def test_pressure_features_causal_and_bounded():
    p = StrategyParams()
    m1 = synth(4000, drift=0.01)
    full = features.build(m1, "5m", p)
    assert full["press3"].dropna().between(-1, 1).all()
    cut = m1.index[3000]
    part = features.build(m1[m1.index < cut], "5m", p)
    common = part.index[part["close_time"] <= cut][-30:]
    pd.testing.assert_frame_equal(full.loc[common, ["delta", "press3", "eq_high", "eq_low"]],
                                  part.loc[common, ["delta", "press3", "eq_high", "eq_low"]])


def test_delta_sign():
    from xahoo.features import pressure
    idx = pd.date_range("2026-03-02", periods=10, freq="1min", tz="UTC")
    up = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 1.0, "close": 2.0, "volume": 5.0}, index=idx)
    f = resample(up, "5m")
    assert (pressure(up, f, 5)["delta"] > 0).all()


def _pattern(sign):
    """Flat, fast impulse, 3-bar pullback to EMA12, then a breakout close. sign=+1 long pattern, -1 short."""
    closes = [100.0] * 260 + [101, 103, 105.5, 108, 110] + [108.5, 107.0, 105.8, 105.5] + [110.4]
    c = np.array(closes)
    c = 100 + sign * (c - 100)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.2
    l = np.minimum(o, c) - 0.2
    idx = pd.date_range("2026-03-02", periods=len(c), freq="5min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


@pytest.mark.parametrize("sign", [1, -1])
def test_impulse_pullback_fires_on_pattern(sign):
    from xahoo.strategy.setups import impulse_pullback
    df = _pattern(sign)
    df["ema_fast"] = ind.ema(df["close"], 12)
    df["atr"] = 0.6
    df = df.join(ind.structure(df)).join(ind.fvg(df)).join(ind.candle_shape(df))
    for col in ("pdl", "pdh", "asia_l", "asia_h"):
        df[col] = np.nan
    p = StrategyParams()
    p.ip_ema_touch_atr = 1.0
    out = impulse_pullback(df, p, sign)
    assert len(out) >= 1 and out.index[-1] == df.index[-1]
    assert (out["sl"].iloc[-1] < df["close"].iloc[-1]) == (sign == 1)
    assert impulse_pullback(df, p, -sign).empty


def test_ema_closed_on_1m_no_lookahead():
    m1 = synth(600)
    e = ind.ema_closed_on_1m(m1, 5, 12)
    f = resample(m1, "5m")
    full = ind.ema(f["close"], 12)
    # at the 1m bar opening 00:10 only the 5m bars 00:00 and 00:05 are closed -> value of the 00:05 bar
    k = m1.index.get_loc(pd.Timestamp("2026-03-02 00:10", tz="UTC"))
    assert e[k] == pytest.approx(full.loc[pd.Timestamp("2026-03-02 00:05", tz="UTC")])
    assert np.isnan(e[m1.index.get_loc(pd.Timestamp("2026-03-02 00:03", tz="UTC"))])


def test_scalein_trailing_stop_locks_profit():
    from xahoo.tracker import simulate_scalein
    lo = np.array([99.9, 101.9, 103.5, 102.4])
    hi = np.array([100.5, 102.5, 104.6, 103.0])
    cl = np.array([100.2, 102.3, 104.4, 102.5])
    trail = np.array([np.nan, 100.5, 102.8, 103.0])     # EMA rising behind price
    o = simulate_scalein(lo, hi, cl, 0, 4, 1, 100.0, 98.0, 110.0, None, 0.0, 1.0, trail, 0.0)
    assert o.result == "TRAIL" and o.r == pytest.approx((102.8 - 100.0) / 2)   # stopped at the trailed EMA level


@pytest.mark.parametrize("sign", [1, -1])
def test_forming_fires_before_trigger_only(sign):
    from xahoo.strategy.setups import impulse_forming
    df = _pattern(sign)
    df["ema_fast"] = ind.ema(df["close"], 12)
    df["atr"] = 0.6
    df["close_time"] = df.index + pd.Timedelta(minutes=5)
    df["session"], df["1h_bias"], df["d_trend"] = "london", sign, sign
    p = StrategyParams.trader()
    p.ip_ema_touch_atr = 1.0
    out = impulse_forming(df, p, sign)
    last = df.index[-1]
    assert len(out) >= 1 and last not in out.index          # forming during the pullback, not on the trigger bar
    row = out.iloc[-1]
    # the trigger level is the pullback's extreme so far, and the trigger bar closes beyond it
    assert (df["close"].iloc[-1] - row["trigger"]) * sign > 0


def test_ticks_to_m1_bid_candles():
    import lzma, struct
    from datetime import date
    from xahoo.data.dukascopy import ticks_to_m1
    rows = [(0, 3900_500, 3900_250, 1.0, 1.0), (30_000, 3901_500, 3901_250, 1.0, 1.0),
            (59_000, 3899_500, 3899_250, 1.0, 1.0), (61_000, 3902_500, 3902_250, 1.0, 1.0)]
    raw = lzma.compress(b"".join(struct.pack(">3i2f", *r) for r in rows))
    m = ticks_to_m1(raw, "XAUUSD", date(2026, 11, 13), 2)
    first = m.iloc[0]
    assert m.index[0] == pd.Timestamp("2026-11-13 02:00", tz="UTC")
    assert (first.open, first.high, first.low, first.close, first.volume) == (3900.25, 3901.25, 3899.25, 3899.25, 3)
    assert len(m) == 2 and m.iloc[1].close == 3902.25

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

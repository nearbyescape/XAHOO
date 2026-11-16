import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xahoo import binance, features
from xahoo.config import DATA, MODELS
from xahoo.model import apply_cal, binned_isotonic
from xahoo.store import Store

HAVE_DATA = (DATA / "binance" / "BTCUSDT_1m.parquet").exists()
HAVE_MODELS = (MODELS / "manifest.json").exists()


def synth(n=4000, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02", periods=n, freq="1min", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.0005, n)))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(50, 150, n)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.0002, "low": np.minimum(o, c) * 0.9998, "close": c,
                         "volume": v, "count": rng.integers(50, 500, n).astype(float),
                         "taker_buy_volume": v * rng.uniform(0.3, 0.7, n)}, index=idx)


def test_features_are_causal():
    """The newest feature row must not change when later bars are appended."""
    k, lead = synth(4000, 1), synth(4000, 2)
    met = pd.DataFrame({"oi": 1000 + np.arange(800.0), "top_ls_acct": 1.2, "top_ls_pos": 1.1, "ls_acct": 1.5,
                        "taker_ratio": 1.0}, index=pd.date_range("2026-03-02", periods=800, freq="5min", tz="UTC"))
    full = features.build(k, met, None, lead)
    part = features.build(k.iloc[:3000], met, None, lead.iloc[:3000])
    a, b = full.iloc[2999], part.iloc[2999]
    both = a.notna() & b.notna()
    assert both.sum() > 40
    assert np.allclose(a[both], b[both], rtol=1e-4, atol=1e-4)


def test_flow_imbalance_sign():
    k = synth(3000)
    k["taker_buy_volume"] = k["volume"]            # every trade is a buy
    f = features.build(k)
    assert (f["b_imb5"].dropna() > 0.99).all()


def test_parse_ws_messages():
    kl = {"stream": "btcusdt@kline_1m", "data": {"e": "kline", "E": 1700000030000, "s": "BTCUSDT", "k": {
        "t": 1700000000000, "T": 1700000059999, "s": "BTCUSDT", "i": "1m", "o": "100.0", "c": "101.0", "h": "102.0",
        "l": "99.0", "v": "12.5", "n": 42, "x": True, "q": "1250", "V": "7.5", "Q": "750"}}}
    ev = binance.parse_ws(kl)
    assert ev["type"] == "bar" and ev["closed"] and ev["close"] == 101.0 and ev["taker_buy_volume"] == 7.5 and ev["count"] == 42
    mp = {"data": {"e": "markPriceUpdate", "E": 1700000030000, "s": "XAUUSDT", "p": "3900.5", "i": "3900.1", "r": "0.0001", "T": 1700006400000}}
    ev = binance.parse_ws(mp)
    assert ev == {"type": "mark", "sym": "XAUUSDT", "mark": 3900.5, "index": 3900.1, "funding": 0.0001,
                  "next_funding": 1700006400000, "ts": 1700000030000}
    fo = {"data": {"e": "forceOrder", "E": 1, "o": {"s": "ETHUSDT", "S": "SELL", "q": "2", "p": "1800", "ap": "1795", "z": "2", "T": 5}}}
    ev = binance.parse_ws(fo)
    assert ev["type"] == "liq" and ev["side"] == "long" and ev["usd"] == 3590.0
    assert binance.parse_ws({"data": {"e": "something_else"}}) is None
    assert "btcusdt@kline_1m" in binance.streams(["BTCUSDT"]) and "btcusdt@markPrice@1s" in binance.streams(["BTCUSDT"])


def test_parse_klines():
    rows = [[1700000000000, "1", "2", "0.5", "1.5", "10", 1700000059999, "15", 7, "6", "9", "0"]]
    df = binance.parse_klines(rows)
    assert list(df.columns) == binance.BAR_COLS and df.iloc[0]["taker_buy_volume"] == 6 and df.iloc[0]["count"] == 7
    assert df.index[0] == pd.Timestamp("2023-11-14 22:13:20", tz="UTC")


def test_binned_isotonic_is_monotone_and_bounded():
    rng = np.random.default_rng(0)
    raw = rng.uniform(0.3, 0.7, 20000)
    y = (rng.uniform(0, 1, 20000) < 0.5 + 0.5 * (raw - 0.5)).astype(float)     # true slope 0.5: raw is overconfident
    cal = binned_isotonic(raw, y, 20)
    assert all(b >= a for a, b in zip(cal["y"], cal["y"][1:]))
    assert 0.38 < cal["y"][0] < 0.46 and 0.54 < cal["y"][-1] < 0.62
    assert apply_cal(cal, np.array([0.99]))[0] == cal["y"][-1]                 # never extrapolates beyond the data


def test_store_scoreboard():
    s = Store(Path(tempfile.mkdtemp()) / "t.db")
    s.add([(100, 160, "BTCUSDT", "1m", 0.58, 50000.0, 1.0, 0.001, "v"), (100, 160, "ETHUSDT", "1m", 0.44, 2000.0, 1.0, 0.001, "v"),
           (100, 400, "BTCUSDT", "5m", 0.51, 50000.0, 1.0, 0.001, "v")])
    due = s.due(200)
    assert len(due) == 2
    s.resolve([(1, 0.001, due[0][0]), (1, 0.002, due[1][0])])
    sb = s.scoreboard()
    assert sb["1m"]["n"] == 2 and sb["1m"]["hits"] == 1 and sb["1m"]["conf_n"] == 2
    assert s.scoreboard(sym="ETHUSDT")["1m"]["hit_rate"] == 0.0
    assert len(s.due(200)) == 0 and len(s.recent()) == 2


@pytest.mark.skipif(not (HAVE_DATA and HAVE_MODELS), reason="needs data/binance and models/")
def test_engine_replay_matches_research_features():
    """The live path must compute the same features, and so the same probabilities, as the research tables."""
    from xahoo.engine import Engine
    from xahoo.model import Models
    from xahoo.replay import SimClock, run_fast
    start = pd.Timestamp("2026-10-20 12:00", tz="UTC")
    clock = SimClock(start.timestamp())
    eng = Engine(Models(MODELS), Store(Path(tempfile.mkdtemp()) / "t.db"), clock)
    assert run_fast(eng, clock, start, 12) == 12
    row = eng.feature_row("ETHUSDT")
    ref = pd.read_parquet(DATA / "features" / "ETHUSDT.parquet").loc[start + pd.Timedelta(minutes=11)]
    cols = [c for c in eng.models.features if row[c] == row[c] and ref[c] == ref[c]]
    assert len(cols) > 50
    diff = (row[cols].astype(float) - ref[cols].astype(float)).abs()
    assert (diff < 2e-2).mean() > 0.97, diff.sort_values().tail(5).to_dict()
    fc = eng.m["BTCUSDT"].forecast["h"]
    assert set(fc) == {"1m", "5m", "15m", "1h", "4h", "1d"}
    for h, v in fc.items():
        assert 0.3 < v["p"] < 0.7 and v["lo68"] < eng.m["BTCUSDT"].forecast["ref"] < v["hi68"] and v["lo95"] < v["lo68"]
    assert not eng.m["XAGUSDT"].forecast["h"]["1m"]["show"] and eng.m["BTCUSDT"].forecast["h"]["1m"]["show"]
    assert eng.store.scoreboard()["1m"]["n"] > 50
    json.dumps(eng.snapshot(), default=str)


def test_manifest_skill_table():
    if not HAVE_MODELS:
        pytest.skip("no models")
    man = json.loads((MODELS / "manifest.json").read_text())
    assert len(man["features"]) == 62 and set(man["skill"]) >= {"BTCUSDT", "XAUUSDT", "XAGUSDT"}
    for sym, hz in man["skill"].items():
        for h, s in hz.items():
            assert s["show"] == (s["tier"] > 0)
    assert all(math.isfinite(v) for v in man["families"]["coin"]["1m"]["calibration"]["y"])


def test_levels_sides_and_reach():
    """Resistance above price, support below, nearest first; a planted double top is found; reach is monotone."""
    import json
    from xahoo.levels import find_levels, reach_prob
    rng = np.random.default_rng(3)
    n = 10080
    ts = 1_700_000_000 + 60 * np.arange(n)
    ts -= ts % 86400 - 0                          # any start is fine; keep integer seconds
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.0008, n)))
    c = c / c[-1] * 100.0                         # end at exactly 100
    h, l = c * 1.0004, c * 0.9996
    # plant a ceiling at 101.5 touched twice, a few days ago
    for k in (6000, 7500):
        h[k:k + 30] = np.maximum(h[k:k + 30], np.linspace(100.8, 101.5, 30))
    v = np.full(n, 10.0)
    out = find_levels(ts, h, l, c, v)
    assert out["resistance"] and out["support"]
    assert all(x["price"] > 100 for x in out["resistance"]) and all(x["price"] < 100 for x in out["support"])
    assert [x["dist"] for x in out["resistance"]] == sorted(x["dist"] for x in out["resistance"])
    assert [x["dist"] for x in out["support"]] == sorted((x["dist"] for x in out["support"]), reverse=True)
    assert all(1 <= x["strength"] <= 3 for x in out["resistance"] + out["support"])
    table = json.loads((MODELS / "levels.json").read_text())["reach"]["coin"]
    ps = [reach_prob(table, "1h", "up", k) for k in (0.2, 0.5, 1.0, 2.0, 3.0)]
    assert ps == sorted(ps, reverse=True) and 0 < ps[-1] < ps[0] <= 1


def test_gap_fill_adds_missing_bars_in_order():
    import asyncio
    from xahoo import app as appmod
    from xahoo.engine import Engine
    from xahoo.model import Models
    from xahoo.store import Store
    eng = Engine(Models(MODELS), Store(Path(tempfile.mkdtemp()) / "t.db"))
    idx = pd.date_range("2026-10-01", periods=4000, freq="1min", tz="UTC")
    full = pd.DataFrame({c: 1.0 for c in binance.BAR_COLS}, index=idx)
    mk = eng.m["BTCUSDT"]
    mk.bars = full.drop(full.index[[3990, 3991, 3995]]).iloc[:-1]       # holes, and the last bar not yet in

    class FakeRest:
        async def klines(self, sym, minutes):
            return full.iloc[-minutes:]                                 # the last row counts as still forming
    n = asyncio.run(appmod.gap_fill(eng, FakeRest(), "BTCUSDT"))
    assert n == 3
    assert mk.bars.index.is_monotonic_increasing and not mk.bars.index.has_duplicates
    assert len(mk.bars) == 3999 and mk.bars.index[-1] == idx[-2]


def test_reasons_and_orderflow():
    from xahoo.orderflow import WallTracker, book_walls, delta_profile
    from xahoo.reasons import explain
    r = explain([("b_imb15", -0.3), ("a_tod_sin", 0.1), ("d_ret5", 0.05), ("c_oi_1h", 0.001)],
                {"b_imb15": -0.2, "a_tod_sin": 0.4, "d_ret5": 1.8, "c_oi_1h": 0.01}, "BTC")
    assert r[0] == {"t": "Sellers dominating, last 15 min", "push": -1, "w": -0.3, "layer": "flow"}
    assert r[1]["t"] == "This time of day has tended to rise" and r[2]["t"] == "BTC sharply rising, last 5 min"
    assert len(r) == 3                                           # tiny pushes are dropped
    bids = [[100 - i * 0.01, 1.0] for i in range(300)]
    asks = [[100.01 + i * 0.01, 1.0] for i in range(300)]
    bids[50][1] = 80.0
    w = book_walls(bids, asks)
    assert len(w["bid"]) == 1 and abs(w["bid"][0]["price"] - 99.5) < 0.01 and not w["ask"]
    t = WallTracker(); t.update(w, 100.0)
    assert t.update(book_walls(bids, asks), 160.0)["bid"][0]["age"] == 60
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 0.05, 1440)); v = np.full(1440, 10.0); tb = v * 0.5; tb[:200] = 9.0
    p = delta_profile(c + 0.03, c - 0.03, c, v, tb)
    assert p["zones"]["buyers"] and len(p["buy"]) == 48


def test_parse_aggtrade():
    ev = binance.parse_ws({"data": {"e": "aggTrade", "E": 1, "s": "BTCUSDT", "p": "100000", "q": "3", "T": 5, "m": True}})
    assert ev == {"type": "trade", "sym": "BTCUSDT", "price": 100000.0, "qty": 3.0, "usd": 300000.0, "side": "sell", "ts": 5}


def test_stream_url_uses_market_route():
    # Binance retired the unrouted futures stream URL on 2026-04-23; these streams live on /market
    assert binance.WS.startswith("wss://fstream.binance.com/market/stream?streams=")
    assert binance.streams(["BTCUSDT"]) == "btcusdt@kline_1m/btcusdt@markPrice@1s/btcusdt@forceOrder/btcusdt@aggTrade"


def test_late_update_cannot_duplicate_a_closed_minute():
    """Quiet markets: the watchdog closes a minute, then a late partial update for it arrives. The chart data
    must still have unique, ascending times (a duplicate froze the screen)."""
    from xahoo.engine import Engine
    from xahoo.model import Models
    from xahoo.store import Store
    eng = Engine(Models(MODELS), Store(Path(tempfile.mkdtemp()) / "t.db"))
    mk = eng.m["XAUUSDT"]
    idx = pd.date_range("2026-11-16 10:00", periods=5, freq="1min", tz="UTC")
    mk.bars = pd.DataFrame({c: 1.0 for c in binance.BAR_COLS}, index=idx)
    t_last = int(idx[-1].timestamp() * 1000)
    eng.on_event({"type": "bar", "sym": "XAUUSDT", "t": t_last, "open": 1, "high": 2, "low": 1, "close": 2,
                  "volume": 3, "count": 1, "taker_buy_volume": 1, "closed": False, "ts": t_last + 70_000})
    assert mk.cur is None                                  # ignored: that minute is already closed
    mk.cur = {"t": t_last, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0, "count": 0.0, "taker_buy_volume": 0.0}
    for tf in (1, 5):
        d = eng.candles("XAUUSDT", tf)
        assert d["t"] == sorted(set(d["t"])), tf          # unique and ascending even with a stale forming bar



def test_ema_regime_is_causal_and_uses_daily_history():
    k = synth(30 * 1440, seed=3)
    full = features.ema_regime(k["close"])
    cut = k.index[20 * 1440 + 777]
    part = features.ema_regime(k["close"][k.index <= cut])
    a, b = full.loc[cut], part.loc[cut]
    assert np.allclose(a.fillna(-9).to_numpy(), b.fillna(-9).to_numpy(), atol=1e-5)     # no look-ahead
    # live: only ~7 days of 1m bars plus daily closes must give the 20-day input the full history gives
    win = k["close"][(k.index > cut - pd.Timedelta(minutes=10_600)) & (k.index <= cut)]
    daily = k["close"].resample("1D", label="left", closed="left").last()
    live = features.ema_regime(win, daily[daily.index < cut.floor("1D")]).loc[cut]
    assert np.isfinite(live["r_d20"]) and abs(live["r_d20"] - a["r_d20"]) < 1e-4
    assert abs(live["x_px60"] - a["x_px60"]) < 1e-3
    assert set(a.index) >= {"x_cross5", "x_px15", "x_slope60", "r_er1h", "r_state"}


def test_steady_labels_hold_until_the_lean_fades():
    from xahoo.model import steady
    seq = [0.50, 0.521, 0.515, 0.511, 0.509, 0.47, 0.485, 0.495, 0.505]
    lab, out = 0, []
    for p in seq:
        lab = steady(lab, p, 0.02, 0.01)
        out.append(lab)
    assert out == [0, 1, 1, 1, 0, -1, -1, 0, 0]
    assert [steady(0, p) for p in (0.519, 0.52, 0.48)] == [0, 1, -1]      # default: today's fixed 2-point band


def test_headline_combines_timeframes():
    from xahoo.model import headline
    spec = {"horizons": ["5m", "15m", "1h", "4h"], "calibration": {"x": [0.0, 1.0], "y": [0.0, 1.0]}, "target": "1h"}
    fc = {h: {"p": p, "show": True} for h, p in zip(spec["horizons"], (0.53, 0.52, 0.55, 0.49))}
    hd = headline(spec, fc)
    assert 0.52 < hd["p"] < 0.53 and hd["agree"] == 3 and hd["of"] == 4
    fc["4h"]["show"] = False
    assert headline(spec, fc) is None and headline(None, fc) is None


def test_ema_reasons_wording():
    from xahoo.reasons import explain
    row = {"x_px15": 1.2, "x_slope15": 0.3, "r_state": 0.0, "x_age60": float(np.log1p(6)), "x_cross60": -1.0}
    r = explain([("x_px15", 0.05), ("r_state", -0.02), ("x_age60", -0.01)], row, "BTC")
    assert r[0]["t"] == "Above its 15m EMA and rising" and r[0]["layer"] == "EMA 9/26"
    assert r[1]["t"] == "Market ranging" and r[2]["t"] == "1h bearish EMA cross 6 candles ago"


@pytest.mark.skipif(not HAVE_MODELS, reason="models not trained")
def test_models_list_every_input_they_read():
    from xahoo.model import Models
    m = Models(MODELS)
    for hz in m.manifest["families"].values():
        for spec in hz.values():
            assert set(spec.get("features_dir") or []) <= set(m.all_features)

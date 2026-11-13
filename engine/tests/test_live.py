"""Live runner: candle building, and parity with the backtest on real history (skipped without cached data)."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from xahoo.config import StrategyParams
from xahoo.data import dukascopy
from xahoo.engine import generate, run_backtest
from xahoo.live.runner import LiveRunner
from xahoo.providers.free import Quote
from xahoo.telegram import Telegram

CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"


class _NoFeed:
    def quote(self, sym):
        return None


def _runner(tmp_path):
    return LiveRunner(StrategyParams.trader(), db=tmp_path / "t.db", telegram=Telegram("", ""), feed=_NoFeed())


def test_candle_builder(tmp_path):
    r = _runner(tmp_path)
    t0 = 1_794_000_000 - 1_794_000_000 % 60
    assert r.on_quote(Quote("XAUUSD", t0 + 1, 100.0, 100.3, "t")) == []
    r.on_quote(Quote("XAUUSD", t0 + 20, 101.5, 101.8, "t"))
    r.on_quote(Quote("XAUUSD", t0 + 50, 99.0, 99.3, "t"))
    assert r.on_quote(Quote("XAUUSD", t0 + 61, 100.0, 100.3, "t")) == ["XAUUSD"]
    bar = r.m1["XAUUSD"].iloc[-1]
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (100.0, 101.5, 99.0, 99.0, 3.0)
    assert len(r.store.bars("XAUUSD", 0)) == 1


@pytest.mark.skipif(not (CACHE / "XAUUSD").exists(), reason="no cached Dukascopy data")
def test_live_matches_backtest(tmp_path):
    """Feed real history through the live code path; the signal and its outcome must equal the backtest's."""
    p = StrategyParams.trader()
    data = {s: dukascopy.load(s, CACHE, date(2026, 9, 15), date(2026, 11, 11)) for s in ("XAUUSD", "XAGUSD")}
    cand = generate(data, p, p.exec_tfs)
    cand = cand[cand["close_time"] >= pd.Timestamp("2026-10-25", tz="UTC")].reset_index(drop=True)
    bt = run_backtest(data, p, p.exec_tfs, cand=cand)
    target = bt[bt["symbol"] == "XAUUSD"].iloc[0]
    t = target["close_time"]

    r = _runner(tmp_path)
    r.m1 = {s: m[m.index < t] for s, m in data.items()}
    sigs = r.evaluate(t)
    live = [s for s in sigs if s["symbol"] == "XAUUSD"]
    assert live, "live runner produced no signal where the backtest did"
    s = live[0]
    for k in ("dir", "entry", "sl", "tp1", "add_price"):
        assert s[k] == pytest.approx(float(target[k]), rel=1e-9), k

    r.m1 = {sym: m[m.index < pd.Timestamp(target["exit_time"]) + pd.Timedelta(minutes=5)] for sym, m in data.items()}
    r.track()
    done = [x for x in r.store.signals() if x["id"] == s["id"]][0]
    assert done["state"] in {"TP", "SL", "BE", "TIME"}
    assert done["r"] == pytest.approx(float(target["r"]), abs=1e-6)

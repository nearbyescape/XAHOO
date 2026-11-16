"""Live state and forecasting.

Events (from the Binance stream or the replay feed) update per-market state. When a 1-minute bar closes for
every market, `forecast()` computes features with the same code used in research, predicts all six horizons,
stores forecasts for the scoreboard and resolves the ones that have come due.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque

import numpy as np
import pandas as pd

import json

from . import features
from .levels import find_levels, reach_prob
from .orderflow import BIG_TRADE_USD, WallTracker, book_walls, delta_profile
from .reasons import explain
from .binance import BAR_COLS
from .config import KEEP_BARS, KIND, MARKETS, ROUND_TRIP_FEE_BP, STORE_EVERY
from .features import HORIZONS, leader_of
from .model import Models
from .store import Store

log = logging.getLogger("xahoo.engine")
FEAT_TAIL = 10_500      # rows of 1m history used to compute the newest feature row


class Market:
    def __init__(self, meta: dict):
        self.meta = meta
        self.sym = meta["sym"]
        self.bars = pd.DataFrame(columns=BAR_COLS, dtype="float64")
        self.cur: dict | None = None            # forming bar
        self.mark = math.nan
        self.funding_now = math.nan
        self.next_funding = 0
        self.metrics = pd.DataFrame()
        self.funding = pd.DataFrame()
        self.flow = deque(maxlen=120)           # (second, buy_usd, sell_usd)
        self.liqs = deque(maxlen=50)
        self.forecast: dict = {}
        self.ribbon = deque(maxlen=240)         # (ts, {h: p}) one per minute: 4 hours
        self.big = deque(maxlen=60)             # recent big trades
        self.book: dict = {}
        self.walls = WallTracker()
        self.last_event = 0.0

    @property
    def price(self) -> float:
        if self.cur:
            return self.cur["close"]
        return float(self.bars["close"].iloc[-1]) if len(self.bars) else math.nan

    def add_flow(self, ts_ms: int, buy_usd: float, sell_usd: float) -> None:
        sec = ts_ms // 1000
        if self.flow and self.flow[-1][0] == sec:
            s, b, a = self.flow[-1]
            self.flow[-1] = (s, b + buy_usd, a + sell_usd)
        else:
            self.flow.append((sec, buy_usd, sell_usd))

    def flow_sum(self, now_s: int, window: int) -> tuple[float, float]:
        b = sum(x[1] for x in self.flow if x[0] > now_s - window)
        s = sum(x[2] for x in self.flow if x[0] > now_s - window)
        return b, s


class Engine:
    def __init__(self, models: Models, store: Store, clock=time.time):
        self.models, self.store, self.clock = models, store, clock
        lp = models.path / "levels.json"
        self.levels_info = json.loads(lp.read_text()) if lp.exists() else {}
        self.m = {meta["sym"]: Market(meta) for meta in MARKETS}
        self.last_minute: int | None = None      # open time (s) of the last bar that was forecast
        self.closed: dict[str, int] = {}         # sym -> open time (s) of its newest closed bar
        self.resolved_recent: deque = deque(maxlen=80)
        self.listeners: list = []                # callables(message dict)
        self.status = {"started": clock(), "feed": "starting", "bars": 0, "forecasts": 0, "last_forecast": None,
                       "compute_ms": None}

    # ------------------------------------------------------------ events
    def emit(self, msg: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(msg)
            except Exception:  # noqa: BLE001 - a broken listener must not stop the engine
                log.exception("listener failed")

    def on_event(self, ev: dict) -> None:
        mk = self.m.get(ev["sym"])
        if mk is None:
            return
        mk.last_event = self.clock()
        t = ev["type"]
        if t == "bar":
            self._on_bar(mk, ev)
        elif t == "mark":
            mk.mark = ev["mark"]
            mk.funding_now = ev.get("funding", math.nan)
            mk.next_funding = int(ev.get("next_funding") or 0)
        elif t == "trade":
            if ev["usd"] >= BIG_TRADE_USD.get(mk.sym, 1e9):
                b = {"ts": ev["ts"], "side": ev["side"], "usd": round(ev["usd"]), "price": ev["price"]}
                if ev.get("sim"):
                    b["sim"] = True
                mk.big.append(b)
                self.emit({"type": "big", "sym": mk.sym, **b})
        elif t == "liq":
            mk.liqs.append({"ts": ev["ts"], "side": ev["side"], "usd": ev["usd"], "price": ev["price"]})
            self.emit({"type": "liq", "sym": mk.sym, "side": ev["side"], "usd": ev["usd"], "price": ev["price"], "ts": ev["ts"]})

    def _on_bar(self, mk: Market, ev: dict) -> None:
        cur = mk.cur
        if cur is not None and ev["t"] > cur["t"]:
            self._close_bar(mk, cur)            # the close flag was missed: finalize on the first tick of the next bar
            cur = None
        prev_v = cur["volume"] if cur and cur["t"] == ev["t"] else 0.0
        prev_tb = cur["taker_buy_volume"] if cur and cur["t"] == ev["t"] else 0.0
        dv, dtb = max(ev["volume"] - prev_v, 0.0), max(ev["taker_buy_volume"] - prev_tb, 0.0)
        if dv > 0:
            mk.add_flow(ev.get("ts") or ev["t"], dtb * ev["close"], max(dv - dtb, 0.0) * ev["close"])
        mk.cur = {k: ev[k] for k in ("t", "open", "high", "low", "close", "volume", "count", "taker_buy_volume")}
        if ev.get("closed"):
            self._close_bar(mk, mk.cur)
            mk.cur = None

    def _close_bar(self, mk: Market, bar: dict) -> None:
        ts = pd.Timestamp(bar["t"], unit="ms", tz="UTC")
        if len(mk.bars) and ts <= mk.bars.index[-1]:
            return
        mk.bars.loc[ts] = [bar[c] for c in BAR_COLS]
        if len(mk.bars) > KEEP_BARS + 200:
            mk.bars = mk.bars.iloc[-KEEP_BARS:]
        self.closed[mk.sym] = bar["t"] // 1000
        self.status["bars"] += 1

    def minute_ready(self) -> int | None:
        """Open time (s) of a minute that every market has closed and that hasn't been forecast yet."""
        if len(self.closed) < len(self.m):
            return None
        t = min(self.closed.values())
        return t if (self.last_minute is None or t > self.last_minute) else None

    def force_close(self, minute_s: int) -> None:
        """Watchdog: finalize bars for markets whose close message hasn't arrived (quiet market)."""
        for mk in self.m.values():
            if self.closed.get(mk.sym, 0) >= minute_s:
                continue
            if mk.cur and mk.cur["t"] // 1000 == minute_s:
                self._close_bar(mk, mk.cur)
                mk.cur = None
            elif len(mk.bars):
                c = float(mk.bars["close"].iloc[-1])
                self._close_bar(mk, {"t": minute_s * 1000, "open": c, "high": c, "low": c, "close": c, "volume": 0.0,
                                     "count": 0.0, "taker_buy_volume": 0.0})

    def set_book(self, sym: str, depth: dict, simulated: bool = False) -> None:
        """New order-book snapshot -> walls (with age) and imbalance; pushed to the screen."""
        mk = self.m.get(sym)
        if mk is None:
            return
        w = book_walls(depth.get("bids", []), depth.get("asks", []))
        if not w:
            return
        mk.walls.update(w, self.clock())
        w["ts"] = self.clock()
        if simulated:
            w["sim"] = True
        mk.book = w
        self.emit({"type": "book", "sym": sym, "book": w})

    def big15(self, mk: Market, now_s: float) -> list[float]:
        b = sum(x["usd"] for x in mk.big if x["side"] == "buy" and x["ts"] / 1000 > now_s - 900)
        s_ = sum(x["usd"] for x in mk.big if x["side"] == "sell" and x["ts"] / 1000 > now_s - 900)
        return [round(b), round(s_)]

    # ------------------------------------------------------------ forecasting
    def feature_row(self, sym: str) -> pd.Series | None:
        mk = self.m[sym]
        if len(mk.bars) < 3000:
            return None
        k = mk.bars.iloc[-FEAT_TAIL:]
        lead = self.m[leader_of(sym)].bars.iloc[-FEAT_TAIL - 10:]
        f = features.build(k, mk.metrics if len(mk.metrics) else None, mk.funding if len(mk.funding) else None,
                           lead if len(lead) else None)
        row = f.iloc[-1].copy()
        r1 = np.log(k["close"]).diff()
        row["sig1d"] = float(r1.iloc[-1440:].std())
        return row

    def forecast(self, minute_s: int) -> dict:
        """Forecast every market as of the close of the bar that opened at minute_s."""
        t0 = time.perf_counter()
        now = minute_s + 60
        rows, syms = [], []
        for sym in self.m:
            r = self.feature_row(sym)
            if r is not None:
                rows.append(r)
                syms.append(sym)
        out = {}
        if rows:
            X = pd.DataFrame(rows).reindex(columns=self.models.features + ["sig1d"])
            preds = self.models.predict(X, [KIND[s] for s in syms], syms)
            to_store = []
            minute_idx = now // 60
            for sym, r, pr in zip(syms, rows, preds):
                mk = self.m[sym]
                ref = mk.mark if mk.mark == mk.mark else mk.price       # mark price is the reference; last price if absent
                sig = float(r["sig1d"]) if r["sig1d"] == r["sig1d"] else 0.0
                fc = {}
                lead_short = self.m[leader_of(sym)].meta["short"]
                for h, n in HORIZONS.items():
                    if h not in pr:
                        continue
                    d = pr[h]
                    s_h = sig * math.sqrt(n)
                    b68, b95 = d["u68"] * s_h, d["u95"] * s_h
                    skill = self.models.skill(sym, h)
                    fc[h] = {"p": round(d["p"], 4), "band68": round(b68, 6), "band95": round(b95, 6),
                             "lo68": ref * math.exp(-b68), "hi68": ref * math.exp(b68),
                             "lo95": ref * math.exp(-b95), "hi95": ref * math.exp(b95),
                             "move_bp": round(b68 * 1e4, 1), "tradable": bool(b68 * 1e4 > ROUND_TRIP_FEE_BP),
                             "layers": {k: round(v, 3) for k, v in d["layers"].items()},
                             "show": bool(skill.get("show", False)) and d["has_dir"], "tier": int(skill.get("tier", 0)),
                             "reasons": explain(d.get("top", []), r, lead_short) if d.get("top") else []}
                    if fc[h]["show"] and minute_idx % STORE_EVERY[h] == 0:      # only shown forecasts are scored
                        to_store.append((now, now + n * 60, sym, h, d["p"], ref, d["u68"], s_h, self.models.version))
                tail = mk.bars.iloc[-1440:]
                prof = delta_profile(tail["high"].to_numpy(), tail["low"].to_numpy(), tail["close"].to_numpy(),
                                     tail["volume"].to_numpy(), tail["taker_buy_volume"].to_numpy())
                mk.forecast = {"ts": now, "ref": ref, "h": fc, "levels": self.levels(sym, ref, fc), "profile": prof}
                mk.ribbon.append((now, {h: v["p"] for h, v in fc.items()}))
                out[sym] = mk.forecast
            if to_store:
                self.store.add(to_store)
            self.status["forecasts"] += len(to_store)
        self.last_minute = minute_s
        self.resolve(now)
        self.status.update(last_forecast=now, compute_ms=round((time.perf_counter() - t0) * 1000))
        self.emit({"type": "forecast", "ts": now, "markets": out})
        return out

    def levels(self, sym: str, ref: float, fc: dict) -> dict:
        """Support / resistance from the last 7 days, with the measured chance of price reaching each level."""
        mk = self.m[sym]
        b = mk.bars.iloc[-10080:]
        if len(b) < 1500:
            return {"resistance": [], "support": []}
        ts = np.asarray((b.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1), dtype=np.int64)
        lv = find_levels(ts, b["high"].to_numpy(), b["low"].to_numpy(), b["close"].to_numpy(), b["volume"].to_numpy(), ref)
        table = (self.levels_info.get("reach") or {}).get(KIND[sym])
        for side, key in (("up", "resistance"), ("down", "support")):
            for x in lv[key]:
                x["reach"] = {}
                for h in ("15m", "1h", "4h", "1d"):
                    if h in fc and fc[h]["band68"] > 0:
                        p = reach_prob(table, h, side, abs(x["dist"]) / fc[h]["band68"])
                        if p is not None:
                            x["reach"][h] = round(p, 3)
                x["price"] = round(x["price"], 8)
                x["dist"] = round(x["dist"], 6)
                x["dist_sig"] = round(x["dist_sig"], 3)
        return {"tol": lv["tol"], "resistance": lv["resistance"], "support": lv["support"]}

    def resolve(self, now: int) -> None:
        due = self.store.due(now)
        if not due:
            return
        upd, shown = [], []
        for fid, sym, h, p, price, due_ts in due:
            mk = self.m.get(sym)
            cur = mk.mark if mk and mk.mark == mk.mark else (mk.price if mk else math.nan)
            if cur != cur or now - due_ts > 180:           # no price, or resolved too late to be fair (e.g. after downtime)
                upd.append((-1, None, fid))
                continue
            ret = math.log(cur / price)
            outcome = 1 if ret > 0 else (0 if ret < 0 else -1)
            upd.append((outcome, ret, fid))
            if outcome >= 0:
                shown.append({"sym": sym, "h": h, "p": round(p, 4), "outcome": outcome, "ret": ret, "due": due_ts})
        self.store.resolve(upd)
        if shown:
            self.resolved_recent.extend(shown)
            self.emit({"type": "resolved", "items": shown[-40:]})

    # ------------------------------------------------------------ views
    def tick(self) -> dict:
        """Lightweight per-second update for the screen."""
        now_s = int(self.clock())
        out = {}
        for sym, mk in self.m.items():
            b5, s5 = mk.flow_sum(now_s, 5)
            b60, s60 = mk.flow_sum(now_s, 60)
            out[sym] = {"price": mk.price, "mark": mk.mark, "b5": b5, "s5": s5, "b60": b60, "s60": s60, "big15": self.big15(mk, now_s),
                        "funding": mk.funding_now, "next_funding": mk.next_funding or None, "age": round(self.clock() - mk.last_event, 2) if mk.last_event else None}
        return {"type": "tick", "ts": self.clock(), "m": out}

    def snapshot(self) -> dict:
        mk_out = {}
        for sym, mk in self.m.items():
            c = mk.bars["close"]
            day_ago = float(c.iloc[-1440]) if len(c) >= 1440 else (float(c.iloc[0]) if len(c) else math.nan)
            oi = mk.metrics["oi"].dropna() if "oi" in mk.metrics else pd.Series(dtype=float)
            ls = mk.metrics["ls_acct"].dropna() if "ls_acct" in mk.metrics else pd.Series(dtype=float)
            mk_out[sym] = {
                "price": mk.price, "mark": mk.mark, "day_ago": day_ago, "forecast": mk.forecast,
                "ribbon": [[t, p] for t, p in mk.ribbon],
                "spark": [float(x) for x in c.iloc[-180:]] if len(c) else [],
                "oi_chg_1h": float(oi.iloc[-1] / oi.iloc[-13] - 1) if len(oi) > 13 else None,
                "ls_ratio": float(ls.iloc[-1]) if len(ls) else None,
                "funding": mk.funding_now if mk.funding_now == mk.funding_now else (float(mk.funding["funding"].iloc[-1]) if len(mk.funding) else None),
                "liqs": list(mk.liqs)[-10:],
                "big": list(mk.big)[-30:], "big15": self.big15(mk, self.clock()), "book": mk.book,
            }
        return {"type": "snapshot", "ts": self.clock(), "markets": MARKETS, "horizons": list(HORIZONS),
                "m": mk_out, "model": {"version": self.models.version, "trained_through": self.models.manifest.get("trained_through"),
                                       "skill": self.models.manifest["skill"],
                                       "levels": {"hold": self.levels_info.get("hold"), "period": self.levels_info.get("period")}},
                "status": self.status, "resolved": list(self.resolved_recent)[-40:], "big_usd": BIG_TRADE_USD}

    def candles(self, sym: str, tf_min: int = 1, limit: int = 500) -> dict:
        mk = self.m[sym]
        b = mk.bars
        if mk.cur:
            cur = pd.DataFrame([[mk.cur[c] for c in BAR_COLS]], columns=BAR_COLS,
                               index=[pd.Timestamp(mk.cur["t"], unit="ms", tz="UTC")])
            b = pd.concat([b, cur])
        if tf_min > 1:
            b = b.resample(f"{tf_min}min").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                "volume": "sum", "taker_buy_volume": "sum"}).dropna()
        b = b.iloc[-limit:]
        return {"sym": sym, "tf": tf_min, "t": [int(x.timestamp()) for x in b.index],
                "o": b["open"].round(8).tolist(), "h": b["high"].round(8).tolist(), "l": b["low"].round(8).tolist(),
                "c": b["close"].round(8).tolist(), "v": b["volume"].tolist(),
                "tb": b["taker_buy_volume"].tolist()}

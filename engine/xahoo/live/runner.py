"""Live signal service on a free feed.

  python -m xahoo.live.runner            # headless (Telegram only)
  XAHOO_MODE=live uvicorn xahoo.api:app  # with the terminal UI (runner starts inside the API process)

Loop (every `poll` seconds): fetch quotes -> build 1m BID candles -> at each 5m close run the same strategy code
as the backtests (StrategyParams.trader()) on the last 45 days -> new signals are stored and sent to Telegram ->
open signals are re-simulated on the 1m bars since entry with the same tracker as the backtests, and every state
change (2nd lot added, stop to average entry, target / stop / time exit) is stored and sent as a reply.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import SYMBOLS, TF_MINUTES, StrategyParams
from ..data import dukascopy
from .. import features
from ..engine import generate
from ..strategy.setups import impulse_forming
from ..providers.free import FreeFeed, Quote
from ..telegram import NAMES, Telegram, _px, format_prealert, format_signal, format_update
from .push import WebPush
from ..tracker import simulate_scalein
from .guard import GuardConfig, evaluate as guard_eval
from .store import Store

log = logging.getLogger("xahoo.live")
ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "dukascopy"
HISTORY_DAYS = 45
CLOSED = {"TP", "SL", "BE", "TRAIL", "TIME"}


class LiveRunner:
    def __init__(self, params: StrategyParams | None = None, poll: float = 2.0, db: Path | None = None,
                 telegram: Telegram | None = None, feed: FreeFeed | None = None):
        self.p = params or StrategyParams.trader()
        self.poll = poll
        self.store = Store(db or ROOT / "data" / "live.db")
        self.tg = telegram or Telegram()
        self.push = WebPush((db or ROOT / "data" / "live.db").parent / "vapid_private.pem")
        self.feed = feed or FreeFeed()
        self.m1: dict[str, pd.DataFrame] = {}
        self.cur: dict[str, dict] = {}
        self.quotes: dict[str, Quote] = {}
        self.started = time.time()
        self.last_eval: pd.Timestamp | None = None
        self.status = {"feed": "starting", "last_quote": None, "last_bar": None, "ready": False, "errors": 0}
        self._lock = threading.Lock()
        self._next_history = time.time() + 3600
        self.watch: dict[str, dict] = {}
        self.history_ready = False
        self.prealerts = os.environ.get("XAHOO_PREALERTS", "on").lower() != "off"
        self.watch: dict[str, dict] = {}
        self.prealerts = os.environ.get("XAHOO_PREALERTS", "on").lower() != "off"

    # ------------------------------------------------------------ history
    def _history_range(self):
        today = datetime.now(timezone.utc).date()
        return today - timedelta(days=HISTORY_DAYS + 10), today

    def history_progress(self) -> dict:
        """Cached days vs days needed (the downloader skips Saturdays), across both symbols."""
        start, today = self._history_range()
        need = [start + timedelta(days=i) for i in range((today - start).days) if (start + timedelta(days=i)).weekday() != 5]
        done = sum((CACHE / sym / f"{d.isoformat()}.bi5").exists() for sym in SYMBOLS for d in need)
        total = len(need) * len(SYMBOLS)
        return {"done": done, "total": total, "pct": round(100 * done / max(total, 1)), "ready": self.history_ready}

    def backfill(self, download: bool = True) -> None:
        """Download (throttled) and load ~55 days of 1m history, then merge any live bars on top.
        Runs in a background thread on a fresh server; live quotes keep flowing meanwhile."""
        start, today = self._history_range()
        for sym in SYMBOLS:
            if download:
                try:
                    dukascopy.download(sym, start, today - timedelta(days=1), CACHE, pause=3.0,
                                       log=lambda m: log.info("history %s (%s)", m, self.history_progress()["pct"]))
                except Exception as e:  # noqa: BLE001 - history gaps are tolerated, live bars fill in
                    log.warning("backfill %s: %s", sym, e)
            try:
                hist = dukascopy.load(sym, CACHE, start, today)
            except FileNotFoundError:
                hist = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            live = self.store.bars(sym, int(hist.index[-1].timestamp()) + 60 if len(hist) else 0)
            with self._lock:
                m = pd.concat([hist, live, self.m1.get(sym, hist.iloc[:0])]).sort_index()
                self.m1[sym] = m[~m.index.duplicated(keep="last")]
        self.fill_today(download)
        self.history_ready = True
        log.info("history ready: %s", {s: len(m) for s, m in self.m1.items()})

    def fill_today(self, download: bool = True) -> None:
        """Fill today's completed hours (UTC) that have no candles yet from Dukascopy hourly tick files, so the
        chart has no hole before the service started and signals can start sooner after a restart."""
        now = datetime.now(timezone.utc)
        day = now.date()
        for sym in SYMBOLS:
            m = self.m1.get(sym)
            have = set() if m is None else set(m.index[m.index >= pd.Timestamp(day, tz="UTC")].hour)
            missing = [h for h in range(now.hour) if h not in have]
            if not missing or not download:
                continue
            bars = dukascopy.fetch_today_hours(sym, day, missing, CACHE, log=log.info)
            if bars.empty:
                continue
            with self._lock:
                cur = self.m1.get(sym, bars.iloc[:0])
                merged = pd.concat([bars, cur]).sort_index()
                self.m1[sym] = merged[~merged.index.duplicated(keep="last")]   # live bars win where both exist
            log.info("filled today %s: %d bars from %d hourly tick files", sym, len(bars), len(missing))

    def refresh_history(self) -> None:
        """Hourly: fetch any finished days Dukascopy has published since startup (e.g. yesterday) and merge them
        under the live bars, so indicators run on complete history."""
        today = datetime.now(timezone.utc).date()
        for sym in SYMBOLS:
            try:
                dukascopy.download(sym, today - timedelta(days=5), today - timedelta(days=1), CACHE, pause=3.0,
                                   log=log.info)
                hist = dukascopy.load(sym, CACHE, today - timedelta(days=5), today)
            except Exception as e:  # noqa: BLE001
                log.warning("history refresh %s: %s", sym, e)
                continue
            with self._lock:
                m = pd.concat([self.m1.get(sym, hist.iloc[:0]), hist]).sort_index()
                self.m1[sym] = m[~m.index.duplicated(keep="first")]   # keep live bars where both exist
        self.fill_today()

    # ------------------------------------------------------------ candles
    def on_quote(self, q: Quote) -> list[str]:
        """Fold a quote into the current 1m BID bar. Returns symbols whose bar just closed."""
        closed = []
        minute = int(q.ts // 60) * 60
        b = self.cur.get(q.symbol)
        if b is not None and minute > b["t"]:
            self._close_bar(q.symbol, b)
            closed.append(q.symbol)
            b = None
        if b is None:
            b = self.cur[q.symbol] = {"t": minute, "o": q.bid, "h": q.bid, "l": q.bid, "c": q.bid, "v": 0, "sp": []}
        b["h"], b["l"], b["c"] = max(b["h"], q.bid), min(b["l"], q.bid), q.bid
        b["v"] += 1
        b["sp"].append(q.ask - q.bid)
        return closed

    def _close_bar(self, sym: str, b: dict) -> None:
        ts = pd.Timestamp(b["t"], unit="s", tz="UTC")
        row = pd.DataFrame({"open": [b["o"]], "high": [b["h"]], "low": [b["l"]], "close": [b["c"]],
                            "volume": [float(b["v"])]}, index=pd.DatetimeIndex([ts], name="ts"))
        with self._lock:
            self.m1[sym] = pd.concat([self.m1.get(sym, row.iloc[:0]), row])
        self.store.add_bars(sym, [(b["t"], b["o"], b["h"], b["l"], b["c"], float(b["v"]), float(np.mean(b["sp"])))])
        self.status["last_bar"] = int(b["t"])

    def ready(self, sym: str) -> bool:
        """Signals need continuous recent data: no gap > 5 min in the last 150 minutes of 1m bars."""
        m = self.m1.get(sym)
        if m is None or len(m) < 500:
            return False
        recent = m.index[m.index >= m.index[-1] - pd.Timedelta(minutes=150)]
        return len(recent) > 100 and (pd.Series(recent).diff().max() <= pd.Timedelta(minutes=5))

    # ------------------------------------------------------------ notifications
    def notify(self, kind: str, level: str, title: str, body: str, ref: str | None = None, tg_text: str | None = None,
               reply_to: int | None = None, external: bool = True, push: bool = True) -> int | None:
        """One path for every alert: dashboard bell (always), Telegram and device push (if `external`)."""
        self.store.add_alert(kind, level, title, body, ref)
        msg_id = None
        if external:
            try:
                msg_id = self.tg.send(tg_text or f"{title}\n{body}", reply_to=reply_to)
            except Exception as e:  # noqa: BLE001 - a Telegram outage must not stop the service
                log.warning("telegram: %s", e)
            if push:
                threading.Thread(target=self._push_all, daemon=True).start()
        return msg_id

    def _push_all(self) -> None:
        subs = self.store.get("push_subs", []) or []
        keep = []
        for sub in subs:
            try:
                code = self.push.send(sub)
            except Exception as e:  # noqa: BLE001
                log.warning("push: %s", e)
                code = 0
            if code not in (404, 410):
                keep.append(sub)
        if len(keep) != len(subs):
            self.store.put("push_subs", keep)

    # ------------------------------------------------------------ strategy stop rules
    def guard(self, notify: bool = True) -> dict:
        closed = [x for x in self.store.signals(5000) if x["state"] in CLOSED and x.get("r") is not None]
        g = guard_eval(closed, pd.Timestamp.now(tz="UTC"), GuardConfig(),
                       baseline_ts=self.store.get("guard_baseline", 0), manual_pause=self.store.get("guard_manual"))
        prev = self.store.get("guard_state")
        if g["state"] != prev:
            self.store.put("guard_state", g["state"])
            if notify and prev is not None:
                text = {"ACTIVE": "✅ XAHOO active — normal size",
                        "HALF": "⚠️ XAHOO half size — risk 0.25% per lot",
                        "DAY_STOP": "⏸ XAHOO day stop — no new signals until tomorrow (UTC)",
                        "PAUSED": "🛑 XAHOO PAUSED — no new signals until you resume in the dashboard"}[g["state"]]
                self.notify("guard", "info" if g["state"] == "ACTIVE" else "warn", text,
                            "; ".join(g["reasons"]) or "normal operation",
                            tg_text=text + ("\n" + "\n".join(g["reasons"]) if g["reasons"] else ""))
        return g

    def pause(self, reason: str = "paused by owner") -> dict:
        self.store.put("guard_manual", reason)
        return self.guard()

    def resume(self) -> dict:
        """Clear a pause and restart drawdown / edge tracking from now."""
        self.store.put("guard_manual", None)
        self.store.put("guard_baseline", int(time.time()))
        return self.guard()

    # ------------------------------------------------------------ signals
    def evaluate(self, bar_close: pd.Timestamp) -> list[dict]:
        """Run the strategy at a 5m close; store and announce new signals."""
        window = {s: m[m.index >= bar_close - pd.Timedelta(days=HISTORY_DAYS)] for s, m in self.m1.items() if len(m)}
        if not window:
            return []
        cand = generate(window, self.p, self.p.exec_tfs)
        if cand.empty:
            return []
        cand = cand[cand["close_time"] == bar_close]
        if cand.empty:
            return []
        g = self.guard()
        if g["risk_mult"] <= 0:
            log.info("guard %s: %d candidate(s) not sent", g["state"], len(cand))
            return []
        out = []
        open_syms = {s["symbol"] for s in self.store.signals(open_only=True)}
        for rec in cand.to_dict("records"):
            sym = rec["symbol"]
            if sym in open_syms or not self.ready(sym) or self._sl_today(sym) >= self.p.max_sl_per_day:
                continue
            ist = bar_close + pd.Timedelta(minutes=330)
            sig = {
                "id": f"SIG-{ist:%Y%m%d-%H%M}-{sym[:3]}", "created": int(bar_close.timestamp()), "symbol": sym,
                "tf": rec["tf"], "dir": int(rec["dir"]), "setup": rec["setup"], "grade": rec["grade"],
                "score": float(rec["score"]), "entry": float(rec["entry"]), "sl": float(rec["sl"]),
                "tp1": float(rec["tp1"]), "tp2": float(rec["tp2"]), "tp3": float(rec["tp3"]),
                "add_price": float(rec["add_price"]) if pd.notna(rec.get("add_price")) else None,
                "risk": float(rec["risk"]), "atr": float(rec["atr"]), "session": rec["session"],
                "overlap": bool(rec["overlap"]), "1h_bias": int(rec["1h_bias"]), "4h_bias": int(rec["4h_bias"]),
                "d_trend": int(rec["d_trend"]), "close_time": int(bar_close.timestamp()), "source": "live",
                "components": rec.get("components", {}), "risk_mult": g["risk_mult"],
            }
            spikes = features.news_spikes(window[sym][window[sym].index >= bar_close - pd.Timedelta(days=25)])
            sig["news_impulse"] = bool(len(spikes) and ((bar_close - spikes[spikes <= bar_close]).min()
                                                         <= pd.Timedelta(minutes=90) if (spikes <= bar_close).any() else False))
            pre = self.store.get(f"prealert:{sym}")
            reply_to = pre["msg_id"] if pre and pre.get("dir") == sig["dir"] else None
            if pre:
                self.store.put(f"prealert:{sym}", None)
                self.watch.pop(sym, None)
            side = "BUY" if sig["dir"] == 1 else "SELL"
            body = (f"Entry {_px(sig['entry'], sym)} · add {_px(sig['add_price'], sym) if sig['add_price'] else '-'} · "
                    f"SL {_px(sig['sl'], sym)} · TP {_px(sig['tp1'], sym)}"
                    + (" · HALF SIZE" if sig["risk_mult"] < 1 else "") + (" · 📰 news impulse" if sig["news_impulse"] else ""))
            msg_id = self.notify("signal", "signal", f"{side} {NAMES.get(sym, sym)} — signal", body, ref=sig["id"],
                                 tg_text=format_signal(sig), reply_to=reply_to)
            self.store.upsert_signal(sig, "OPEN", msg_id)
            self.store.event(sig["id"], sig["created"], "OPEN", sig["entry"], "signal")
            out.append(sig)
            open_syms.add(sym)
        return out

    def update_watch(self, bar_close: pd.Timestamp, fired: set[str]) -> None:
        """Pre-alerts: setups whose impulse is done and whose pullback has reached the EMA12 zone, but that
        haven't triggered yet. One active pre-alert per symbol; cancelled with a reply when it expires."""
        g = self.guard(notify=False)
        for sym, m in self.m1.items():
            if sym in fired or not self.ready(sym):
                continue
            win = m[m.index >= bar_close - pd.Timedelta(days=HISTORY_DAYS)]
            f = features.build(win, "5m", self.p)
            f = f[f["close_time"] <= bar_close]
            if f.empty or f["close_time"].iloc[-1] != bar_close:
                continue
            tail = f.iloc[-(self.p.ip_impulse_bars + self.p.ip_max_wait + 5):]
            best = None
            for d in (1, -1):
                fm = impulse_forming(f.iloc[-400:], self.p, d)
                if fm.empty or fm.index[-1] != tail.index[-1]:
                    continue
                row = fm.iloc[-1]
                risk_ok = abs(row["trigger"] - row["sl_est"]) <= self.p.sl_max_atr * f["atr"].iloc[-1]
                if row["ema_touched"] and risk_ok:
                    best = {"symbol": sym, "dir": d, **{k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                                                       for k, v in row.items() if k not in ("dir",)}}
            pre = self.store.get(f"prealert:{sym}")
            if best and g["risk_mult"] > 0:
                key = f"{best['dir']}:{pd.Timestamp(best['extreme_time']).isoformat()}"
                best.update(key=key, extreme_time=str(best["extreme_time"]), close_time=int(bar_close.timestamp()))
                self.watch[sym] = best
                if not pre or pre.get("key") != key:
                    side = "BUY" if best["dir"] == 1 else "SELL"
                    beyond = "above" if best["dir"] == 1 else "below"
                    msg_id = self.notify(
                        "prealert", "warn", f"GET READY · {side} {NAMES.get(sym, sym)}",
                        f"Setup forming: trigger = 5m close {beyond} {_px(best['trigger'], sym)} "
                        f"(≤ {int(best['bars_left']) * 5} min) · stop ≈ {_px(best['sl_est'], sym)}",
                        ref=key, tg_text=format_prealert(best), external=self.prealerts)
                    self.store.put(f"prealert:{sym}", {**best, "msg_id": msg_id})
            elif pre:
                self.watch.pop(sym, None)
                self.store.put(f"prealert:{sym}", None)
                self.notify("cancel", "muted", f"Setup cancelled · {NAMES.get(sym, sym)}",
                            "No breakdown in time — no trade.", ref=pre.get("key"), tg_text=format_update("CANCELLED"),
                            reply_to=pre.get("msg_id"), external=self.prealerts and bool(pre.get("msg_id")), push=False)

    def _sl_today(self, sym: str) -> int:
        day0 = int(pd.Timestamp.now(tz="UTC").normalize().timestamp())
        return sum(1 for s in self.store.signals(200) if s["symbol"] == sym and s["state"] == "SL"
                   and s.get("exit_time", 0) >= day0)

    def track(self) -> None:
        """Re-simulate every open signal on the bars since entry; announce state changes."""
        for sig in self.store.signals(open_only=True):
            m = self.m1.get(sig["symbol"])
            if m is None or not len(m):
                continue
            start = m.index.searchsorted(pd.Timestamp(sig["created"], unit="s", tz="UTC"))
            if start >= len(m):
                continue
            trail = None
            tp = sig["tp1"]
            if self.p.exit_mode == "trail_ema":
                from ..indicators import ema_closed_on_1m
                trail = ema_closed_on_1m(m)
                tp = sig["entry"] + sig["dir"] * 5.0 * sig["risk"]
            o = simulate_scalein(m["low"].to_numpy(), m["high"].to_numpy(), m["close"].to_numpy(), start, len(m),
                                 sig["dir"], sig["entry"], sig["sl"], tp, sig.get("add_price"),
                                 SYMBOLS[sig["symbol"]].spread, self.p.be_at_r, trail, 0.1 * sig["atr"])
            age_min = (m.index[-1] - pd.Timestamp(sig["created"], unit="s", tz="UTC")).total_seconds() / 60
            if o.result == "TIME" and age_min < self.p.max_hold_minutes[sig["tf"]]:
                state = "RISK_FREE" if o.be_idx is not None else ("ADDED" if o.add_idx is not None else "OPEN")
            else:
                state = o.result
            prev = sig["state"]
            notes = []
            if o.add_idx is not None and not sig.get("added"):
                sig["added"] = int(m.index[o.add_idx].timestamp())
                notes.append(("ADDED", sig["add_price"], f"2nd lot filled @ {sig['add_price']:.2f}"))
            if o.be_idx is not None and not sig.get("risk_free"):
                sig["risk_free"] = int(m.index[o.be_idx].timestamp())
                notes.append(("RISK_FREE", None, "stop moved to average entry"))
            if state in CLOSED and prev not in CLOSED:
                sig.update(result=state, r=o.r, exit_time=int(m.index[o.exit_idx].timestamp()) + 60,
                           exit_price=o.exit_price, lots=o.lots, mfe_r=o.mfe_r, mae_r=o.mae_r,
                           minutes=int(age_min))
                notes.append((state, o.exit_price, f"{o.r:+.2f}R"))
            if not notes:
                continue
            sig["updated"] = int(time.time())
            self.store.upsert_signal(sig, state)
            for st, px, note in notes:
                self.store.event(sig["id"], sig["updated"], st, px, note)
                txt = format_update(st, o.r if st in CLOSED else 0.0, px)
                lvl = "good" if (st in ("TP", "TRAIL") or (st in CLOSED and o.r > 0)) else ("bad" if st == "SL" else "info")
                self.notify("update", lvl, f"{NAMES.get(sig['symbol'], sig['symbol'])} · {st.replace('_', ' ')}",
                            txt, ref=sig["id"], tg_text=txt, reply_to=sig.get("msg_id"))

    # ------------------------------------------------------------ loop
    def step(self) -> None:
        if time.time() >= self._next_history:
            self._next_history = time.time() + 3600
            threading.Thread(target=self.refresh_history, daemon=True).start()
        closed_any = False
        for sym in SYMBOLS:
            q = self.feed.quote(sym)
            if q is None:
                self.status["errors"] += 1
                continue
            if time.time() - q.ts > 120:          # stale quote (market closed / feed lag): don't build bars from it
                self.status["feed"] = "stale"
                continue
            self.quotes[sym] = q
            self.status.update(feed=q.source, last_quote=q.ts)
            if self.on_quote(q):
                closed_any = True
        if not closed_any:
            return
        last = max(int(b["t"]) for b in self.cur.values())          # the open minute; previous minute just closed
        bar_close = pd.Timestamp(last, unit="s", tz="UTC")
        self.status["ready"] = all(self.ready(s) for s in self.m1)
        self.track()
        if bar_close.minute % TF_MINUTES["5m"] == 0 and bar_close != self.last_eval:
            self.last_eval = bar_close
            fired = set()
            for sig in self.evaluate(bar_close):
                log.info("signal %s", sig["id"])
                fired.add(sig["symbol"])
            self.update_watch(bar_close, fired)

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            t0 = time.time()
            try:
                self.step()
            except Exception:  # noqa: BLE001 - keep the service alive; errors are logged
                log.exception("live step failed")
                self.status["errors"] += 1
            stop.wait(max(0.2, self.poll - (time.time() - t0)))


def main():
    logging.basicConfig(level=os.environ.get("XAHOO_LOG", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    r = LiveRunner()
    log.info("backfilling history (Dukascopy, throttled)…")
    r.backfill(download=os.environ.get("XAHOO_BACKFILL", "1") == "1")
    log.info("history: %s", {s: len(m) for s, m in r.m1.items()})
    r.run_forever()


if __name__ == "__main__":
    main()

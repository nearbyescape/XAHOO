"""Research recorder: one row per market per minute with the live data Binance does not archive.

Order book (from the ~15-second depth snapshots): spread, size at the best prices, resting USD and imbalance
within 0.1 / 0.25 / 0.5 / 1 / 2% of the mid (last snapshot of the minute, plus the minute's average imbalance),
and the largest wall on each side. Single trades (aggTrade): count, largest trade, big-trade buy / sell USD.
Liquidations (forceOrder): long / short USD and count. The predicted funding rate from the mark-price stream.

Taker buy / sell volume per minute is not recorded: the archive already has it. Written to DATA/micro.db (live mode
only), so that after some weeks research can test whether these inputs make the direction probabilities more
accurate (docs/RESEARCH.md section 14).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .orderflow import DEPTHS

KEYS = [f"{w * 100:g}".replace(".", "_") for w in DEPTHS]
COLS = (["ts", "sym", "mid", "mark", "spread_bp", "bid1_usd", "ask1_usd"]
        + [f"{s}_{k}" for k in KEYS for s in ("bid", "ask", "imb")]
        + ["imb_0_25_avg", "imb_1_avg", "n_book", "book_age_s", "covered_bid", "covered_ask",
           "wall_bid_usd", "wall_bid_dist", "wall_ask_usd", "wall_ask_dist",
           "n_trades", "max_trade_usd", "big_buy_usd", "big_sell_usd", "n_big",
           "liq_long_usd", "liq_short_usd", "n_liq", "funding_pred"])
INT_COLS = {"ts", "n_book", "n_trades", "n_big", "n_liq"}


class Recorder:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        typed = ", ".join(f"{c} {'INTEGER' if c in INT_COLS else 'TEXT' if c == 'sym' else 'REAL'}" for c in COLS)
        self.db.executescript(f"CREATE TABLE IF NOT EXISTS micro ({typed}, PRIMARY KEY (ts, sym)) WITHOUT ROWID;")
        self.lock = threading.Lock()
        self.rows = self.db.execute("SELECT COUNT(*) FROM micro").fetchone()[0]

    def write(self, rows: list[dict]) -> None:
        if not rows:
            return
        q = f"INSERT OR REPLACE INTO micro ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})"
        with self.lock:
            self.db.executemany(q, [[r.get(c) for c in COLS] for r in rows])
            self.db.commit()
            self.rows += len(rows)

    def summary(self) -> dict:
        with self.lock:
            n, a, b = self.db.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM micro").fetchone()
            per = dict(self.db.execute("SELECT sym, COUNT(*) FROM micro GROUP BY sym").fetchall())
        return {"rows": n, "first": a, "last": b, "days": round((b - a) / 86400, 2) if a and b else 0, "per_market": per}

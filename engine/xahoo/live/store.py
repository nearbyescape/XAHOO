"""SQLite persistence for the live service: 1m bars, signals and their lifecycle events."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (symbol TEXT, ts INTEGER, open REAL, high REAL, low REAL, close REAL,
                                 volume REAL, spread REAL, PRIMARY KEY (symbol, ts));
CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, created INTEGER, symbol TEXT, state TEXT,
                                    payload TEXT, msg_id INTEGER, updated INTEGER);
CREATE TABLE IF NOT EXISTS events (signal_id TEXT, ts INTEGER, state TEXT, price REAL, note TEXT);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def add_bars(self, symbol: str, rows: list[tuple]):
        with self.lock:
            self.db.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?)",
                                [(symbol, *r) for r in rows])
            self.db.commit()

    def bars(self, symbol: str, since_ts: int) -> pd.DataFrame:
        with self.lock:
            df = pd.read_sql_query("SELECT ts, open, high, low, close, volume FROM bars WHERE symbol=? AND ts>=? ORDER BY ts",
                                   self.db, params=(symbol, since_ts))
        df.index = pd.to_datetime(df.pop("ts"), unit="s", utc=True).rename("ts")
        return df

    def upsert_signal(self, sig: dict, state: str, msg_id: int | None = None):
        with self.lock:
            self.db.execute("""INSERT INTO signals VALUES (?,?,?,?,?,?,?)
                               ON CONFLICT(id) DO UPDATE SET state=excluded.state, payload=excluded.payload,
                               msg_id=COALESCE(excluded.msg_id, signals.msg_id), updated=excluded.updated""",
                            (sig["id"], sig["created"], sig["symbol"], state, json.dumps(sig, default=str), msg_id,
                             sig.get("updated", sig["created"])))
            self.db.commit()

    def get(self, k: str, default=None):
        with self.lock:
            row = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, k: str, v) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, json.dumps(v)))
            self.db.commit()

    def event(self, signal_id: str, ts: int, state: str, price: float | None, note: str = ""):
        with self.lock:
            self.db.execute("INSERT INTO events VALUES (?,?,?,?,?)", (signal_id, ts, state, price, note))
            self.db.commit()

    def signals(self, limit: int = 500, open_only: bool = False) -> list[dict]:
        q = "SELECT payload, state, msg_id FROM signals"
        q += " WHERE state NOT IN ('TP','SL','BE','TRAIL','TIME')" if open_only else ""
        q += " ORDER BY created DESC LIMIT ?"
        with self.lock:
            rows = self.db.execute(q, (limit,)).fetchall()
        out = []
        for payload, state, msg_id in rows:
            d = json.loads(payload)
            d["state"], d["msg_id"] = state, msg_id
            out.append(d)
        return out

    def events(self, signal_id: str) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT ts, state, price, note FROM events WHERE signal_id=? ORDER BY ts",
                                   (signal_id,)).fetchall()
        return [{"ts": r[0], "state": r[1], "price": r[2], "note": r[3]} for r in rows]

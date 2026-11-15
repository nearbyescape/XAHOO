"""SQLite store for forecasts and their outcomes (the scoreboard)."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, due INTEGER, sym TEXT, h TEXT, p REAL, price REAL,
  u68 REAL, sig REAL, outcome INTEGER, ret REAL, model TEXT);
CREATE INDEX IF NOT EXISTS ix_due ON forecasts (outcome, due);
CREATE INDEX IF NOT EXISTS ix_sym ON forecasts (sym, h, ts);
"""
BINS = [0.0, 0.40, 0.45, 0.48, 0.52, 0.55, 0.60, 1.0001]
BIN_LABELS = ["<40", "40-45", "45-48", "48-52", "52-55", "55-60", ">60"]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def add(self, rows: list[tuple]) -> None:
        """rows: (ts, due, sym, h, p, price, u68, sig, model)"""
        with self.lock:
            self.db.executemany("INSERT INTO forecasts (ts, due, sym, h, p, price, u68, sig, model) VALUES (?,?,?,?,?,?,?,?,?)", rows)
            self.db.commit()

    def due(self, now: int) -> list[tuple]:
        with self.lock:
            return self.db.execute("SELECT id, sym, h, p, price, due FROM forecasts WHERE outcome IS NULL AND due <= ? "
                                   "ORDER BY due LIMIT 5000", (now,)).fetchall()

    def resolve(self, rows: list[tuple]) -> None:
        """rows: (outcome, ret, id). outcome 1 = up, 0 = down, -1 = unchanged / no price."""
        with self.lock:
            self.db.executemany("UPDATE forecasts SET outcome=?, ret=? WHERE id=?", rows)
            self.db.commit()

    def recent(self, limit: int = 60) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT ts, due, sym, h, p, outcome, ret FROM forecasts WHERE outcome IS NOT NULL "
                                   "AND outcome >= 0 ORDER BY due DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(("ts", "due", "sym", "h", "p", "outcome", "ret"), r)) for r in rows]

    def scoreboard(self, since: int = 0, sym: str | None = None) -> dict:
        """Calibration and hit rate per horizon from resolved forecasts."""
        q = "SELECT h, p, outcome FROM forecasts WHERE outcome >= 0 AND ts >= ?"
        args: list = [since]
        if sym:
            q += " AND sym = ?"
            args.append(sym)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        out: dict = {}
        for h, p, o in rows:
            d = out.setdefault(h, {"n": 0, "hits": 0, "brier": 0.0, "conf_n": 0, "conf_hits": 0,
                                   "bins": [[0, 0.0, 0] for _ in BIN_LABELS]})
            d["n"] += 1
            hit = int((p > 0.5) == (o == 1))
            d["hits"] += hit
            d["brier"] += (p - o) ** 2
            if p >= 0.55 or p <= 0.45:
                d["conf_n"] += 1
                d["conf_hits"] += hit
            for i in range(len(BIN_LABELS)):
                if BINS[i] <= p < BINS[i + 1]:
                    b = d["bins"][i]
                    b[0] += 1
                    b[1] += p
                    b[2] += o
                    break
        for h, d in out.items():
            n = d["n"]
            d["hit_rate"] = d["hits"] / n if n else None
            d["brier"] = d["brier"] / n if n else None
            d["conf_hit_rate"] = d["conf_hits"] / d["conf_n"] if d["conf_n"] else None
            d["bins"] = [{"label": BIN_LABELS[i], "n": b[0], "predicted": b[1] / b[0] if b[0] else None,
                          "actual": b[2] / b[0] if b[0] else None} for i, b in enumerate(d["bins"])]
        return out

    def prune(self, keep_days: int = 60) -> None:
        with self.lock:
            self.db.execute("DELETE FROM forecasts WHERE ts < ?", (int(time.time()) - keep_days * 86400,))
            self.db.commit()

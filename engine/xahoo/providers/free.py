"""Free real-time quote sources for XAUUSD / XAGUSD (no API key).

Primary : Swissquote public quote feed (bank-operated; live bid/ask with millisecond timestamps).
Fallback: gold-api.com (mid price only; spread assumed from SymbolSpec).
Both are polled; neither is an official market-data product, so the runner checks staleness and
the UI shows feed health. For execution prices always rely on your own broker.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from ..config import SYMBOLS

UA = {"User-Agent": "Mozilla/5.0 (XAHOO private terminal)"}
SQ = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{b}/{q}"
GA = "https://api.gold-api.com/price/{b}"


@dataclass
class Quote:
    symbol: str
    ts: float      # epoch seconds
    bid: float
    ask: float
    source: str


class FreeFeed:
    def __init__(self, timeout: float = 6.0):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.timeout = timeout
        self.errors: dict[str, int] = {}

    def _swissquote(self, sym: str) -> Quote:
        r = self.s.get(SQ.format(b=sym[:3], q=sym[3:]), timeout=self.timeout)
        r.raise_for_status()
        best = None
        for venue in r.json():
            for pr in venue.get("spreadProfilePrices", []):
                if pr.get("bid") and pr.get("ask") and (best is None or pr["ask"] - pr["bid"] < best[2] - best[1]):
                    best = (venue["ts"] / 1000.0, float(pr["bid"]), float(pr["ask"]))
        if best is None:
            raise ValueError("no prices")
        return Quote(sym, best[0], best[1], best[2], "swissquote")

    def _goldapi(self, sym: str) -> Quote:
        r = self.s.get(GA.format(b=sym[:3]), timeout=self.timeout)
        r.raise_for_status()
        mid = float(r.json()["price"])
        half = SYMBOLS[sym].spread / 2
        return Quote(sym, time.time(), mid - half, mid + half, "gold-api")

    def quote(self, sym: str) -> Quote | None:
        for name, fn in (("swissquote", self._swissquote), ("gold-api", self._goldapi)):
            try:
                q = fn(sym)
                self.errors[name] = 0
                return q
            except Exception:  # noqa: BLE001 - any feed failure falls through to the next source
                self.errors[name] = self.errors.get(name, 0) + 1
        return None

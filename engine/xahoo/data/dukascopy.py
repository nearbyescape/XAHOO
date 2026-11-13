"""Dukascopy historical 1-minute candle downloader / loader.

Dukascopy publishes free BID/ASK 1m candles per day at
  https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1:02}/{DD}/BID_candles_min_1.bi5
Each file is LZMA-compressed; records are 24 bytes big-endian:
  int32 seconds-from-day-start, int32 open, int32 close, int32 low, int32 high, float32 volume
Prices are integers scaled by the symbol's point divisor.

Used for backtesting only. Live data comes through a provider (see providers/).
"""
from __future__ import annotations

import lzma
import struct
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://datafeed.dukascopy.com/datafeed"
DIVISOR = {"XAUUSD": 1000.0, "XAGUSD": 1000.0, "USATECHIDXUSD": 1000.0, "USA30IDXUSD": 1000.0, "EURUSD": 100000.0}
REC = struct.Struct(">5if")


def _url(symbol: str, d: date, side: str) -> str:
    return f"{BASE}/{symbol}/{d.year}/{d.month - 1:02d}/{d.day:02d}/{side}_candles_min_1.bi5"


def decode(raw: bytes, symbol: str, d: date) -> pd.DataFrame:
    cols = ["ts", "open", "high", "low", "close", "volume"]
    if not raw:
        return pd.DataFrame(columns=cols)
    buf = lzma.decompress(raw)
    n = len(buf) // REC.size
    arr = np.frombuffer(buf[: n * REC.size], dtype=np.dtype([
        ("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")]))
    div = DIVISOR[symbol]
    day0 = pd.Timestamp(datetime(d.year, d.month, d.day, tzinfo=timezone.utc))
    df = pd.DataFrame({
        "ts": day0 + pd.to_timedelta(arr["t"].astype(np.int64), unit="s"),
        "open": arr["o"] / div, "high": arr["h"] / div, "low": arr["l"] / div,
        "close": arr["c"] / div, "volume": arr["v"].astype(float),
    })
    # Dukascopy fills closed-market minutes with flat zero-volume candles; drop them.
    return df[df["volume"] > 0].reset_index(drop=True)


def fetch_day(symbol: str, d: date, side: str = "BID", session: requests.Session | None = None,
              retries: int = 6, pause: float = 2.5) -> bytes:
    s = session or requests.Session()
    delay = pause
    last = None
    for _ in range(retries):
        try:
            r = s.get(_url(symbol, d, side), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            last = r.status_code
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return b""
        except requests.RequestException as e:  # timeouts / resets: back off and retry
            last = type(e).__name__
        time.sleep(delay)
        delay = min(delay * 2, 60)
    raise RuntimeError(f"dukascopy: failed {symbol} {d} after {retries} tries (last {last})")


def download(symbol: str, start: date, end: date, cache_dir: Path, pause: float = 2.5,
             log=print) -> None:
    """Download each day into cache_dir/{symbol}/{YYYY-MM-DD}.bi5 (skips already cached days)."""
    out = cache_dir / symbol
    out.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    d = start
    while d <= end:
        f = out / f"{d.isoformat()}.bi5"
        if d.weekday() != 5 and not f.exists():  # Saturday: market closed
            try:
                raw = fetch_day(symbol, d, session=s, retries=4, pause=pause * 2)
                f.write_bytes(raw)
                log(f"{symbol} {d} {len(raw)}B")
            except RuntimeError as e:   # leave the gap; the next pass fills it
                log(f"skip {e}")
                s = requests.Session()
            time.sleep(pause)
        d += timedelta(days=1)


def load(symbol: str, cache_dir: Path, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Load cached days into one UTC-indexed 1m OHLCV frame."""
    frames = []
    for f in sorted((cache_dir / symbol).glob("*.bi5")):
        d = date.fromisoformat(f.stem)
        if (start and d < start) or (end and d > end):
            continue
        frames.append(decode(f.read_bytes(), symbol, d))
    if not frames:
        raise FileNotFoundError(f"no cached data for {symbol} in {cache_dir}")
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ts").set_index("ts").sort_index()
    return df

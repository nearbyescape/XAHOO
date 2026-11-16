"""Extra inputs for the accuracy work: Binance SPOT 1m klines (8 coins) and the futures PREMIUM INDEX 1m klines
(all 10 markets), from data.binance.vision. Written to data/binance/{SYM}_spot.parquet and {SYM}_prem.parquet.

Spot archive timestamps switched from milliseconds to microseconds on 2025-01-01; both are handled.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download import COINS, END, KCOLS, METALS, OUT, START, days, fetch_csv, months  # noqa: E402

SPOT = "https://data.binance.vision/data/spot"
UM = "https://data.binance.vision/data/futures/um"


def _ts(s: pd.Series) -> pd.DatetimeIndex:
    v = s.astype("int64")
    v = v.where(v < 10**14, v // 1000)            # microseconds -> milliseconds
    return pd.to_datetime(v, unit="ms", utc=True)


def get(urls):
    with ThreadPoolExecutor(8) as ex:
        return [p for p in ex.map(lambda u: fetch_csv(u, KCOLS), urls) if p is not None]


def spot(sym: str):
    f = OUT / f"{sym}_spot.parquet"
    if f.exists():
        return
    parts = get([f"{SPOT}/monthly/klines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip" for y, m in months(START, END)])
    df = pd.concat(parts, ignore_index=True)
    df.index = _ts(df["open_time"])
    df = df[["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]].astype("float64")
    df = df[~df.index.duplicated()].sort_index()
    df.to_parquet(f)
    print(f"{sym} spot: {len(df):,} rows {df.index[0]} → {df.index[-1]}", flush=True)


def premium(sym: str, start: date):
    f = OUT / f"{sym}_prem.parquet"
    if f.exists():
        return
    urls = [f"{UM}/monthly/premiumIndexKlines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip" for y, m in months(start, END)]
    if start.day > 1:
        last = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        urls += [f"{UM}/daily/premiumIndexKlines/{sym}/1m/{sym}-1m-{d.isoformat()}.zip" for d in days(start, last) if d < last]
    parts = get(urls)
    df = pd.concat(parts, ignore_index=True)
    df.index = _ts(df["open_time"])
    df = df[["open", "high", "low", "close"]].astype("float64")
    df = df[~df.index.duplicated()].sort_index()
    df.to_parquet(f)
    print(f"{sym} premium: {len(df):,} rows {df.index[0]} → {df.index[-1]}", flush=True)


if __name__ == "__main__":
    for s in COINS:
        spot(s)
    for s in COINS:
        premium(s, START)
    for s, d in METALS.items():
        premium(s, d)

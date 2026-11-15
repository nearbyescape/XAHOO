"""Download Binance USD-M futures history from the public archive (data.binance.vision) into data/binance/.

  python research/download.py            # 1m klines, 5m positioning metrics, funding rates for all markets

Raw zips are parsed straight into Parquet (one file per symbol and dataset). Zips are treated as data: only the
CSV member is read in memory, nothing is extracted to disk.
"""
from __future__ import annotations

import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://data.binance.vision/data/futures/um"
OUT = Path(__file__).resolve().parents[1] / "data" / "binance"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
METALS = {"XAUUSDT": date(2025, 12, 11), "XAGUSDT": date(2026, 1, 7)}
START, END = date(2022, 1, 1), date(2026, 10, 31)
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
         "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
_s = requests.Session()
_s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=3))


def fetch_csv(url: str, header_names=None) -> pd.DataFrame | None:
    r = _s.get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        raw = z.read(z.namelist()[0])
    first = raw[:200].split(b"\n", 1)[0]
    has_header = not first[:1].isdigit()
    return pd.read_csv(io.BytesIO(raw), header=0 if has_header else None, names=None if has_header else header_names)


def months(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def klines(sym: str, start: date):
    f = OUT / f"{sym}_1m.parquet"
    if f.exists():
        return
    urls = [f"{BASE}/monthly/klines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip" for y, m in months(start, END)]
    with ThreadPoolExecutor(8) as ex:
        parts = [p for p in ex.map(lambda u: fetch_csv(u, KCOLS), urls) if p is not None]
    if not parts and start.day > 1:
        pass
    # a market listed mid-month has no monthly file for its first month: fill with daily files
    first_month_end = (date(start.year + (start.month == 12), start.month % 12 + 1, 1) - timedelta(days=1))
    if start.day > 1:
        durls = [f"{BASE}/daily/klines/{sym}/1m/{sym}-1m-{d.isoformat()}.zip" for d in days(start, first_month_end)]
        with ThreadPoolExecutor(8) as ex:
            parts = [p for p in ex.map(lambda u: fetch_csv(u, KCOLS), durls) if p is not None] + parts
    df = pd.concat(parts, ignore_index=True)
    df = df[["open_time", "open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume"]]
    df = df.drop_duplicates("open_time").sort_values("open_time")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").astype("float64")
    df.to_parquet(f)
    print(f"{sym} klines 1m: {len(df):,} rows {df.index[0]} → {df.index[-1]}", flush=True)


def mark(sym: str, start: date):
    """1m mark-price closes (the forecast target: free of bid/ask bounce)."""
    f = OUT / f"{sym}_mark.parquet"
    if f.exists():
        return
    urls = [f"{BASE}/monthly/markPriceKlines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip" for y, m in months(start, END)]
    with ThreadPoolExecutor(8) as ex:
        parts = [p for p in ex.map(lambda u: fetch_csv(u, KCOLS), urls) if p is not None]
    if start.day > 1:
        first_month_end = (date(start.year + (start.month == 12), start.month % 12 + 1, 1) - timedelta(days=1))
        durls = [f"{BASE}/daily/markPriceKlines/{sym}/1m/{sym}-1m-{d.isoformat()}.zip" for d in days(start, first_month_end)]
        with ThreadPoolExecutor(8) as ex:
            parts = [p for p in ex.map(lambda u: fetch_csv(u, KCOLS), durls) if p is not None] + parts
    df = pd.concat(parts, ignore_index=True)[["open_time", "close"]].drop_duplicates("open_time").sort_values("open_time")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").astype("float64").rename(columns={"close": "mark"})
    df.to_parquet(f)
    print(f"{sym} mark 1m: {len(df):,} rows", flush=True)


def metrics(sym: str, start: date):
    f = OUT / f"{sym}_metrics.parquet"
    if f.exists():
        return
    urls = [f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{d.isoformat()}.zip" for d in days(start, END)]
    with ThreadPoolExecutor(24) as ex:
        parts = [p for p in ex.map(fetch_csv, urls) if p is not None]
    df = pd.concat(parts, ignore_index=True)
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.drop(columns=["symbol"]).drop_duplicates("create_time").sort_values("create_time").set_index("create_time")
    df.columns = ["oi", "oi_value", "top_ls_acct", "top_ls_pos", "ls_acct", "taker_ratio"]
    df.astype("float64").to_parquet(f)
    print(f"{sym} metrics 5m: {len(df):,} rows ({len(parts)}/{len(urls)} days)", flush=True)


def funding(sym: str, start: date):
    f = OUT / f"{sym}_funding.parquet"
    if f.exists():
        return
    urls = [f"{BASE}/monthly/fundingRate/{sym}/{sym}-fundingRate-{y}-{m:02d}.zip" for y, m in months(start, END)]
    with ThreadPoolExecutor(8) as ex:
        parts = [p for p in ex.map(lambda u: fetch_csv(u, ["calc_time", "funding_interval_hours", "last_funding_rate"]), urls)
                 if p is not None]
    if not parts:
        print(f"{sym} funding: none", flush=True)
        return
    df = pd.concat(parts, ignore_index=True)
    df["calc_time"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
    df = df.drop_duplicates("calc_time").sort_values("calc_time").set_index("calc_time")[["last_funding_rate"]]
    df.columns = ["funding"]
    df.astype("float64").to_parquet(f)
    print(f"{sym} funding: {len(df):,} rows", flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [(s, START) for s in COINS] + list(METALS.items())
    only = set(sys.argv[1:])
    for sym, start in todo:
        if only and sym not in only:
            continue
        for fn in (klines, mark, funding, metrics):
            try:
                fn(sym, start)
            except Exception as e:  # noqa: BLE001 - keep going; rerun fills gaps
                print(f"{sym} {fn.__name__} FAILED: {type(e).__name__} {e}", flush=True)
    print("DONE", flush=True)

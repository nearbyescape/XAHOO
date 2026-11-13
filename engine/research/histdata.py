"""HistData.com free 1-minute history (research-only markets for the multi-market test).

Files are monthly zips containing `YYYYMMDD HHMMSS;open;high;low;close;volume` in EST without daylight saving
(fixed UTC-5); we convert to UTC. Zips are treated as data: only the CSV member is read, nothing is extracted to disk.
usage: python research/histdata.py NSXUSD,SPXUSD,EURUSD 2025-01 2026-10
"""
from __future__ import annotations

import io
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2] / "data" / "histdata"
PAGE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{p}/{y}/{m}"
GET = "https://www.histdata.com/get.php"
UA = {"User-Agent": "Mozilla/5.0"}


def months(a: str, b: str):
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_month(s: requests.Session, pair: str, y: int, m: int | None) -> pd.DataFrame | None:
    """m=None fetches a whole past year (HistData publishes completed years as one file)."""
    url = PAGE.format(p=pair.lower(), y=y, m=m) if m else PAGE.format(p=pair.lower(), y=y, m="").rstrip("/")
    page = s.get(url, timeout=30).text
    tk = re.search(r'name="tk" id="tk" value="([^"]+)"', page)
    if not tk:
        return None
    dm = f"{y}{m:02d}" if m else str(y)
    r = s.post(GET, data={"tk": tk.group(1), "date": str(y), "datemonth": dm, "platform": "ASCII",
                          "timeframe": "M1", "fxpair": pair.upper()}, headers={"Referer": url}, timeout=180)
    if r.status_code != 200 or not r.content.startswith(b"PK"):
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        raw = z.read(name).decode()
    df = pd.read_csv(io.StringIO(raw), sep=";", header=None, names=["dt", "open", "high", "low", "close", "volume"])
    ts = pd.to_datetime(df.pop("dt"), format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)   # EST (no DST) -> UTC
    df.index = ts.dt.tz_localize("UTC").rename("ts")
    df["volume"] = 1.0   # HistData has no volume; tick-count proxy so volume-based features stay defined
    return df


def download(pairs, a, b):
    s = requests.Session()
    s.headers.update(UA)
    for pair in pairs:
        out = ROOT / pair
        out.mkdir(parents=True, exist_ok=True)
        for y, m in months(a, b):
            f = out / f"{y}{m:02d}.csv.gz"
            if f.exists():
                continue
            df = None
            for _ in range(3):
                try:
                    df = fetch_month(s, pair, y, m)
                    break
                except requests.RequestException:
                    time.sleep(5)
            if df is None:
                print(pair, y, m, "not available", flush=True)
                continue
            df.to_csv(f, compression="gzip")
            print(pair, y, m, len(df), "bars", flush=True)
            time.sleep(1.5)


def load(pair: str, start=None, end=None) -> pd.DataFrame:
    files = sorted((ROOT / pair).glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(pair)
    df = pd.concat(pd.read_csv(f, index_col=0, parse_dates=True) for f in files).sort_index()
    df = df[~df.index.duplicated()]
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    return df


def download_year(pairs, y: int):
    s = requests.Session()
    s.headers.update(UA)
    for pair in pairs:
        f = ROOT / pair / f"{y}.csv.gz"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            continue
        df = fetch_month(s, pair, y, None)
        print(pair, y, "year", "not available" if df is None else f"{len(df)} bars", flush=True)
        if df is not None:
            df.to_csv(f, compression="gzip")


if __name__ == "__main__":
    if sys.argv[2] == "year":
        download_year(sys.argv[1].split(","), int(sys.argv[3]))
    else:
        download(sys.argv[1].split(","), sys.argv[2], sys.argv[3])

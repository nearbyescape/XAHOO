"""Build higher timeframes from 1m candles and align them without look-ahead."""
from __future__ import annotations

import pandas as pd

from ..config import TF_MINUTES

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample 1m OHLCV (index = bar open time, UTC) to `tf`.

    The 4h bars are anchored at 00:00 UTC (00,04,08,12,16,20), as on most MT5 servers.
    Adds `close_time` = open time + tf, the moment the bar becomes final.
    """
    if tf == "1m":
        out = m1.copy()
    else:
        out = m1.resample(f"{TF_MINUTES[tf]}min", label="left", closed="left").agg(AGG).dropna(subset=["open"])
    out["close_time"] = out.index + pd.Timedelta(minutes=TF_MINUTES[tf])
    return out


def align_closed(htf: pd.DataFrame, at: pd.Series, cols: list[str], prefix: str) -> pd.DataFrame:
    """For each timestamp in `at`, take the latest `htf` row whose close_time <= that timestamp.

    This guarantees a 5m signal at 10:05 only sees the 1h bar that closed at 10:00,
    never the still-forming 10:00-11:00 bar.
    """
    left = pd.DataFrame({"_t": pd.DatetimeIndex(at)}, index=at.index)
    right = htf[["close_time", *cols]].rename(columns={c: f"{prefix}{c}" for c in cols})
    right = right.sort_values("close_time")
    merged = pd.merge_asof(left.sort_values("_t"), right, left_on="_t", right_on="close_time", direction="backward")
    merged.index = left.sort_values("_t").index
    return merged.drop(columns=["_t", "close_time"]).reindex(at.index)

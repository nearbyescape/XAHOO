"""Build the feature table and forecast targets for every market → data/features/{SYM}.parquet

Targets use the MARK price (free of bid/ask bounce): y_{h} = log(mark[t+h] / mark[t]) for each horizon,
where t is the close of the bar. Features use only data up to that close."""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from xahoo.features import HORIZONS, build, leader_of   # noqa: E402

BN, OUT = ROOT / "data" / "binance", ROOT / "data" / "features"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "XAUUSDT", "XAGUSDT"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for sym in sys.argv[1:] or SYMS:
        t0 = time.time()
        k = pd.read_parquet(BN / f"{sym}_1m.parquet")
        f = build(k, pd.read_parquet(BN / f"{sym}_metrics.parquet"), pd.read_parquet(BN / f"{sym}_funding.parquet"),
                  pd.read_parquet(BN / f"{leader_of(sym)}_1m.parquet"))
        mark = pd.read_parquet(BN / f"{sym}_mark.parquet")["mark"]
        lm = np.log(mark.reindex(k.index))
        for name, h in HORIZONS.items():
            fut = np.log(mark.reindex(k.index + pd.Timedelta(minutes=h))).to_numpy()
            f[f"y_{name}"] = (fut - lm.to_numpy()).astype("float32")
        r1 = np.log(k["close"]).diff()
        f["sig1d"] = r1.rolling(1440, min_periods=360).std().astype("float32")   # for the range model
        f = f.iloc[10080:]                                                        # 7-day warm-up
        f.to_parquet(OUT / f"{sym}.parquet")
        nan = f.filter(regex="^[abcd]_").isna().mean().sort_values(ascending=False).head(3).round(3).to_dict()
        print(f"{sym}: {len(f):,} rows × {f.shape[1]} cols in {time.time() - t0:.0f}s | most-missing {nan}", flush=True)


if __name__ == "__main__":
    main()

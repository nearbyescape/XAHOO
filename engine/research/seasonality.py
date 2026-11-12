"""Time-of-day drift in gold/silver: mean 1h return by UTC hour, per year. Real effects must repeat across years."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xahoo.data import dukascopy
CACHE = Path(__file__).resolve().parents[2] / "data" / "dukascopy"
years = [int(y) for y in sys.argv[1:]] or [2025, 2026]
pd.set_option("display.width", 250)
for sym in ("XAUUSD", "XAGUSD"):
    m1 = dukascopy.load(sym, CACHE)
    h = m1["close"].resample("1h").last().dropna()
    r = np.log(h).diff().dropna() * 1e4          # basis points per hour
    r = r[r.abs() < 300]                         # drop weekend-gap hours
    df = pd.DataFrame({"r": r, "hour": r.index.hour - 1, "year": r.index.year})   # hour the move happened in
    df.loc[df.hour < 0, "hour"] = 23
    out = {}
    for y in years:
        d = df[df.year == y].groupby("hour")["r"]
        out[(y, "bp")] = d.mean().round(2)
        out[(y, "t")] = (d.mean() / (d.std() / np.sqrt(d.count()))).round(1)
        out[(y, "up%")] = (d.apply(lambda x: (x > 0).mean() * 100)).round(0)
    t = pd.DataFrame(out)
    t.index = [f"{h:02d}-{h+1:02d} UTC ({(h*60+330)//60%24:02d}:{(330%60):02d} IST)" for h in t.index]
    print(f"\n=== {sym}: mean move per hour (basis points), t-stat, % of hours up ===")
    print(t.to_string())

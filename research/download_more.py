"""Eight more liquid coins for training only (never shown on screen): klines, mark, metrics, funding.
  python research/download_more.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import download as d  # noqa: E402

MORE = ["LTCUSDT", "BCHUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "ATOMUSDT", "ETCUSDT", "NEARUSDT"]

if __name__ == "__main__":
    for s in MORE:
        for fn in (d.klines, d.mark, d.metrics, d.funding):
            try:
                fn(s, d.START)
            except Exception as e:  # noqa: BLE001
                print(s, fn.__name__, "failed:", e, flush=True)

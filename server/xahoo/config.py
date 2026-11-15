"""Markets, horizons and runtime settings."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = Path(os.environ.get("XAHOO_MODELS", ROOT / "models"))
DATA = Path(os.environ.get("XAHOO_DATA", ROOT / "data"))
WEB = ROOT / "web" / "dist"

MARKETS = [
    {"sym": "BTCUSDT", "name": "Bitcoin", "short": "BTC", "kind": "coin", "digits": 1},
    {"sym": "ETHUSDT", "name": "Ethereum", "short": "ETH", "kind": "coin", "digits": 2},
    {"sym": "SOLUSDT", "name": "Solana", "short": "SOL", "kind": "coin", "digits": 2},
    {"sym": "XRPUSDT", "name": "XRP", "short": "XRP", "kind": "coin", "digits": 4},
    {"sym": "BNBUSDT", "name": "BNB", "short": "BNB", "kind": "coin", "digits": 2},
    {"sym": "DOGEUSDT", "name": "Dogecoin", "short": "DOGE", "kind": "coin", "digits": 5},
    {"sym": "ADAUSDT", "name": "Cardano", "short": "ADA", "kind": "coin", "digits": 4},
    {"sym": "LINKUSDT", "name": "Chainlink", "short": "LINK", "kind": "coin", "digits": 3},
    {"sym": "XAUUSDT", "name": "Gold", "short": "XAU", "kind": "metal", "digits": 2},
    {"sym": "XAGUSDT", "name": "Silver", "short": "XAG", "kind": "metal", "digits": 3},
]
SYMS = [m["sym"] for m in MARKETS]
KIND = {m["sym"]: m["kind"] for m in MARKETS}

# How often each horizon's forecast is stored for the scoreboard (minutes). Forecasts are recomputed every minute.
STORE_EVERY = {"1m": 1, "5m": 1, "15m": 1, "1h": 5, "4h": 15, "1d": 60}
KEEP_BARS = 10_600            # 7 days of 1m bars + margin: the longest feature window
ROUND_TRIP_FEE_BP = 10.0      # typical taker fee both ways on Binance futures; below this a move is "too small to trade"

MODE = os.environ.get("XAHOO_MODE", "live").lower()          # live | replay
PASSWORD = os.environ.get("XAHOO_ADMIN_PASSWORD", "")
SECRET = os.environ.get("XAHOO_SECRET", "dev-secret-change-me").encode()
TOTP_SECRET = os.environ.get("XAHOO_TOTP_SECRET", "")
DEV = os.environ.get("XAHOO_DEV", "") == "1"

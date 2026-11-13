"""XAHOO command line.

  python -m xahoo.cli download --from 2026-07-01 --to 2026-11-11
  python -m xahoo.cli backtest --from 2026-07-01 --to 2026-11-11 [--tf 5m 15m] [--symbols XAUUSD]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import StrategyParams
from .data import dukascopy
from .engine import breakdown, run_backtest, stats

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "dukascopy"
REPORTS = ROOT / "reports"


def _load(symbols, a, b):
    return {s: dukascopy.load(s, CACHE, a, b) for s in symbols}


def cmd_download(args):
    for _ in range(3):   # repeat passes fill days skipped by throttling
        for s in args.symbols:
            dukascopy.download(s, args.start, args.end, CACHE, pause=3.0)


def cmd_backtest(args):
    p = StrategyParams.trader() if args.profile == "trader" else StrategyParams()
    p.exit_mode = getattr(args, "exit", "fixed")
    if args.tf is None:
        args.tf = list(p.exec_tfs)
    if args.min_score is not None:
        p.min_score_dashboard = args.min_score
    # Indicators need history before the test window (EMA200 on 4h ~ 33 days).
    data = _load(args.symbols, args.start - timedelta(days=args.warmup_days), args.end)
    from .engine import generate
    cand = generate(data, p, tuple(args.tf))
    if not cand.empty:
        cand = cand[cand["close_time"] >= pd.Timestamp(args.start, tz="UTC")].reset_index(drop=True)
    bt = run_backtest(data, p, tuple(args.tf), cand=cand)
    REPORTS.mkdir(exist_ok=True)
    tag = f"{args.start}_{args.end}"
    if not bt.empty:
        bt.drop(columns=["components"]).to_csv(REPORTS / f"signals_{tag}.csv", index=False)
    s = stats(bt)
    print(json.dumps({"params_version": p.version, **s}, indent=2))
    if bt.empty:
        return
    bt["hour_ist"] = (bt["close_time"] + pd.Timedelta(minutes=330)).dt.hour
    for by in (["symbol"], ["tf"], ["setup"], ["grade"], ["session"], ["symbol", "tf"]):
        print(f"\n--- by {'/'.join(by)} ---")
        print(breakdown(bt, by).to_string())
    print("\n--- by result ---")
    print(bt["result"].value_counts().to_string())


def main(argv=None):
    ap = argparse.ArgumentParser("xahoo")
    sub = ap.add_subparsers(required=True)
    for name, fn in (("download", cmd_download), ("backtest", cmd_backtest)):
        sp = sub.add_parser(name)
        sp.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
        sp.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
        sp.add_argument("--symbols", nargs="+", default=["XAUUSD", "XAGUSD"])
        sp.set_defaults(fn=fn)
        if name == "backtest":
            sp.add_argument("--tf", nargs="+", default=None)
            sp.add_argument("--profile", choices=["trader", "v1"], default="trader")
            sp.add_argument("--exit", choices=["fixed", "trail_ema"], default="fixed")
            sp.add_argument("--min-score", type=int, default=None)
            sp.add_argument("--warmup-days", type=int, default=40)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

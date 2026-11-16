# XAHOO

Private, terminal-style screen showing **direction probabilities** for 10 markets on Binance futures
(BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK, gold, silver) over six horizons: 1m · 5m · 15m · 1h · 4h · 1d.

**Focus view** (default, made for a big screen): market list on the left; a large chart of the selected
market with support/resistance zones, 24h buyer/seller volume by price, order-book walls, big-trade bubbles,
buy-minus-sell volume bars and the expected-range cone; on the right the probability for the chosen horizon
with its tested accuracy, the plain-language reasons behind it, key levels with reach chances, and the strong
buyers and sellers right now; an all-markets table and the live track record along the bottom. Auto-cycle
moves through the markets every 20 seconds for a wall screen. Direction is shown with arrows that tilt from
→ (balanced) to ↑ / ↓ as the probability leans.

**Grid view**: each market card shows: a direction dial (15m–4h blend, plus a 1–5 minute needle), live price with the
nearest support and resistance, the six-horizon probability ladder with expected moves, where price sits
between support and resistance with the measured chance of reaching each, and live taker buy/sell flow.
Click a card for the chart with the 68%/95% projection cone and levels, the reasons behind the forecast,
positioning, liquidations and the market's live track record.

- Plan: [docs/PLAN_PROBABILITY_TERMINAL.md](docs/PLAN_PROBABILITY_TERMINAL.md)
- Research results: [docs/RESEARCH.md](docs/RESEARCH.md)
- Deploy on the VPS: [docs/DEPLOY.md](docs/DEPLOY.md)

Layout: `research/` (data download, features, walk-forward tests), `models/` (trained models, calibration,
level tables), `server/` (FastAPI + live Binance engine, tests), `web/` (Svelte screen).

Local run with archived data: `cd server && XAHOO_MODE=replay XAHOO_ADMIN_PASSWORD=… python -m uvicorn xahoo.app:app`
(needs `research/download.py` data); tests: `cd server && python -m pytest`.

> Probabilities are measured frequencies from history, not advice. Trading involves substantial risk of loss.

## Previous version
The earlier signal terminal (scalping and swing research, dashboard, deploy files, backtest log) was removed on
2026-11-15. It is preserved in this repository's history at commit `33e7d6f`:
`git checkout 33e7d6f` (or `git show 33e7d6f:docs/BACKTEST.md` for the 22 backtest runs).

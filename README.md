# XAHOO

Private terminal-style signal engine for Gold (XAUUSD) and Silver (XAGUSD) scalping:
5m/15m entries with 1h/4h bias (EMA 12 / EMA 200 + liquidity, FVG, range setups), dashboard + Telegram delivery.

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Backtest results: [docs/BACKTEST.md](docs/BACKTEST.md)

## Run it

```bash
cd engine
pip install -r requirements.txt fastapi uvicorn
python -m xahoo.cli download --from 2026-07-01 --to 2026-11-11     # Dukascopy history (throttled, ~10s/day)
python -m xahoo.cli backtest --from 2026-10-01 --to 2026-10-31 --symbols XAUUSD
python -m pytest -q
XAHOO_ADMIN_PASSWORD=change-me uvicorn xahoo.api:app --port 8000   # terminal UI at http://localhost:8000
```

Shortcuts in the UI: `Ctrl+K` command bar (`xau`, `xag`, `5m`, `signals`, `theme`…), `F1`–`F4` switch views, `Esc` closes panels.

Telegram: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (delivery module: `engine/xahoo/telegram.py`).

## Live mode (free feed)

```bash
cd engine && XAHOO_MODE=live uvicorn xahoo.api:app --port 8000     # or: docker compose up -d  (see .env.example)
```

- Prices: Swissquote public quotes (bid/ask, polled every 2 s), fallback gold-api.com. Free, no key, not an official
  market-data product; the header shows feed health. Execution prices are your broker's: **gold spread must be ≤ ~$0.30–0.40**
  for this strategy (docs/BACKTEST.md, spread test).
- Strategy: `StrategyParams.trader()` — impulse → EMA12 pullback → breakdown close on 5m, daily-trend filter, lot 2 added at
  EMA12, target 2R, stop to average entry at +1R. Same code as the backtests (parity test in `engine/tests/test_live.py`).
- Signals start after ~2.5 h of continuous live candles ("warming up"). History: Dukascopy daily files, refreshed hourly.
- **Pre-alerts:** when the impulse is done and the pullback has reached the EMA12, Telegram gets "GET READY" with the exact
  trigger level (~5–6/day; ~1 in 5 becomes a signal; 95% of signals get one, ~10 min ahead). The signal is sent as a reply to
  its pre-alert; expired setups get a "cancelled" reply. `XAHOO_PREALERTS=off` silences Telegram (dashboard still shows them).
- **News tag:** signals within 90 min after a detected US-news spike are marked 📰 (3–6× better avg R in 2024–26, few trades).
- **Strategy stop rules** (`engine/xahoo/live/guard.py`): day stop at −2R · half size at 10R drawdown · pause at 20R drawdown or
  when the live average is statistically below the backtest's. Resume from the dashboard header.
- Needs to run 24/5 on an always-on machine (small VPS). This repo's cloud session is temporary.
> Signals are for personal analysis only. Not financial advice.

## Private app (desktop + mobile)

- **Private:** every page, file and API call needs the owner's login (30-day signed session; optional 2-step code;
  lockout after 5 wrong tries). Search engines are blocked three ways (robots.txt, `X-Robots-Tag`, `<meta robots>`),
  no third-party requests (fonts and chart library are self-hosted), no referrers, no embedding. Live mode won't start
  without `XAHOO_ADMIN_PASSWORD`.
- **Install:** XAHOO is an installable app (PWA). Desktop Chrome/Edge: **⬇ APP** in the header or the install icon in
  the address bar. Android: menu → *Install app*. iPhone/iPad: Safari → Share → *Add to Home Screen*. No app store.
- **Alerts:** 🔔 bell with unread count and alert list, pop-up toasts with sound, and **device notifications even when
  the app is closed** (tap 🔕 → allow). Pushes carry no content: the app fetches the alert from your own server,
  so signal details never pass through Google/Apple push servers. iPhone needs iOS 16.4+ and the home-screen app.
- **Deploy:** `docker compose up -d` (XAHOO + Caddy automatic HTTPS). HTTPS is required for installing on phones and
  for push. See `.env.example`.

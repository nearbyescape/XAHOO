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

> The UI currently runs in **REPLAY** mode over downloaded history. Live mode needs a real-time price feed (see PLAN §6.1).
> Signals are for personal analysis only. Not financial advice.

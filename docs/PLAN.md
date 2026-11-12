# XAHOO — Gold & Silver Scalp Signal Terminal

**Status:** Phase 1–2 built (engine, backtester, terminal UI prototype). **Current rules show no proven edge — see [BACKTEST.md](BACKTEST.md); not for real-money use.** Next: [PLAN_V2_HIGH_WINRATE.md](PLAN_V2_HIGH_WINRATE.md) · **Owner:** single admin (private) · **Instruments:** XAUUSD, XAGUSD
**Execution timeframes:** 1m · 5m · 15m · **Context timeframes:** 1h · 4h

---

## 0. Reality check (read first)

These points shape the plan. They are here so the system stays honest with its only user.

1. **What the research actually covered.** I pulled the channel's video and live-stream list, the public descriptions, and his public Telegram channel (`t.me/s/thetraderamitgupta`). I could **not** read the video transcripts or watch the streams: the transcript download was blocked in this session. So the rule set in §2 is built from:
   - your own observation: **12 EMA + 200 EMA**,
   - the topics he teaches (titles below),
   - what his Telegram shows about how he manages trades,
   - and standard definitions of those methods.
   Every rule marked **[CONFIRM]** needs your check against his live streams before we lock it in (see §11).

2. **What he teaches** (exact titles from the channel):
   - "The Only Trading Strategy You'll Ever Need 🔥 | Range Strategy"
   - "Forex Technical Analysis in Hindi | Liquidity, BOS, CHoCH, FVG & Order Block | Part 4"
   - "All Major Chart Patterns Explained in Hindi 🔥 | Complete Forex Trading Guide"
   - "Candlestick Trading Full Course | Candlestick Free Masterclass"
   - "BANK-NIFTY • Fibonacci strategy masterclass"
   - Daily: "Live Crypto & Gold Analysis || <date>" (≈ 80-minute sessions)

   From his Telegram: live sessions at **1 PM and 9 PM IST** (the London and New York sessions), "**trail your SL at cost to cost**" (move the stop to breakeven early), and "**never risk more than 1% per trade**".

3. **About 9 wins out of 10.** One week of trades is too few to measure accuracy. His channel makes money from broker referrals: the VIP group requires an account opened through his XM or Exness referral link plus a $100 deposit, and posts like "10k$ to 25k$ in just a week" are marketing. That doesn't make his analysis bad. It does mean the winning trades get shown more than the losing ones. A high hit rate usually comes from **taking quick first targets and moving the stop to breakeven**. That's a real technique, but it trades size of win for frequency of win. **XAHOO will measure its own win rate, expectancy and drawdown on every signal and never assume one.** The goal is *positive expectancy*, not a number promised in advance.

4. **Regulatory note (India).** Under FEMA, Indian residents may only trade forex/commodity derivatives on authorised exchanges/brokers. The **RBI Alert List** names offshore platforms that are not authorised. **Check where your broker (e.g. XM, Exness) stands before trading real money.** XAHOO is a signal tool and does not place trades. It is built so the same engine can also run on **MCX Gold/Silver futures (GOLDM, SILVERM, SILVERMIC)**, which are legal for residents. Talk to a CA or advisor about this.

---

## 1. Product overview

A private, terminal-style web app that:

- streams live XAU/XAG prices,
- runs a multi-timeframe strategy engine (1m/5m/15m triggers, 1h/4h bias),
- produces scored signals (entry, SL, TP1/TP2/TP3, R:R, confidence, the reasons behind it),
- follows each signal live to its result (TP hit / SL hit / breakeven / expired),
- pushes every event to a private Telegram channel,
- keeps a full journal with performance analytics and a backtest lab.

One admin, no public sign-up, no payments.

---

## 2. Strategy engine — "Amit-style" EMA 12/200 + SMC confluence

The engine doesn't fire on one indicator crossing. It scores **confluence** across timeframes and only sends signals that pass a minimum score.

### 2.1 Layer A — Higher-timeframe bias (4h, 1h)

| Check | Bullish bias | Bearish bias |
|---|---|---|
| Price vs 200 EMA | close > EMA200 | close < EMA200 |
| EMA200 slope (last 20 bars) | rising | falling |
| Structure | higher highs / higher lows | lower highs / lower lows |
| 12 EMA vs 200 EMA | EMA12 > EMA200 | EMA12 < EMA200 |

Result per TF: `BULL`, `BEAR` or `NEUTRAL`. **Signals only go with the 1h bias**. 4h agreement raises the score; 4h disagreement lowers it (it doesn't block the signal, because scalps can run against 4h). [CONFIRM: does he trade against 4h?]

### 2.2 Layer B — Setup timeframe (15m, 5m)

**Setup 1 — Trend pullback to 12 EMA (main setup)** [CONFIRM]
- Price stays on the bias side of EMA200 on 15m/5m.
- EMA12 is on the same side of EMA200 and pointing in the trend direction.
- Price pulls back **into or slightly through the 12 EMA** (default: within 0.3 × ATR).
- Extra points if the pullback reaches the 0.5–0.618 Fibonacci level of the last impulse, an unfilled **FVG**, or an **order block**.

**Setup 2 — 200 EMA retest** [CONFIRM]
- First pullback to EMA200 after a clean break of it, with EMA12 crossing over in the new direction.

**Setup 3 — Range strategy** (from his "Range Strategy" video) [CONFIRM details]
- Turned on when EMA12 is flat, price keeps crossing EMA200, and ADX(14) < 20 on 15m.
- Range = the last N swing high/low pair tested at least twice.
- **Fade** the range edges after a rejection candle; target the middle, then the opposite edge.
- **Breakout + retest:** a close outside the range, a retest of the broken edge, then entry in the breakout direction.

**Setup 4 — Liquidity sweep reversal (SMC)**
- Price takes out an obvious high/low (previous day's high/low, Asian session high/low, equal highs/lows), then shows a **CHoCH** on 1m/5m and returns inside the level. Used only when it agrees with the 1h bias or at a 4h level.

### 2.3 Layer C — Trigger timeframe (1m / 5m)

Entry fires only when **one** of these confirms on the trigger TF:
- an engulfing or pin-bar rejection candle at the zone (from his candlestick course),
- a micro **BOS** in the bias direction after the pullback,
- a close back above (long) / below (short) EMA12 after poking through it.

Entry types: market at the trigger close (default), or a limit order at the 12 EMA / FVG midpoint (optional).

### 2.4 Filters (block a signal)

- **Session:** only London (12:30–16:30 IST) and New York (18:00–22:30 IST) by default; the Asian session is off (it can be turned on). These match his 1 PM / 9 PM live times.
- **News blackout:** ±15 min around high-impact USD events (CPI, NFP, FOMC, PCE, GDP, Fed speakers). Source: economic-calendar API.
- **Spread filter:** XAU spread > configured max (e.g. 35 points), XAG spread > max.
- **Volatility:** ATR(14) on 5m below a floor (dead market) or above a ceiling (news spike).
- **Overextension:** price more than K × ATR away from EMA12 (don't chase).
- **Cooldown:** no new signal on the same symbol/direction within X minutes of the last one; at most N open signals per symbol.
- **Daily guard:** after 2 stop-losses in a day (setting), the engine goes quiet for that symbol.

### 2.5 Risk model (stop & targets)

- **SL:** beyond the setup's swing point / order block, plus a 0.2 × ATR buffer. Clamped to a minimum and maximum (e.g. XAU 1m/5m: $2–$8, 15m: $4–$15; XAG scaled to its ATR).
- **TP1 = 1R** → Telegram message "**Move SL to entry (cost to cost)**", matching his habit.
- **TP2 = 2R**, **TP3** = next liquidity pool / HTF level (or 3R).
- Suggested lot size in the dashboard from account size × risk % (default 1%) ÷ SL distance.
- **Win definition stored separately:** "TP1 hit" vs "closed in profit" vs "R-multiple". This keeps the stats honest about BE-protected trades.

### 2.6 Confidence score (0–100)

| Factor | Weight |
|---|---|
| 1h bias agrees | 20 |
| 4h bias agrees | 10 |
| Setup quality (clean pullback, slope) | 15 |
| Fib 0.5–0.618 / FVG / OB confluence | 15 |
| Trigger candle strength | 10 |
| Session quality (London/NY overlap highest) | 10 |
| Liquidity swept before entry | 10 |
| XAU/XAG agree (both same bias) | 5 |
| DXY inverse confirmation (optional feed) | 5 |

Grades: **A+ ≥ 85**, **A 75–84**, **B 65–74** (dashboard only, no Telegram), below 65 is dropped. Weights are settings, and the backtest lab will tune them.

### 2.7 Silver-specific handling
- Silver moves differently: higher volatility per dollar and wider spreads, so all distances use **ATR-based** settings per symbol, not fixed values.
- The gold/silver ratio and XAU direction act as a filter for XAG signals.

---

## 3. Signal lifecycle

```
SCANNING → SETUP_FORMING → ARMED (zone reached) → TRIGGERED (signal sent)
   → TP1_HIT (SL→BE) → TP2_HIT → TP3_HIT / CLOSED_BE / SL_HIT
   → or EXPIRED / INVALIDATED (setup broke before trigger)
```

- `SETUP_FORMING` and `ARMED` show on the dashboard as a "**watchlist**" (like "trade in 5 minutes").
- Each state change is stored with a timestamp and price, and sent to Telegram **as a reply to the original signal message**.

---

## 4. Telegram integration

- Private channel + bot (Bot API). Admin-only bot commands.
- **Signal message:**
  ```
  🟢 XAUUSD BUY  ·  A+ (88)  ·  5m
  Entry   2,384.50
  SL      2,380.20   (-4.30)
  TP1     2,388.80   1R
  TP2     2,393.10   2R
  TP3     2,397.00   PDH
  Bias  4h▲ 1h▲  ·  Setup: EMA12 pullback + FVG
  Session: London/NY overlap · Spread 18
  #XAU #scalp  id:SIG-20261112-014
  ```
- Follow-ups: "TP1 hit +1R — move SL to entry", "SL hit −1R", "Closed BE", "Signal invalidated".
- Optional: a chart snapshot image (server-side render) attached to each signal.
- Bot commands: `/status`, `/pause [xau|xag|all]`, `/resume`, `/today` (day's P&L in R), `/open`, `/bias`.
- Daily summary at 23:30 IST; weekly report on Saturday.

---

## 5. Web application — terminal UI

**Design:** dark trading-terminal look (Bloomberg/MT5 style). Monospace type (JetBrains Mono / IBM Plex Mono), amber/green/red on near-black, dense grids, keyboard-first (`Ctrl+K` command bar: `xau 5m`, `pause xag`, `bt last 30d`). Also a light theme. Works on desktop and phone.

### 5.1 Screens

1. **Terminal (home)**
   - Live tickers XAU / XAG: bid, ask, spread, day change, ATR.
   - **MTF matrix:** for each symbol × {1m,5m,15m,1h,4h}: bias arrow, EMA12/EMA200 distance, ADX, structure state.
   - Main chart (TradingView *Lightweight Charts*, open source): EMA12/EMA200, FVG/OB boxes, range boxes, signal markers, SL/TP lines.
   - Active signals panel with live R-multiple.
   - Watchlist (forming/armed setups).
   - Session clock (Asia / London / NY in IST) and the next high-impact news countdown.
   - Event log (scrolling, terminal-style).
2. **Signals:** a table with filters (symbol, TF, setup, grade, outcome, date) and CSV export.
3. **Signal detail:** frozen chart at signal time, confluence checklist with each factor's points, timeline of state changes, Telegram message link, and your notes and whether you took it.
4. **Analytics:** win rate (TP1, any profit, by R), expectancy, profit factor, average R, max drawdown, equity curve in R, streaks. Broken down by symbol, TF, setup, session, weekday, hour and grade. Calibration chart: does a higher score actually win more?
5. **Backtest lab:** choose a date range, symbols and settings → run on stored history → full report. Walk-forward mode. Compare two settings side by side.
6. **Strategy settings:** every setting from §2 with sensible ranges, presets ("Conservative", "Amit-style default", "Aggressive"), and version history (each signal records the settings version that made it).
7. **Risk calculator & journal:** lot size, daily loss limit tracker, your manual notes per day.
8. **Calendar:** economic events with impact level; blackout windows shown on the chart.
9. **Trader comparison (calibration tool):** you log the trader's live-stream calls (time, direction, entry, SL, TP). XAHOO checks whether the engine would have given the same signal and shows the match rate. **This is how we get closer to "his level":** we measure against his real calls and tune until they match.
10. **System health:** feed connection and latency, last tick time, worker heartbeat, Telegram delivery status, error log.

---

## 6. Architecture

```
          ┌──────────────┐    ticks     ┌──────────────────┐
 Feed ───▶│ Ingestor     │─────────────▶│ Candle builder    │──▶ TimescaleDB
 (WS)     │ (per source) │              │ 1m→5m→15m→1h→4h   │
          └──────────────┘              └─────────┬────────┘
                                                  │ bar-close events (Redis pub/sub)
                                        ┌─────────▼────────┐
                                        │ Strategy engine   │──▶ signals table
                                        │ (bias/setup/trig) │
                                        └─────────┬────────┘
                         ┌────────────────────────┼─────────────────┐
                 ┌───────▼──────┐        ┌────────▼───────┐  ┌──────▼──────┐
                 │ Signal tracker│        │ Telegram worker│  │ FastAPI +   │
                 │ (TP/SL/BE)    │        │ (queue, retry) │  │ WebSocket   │──▶ Next.js UI
                 └───────────────┘        └────────────────┘  └─────────────┘
```

| Layer | Choice | Why |
|---|---|---|
| Engine & API | **Python 3.12, FastAPI**, pandas/numpy, own indicator code (unit-tested) | Best tools for quant work; same code runs live and in backtests |
| Data store | **PostgreSQL + TimescaleDB** | Fast time-series storage for candles, plus normal tables for signals |
| Messaging | **Redis** (pub/sub + job queue) | Bar-close events, Telegram retries |
| Frontend | **Next.js + TypeScript + Tailwind**, Lightweight Charts | Fast, modern, good for a terminal-style UI |
| Telegram | `python-telegram-bot` | Mature, async |
| Deploy | Docker Compose on a VPS in **Mumbai/Bangalore** region, Caddy (auto-HTTPS) | Low latency to you; simple to run |
| Monitoring | Health page + Telegram alert on feed loss | One admin needs to know at once |

**Key rule:** the backtest and the live engine run **the same strategy code** on the same candle objects. No separate "backtest version" that can drift apart.

### 6.1 Market data (decision needed)

| Option | Real-time | History | Notes |
|---|---|---|---|
| **Your broker's MT5 feed** via a small bridge (MT5 Python API on a Windows VPS) | ✅ the exact prices you trade | limited | Best match to the prices you trade on; needs a Windows VPS |
| **Twelve Data / Finnhub / TraderMade / Polygon** (paid WS) | ✅ | ✅ | Easy; monthly cost; prices differ slightly from your broker's |
| **Dukascopy** historical tick data | ❌ | ✅ years of free tick data | Use for **backtesting** |
| **MCX** via Zerodha Kite / Upstox / Angel API | ✅ | ✅ | For the India-legal route (GOLDM/SILVERM) |

Recommendation: **Dukascopy for history + broker MT5 bridge (or Twelve Data) for live**, behind one `DataProvider` interface so we can switch later.

### 6.2 Security (single admin)
- One admin account, password (argon2) + **TOTP 2FA**, httpOnly session cookies, rate-limited login.
- Optional IP allow-list / Cloudflare Access in front.
- API keys and bot token stored in env or a secrets file, never in the repo.
- Nightly database backup to object storage.

---

## 7. Data model (core tables)

- `candles(symbol, tf, ts, o, h, l, c, v, spread)` — hypertable
- `signals(id, symbol, tf, direction, setup, grade, score, entry, sl, tp1, tp2, tp3, reasons jsonb, params_version, created_at)`
- `signal_events(signal_id, state, price, ts)`
- `signal_outcomes(signal_id, result, r_multiple, mfe, mae, duration)`
- `journal(signal_id, taken bool, actual_entry, actual_exit, notes)`
- `trader_calls(ts, symbol, direction, entry, sl, tp, source_url)` — for the comparison tool
- `strategy_params(version, json, created_at, active)`
- `news_events(ts, currency, title, impact)`
- `telegram_messages(signal_id, chat_id, message_id)`

---

## 8. Validation plan — proving it before trading real money

1. **Unit tests** for every indicator (EMA, ATR, ADX, swings, BOS/CHoCH, FVG, OB) against known values.
2. **Backtest** on 2+ years of 1m data for XAU and XAG, with realistic spread and slippage. Report results per setup.
3. **Walk-forward** test (tune on 6 months, test on the next 2) so the settings aren't just fitted to the past.
4. **Comparison test:** log ≥ 30 of the trader's live calls; measure how often the engine matches them.
5. **Paper-forward:** 3–4 weeks of live signals with no real money; Telegram on.
6. **Go-live checklist:** expectancy > 0 after costs, max drawdown within your limit, calibration chart rises with score.

---

## 9. Delivery phases

| Phase | Scope | Est. |
|---|---|---|
| **0. Lock the rules** | You confirm §2 [CONFIRM] items; choose data provider & broker/market | 2–4 days |
| **1. Data & engine core** | Ingestor, candle builder, indicators, bias + Setup 1, tests | 1–1.5 weeks |
| **2. Backtest lab (CLI first)** | Dukascopy import, backtester, reports; tune Setup 1 | 1 week |
| **3. Remaining setups** | 200 EMA retest, Range, Liquidity sweep, filters, scoring | 1–1.5 weeks |
| **4. Terminal UI** | Terminal home, signals, detail, settings, health | 1.5–2 weeks |
| **5. Telegram** | Signal + follow-up messages, commands, daily summary | 3–4 days |
| **6. Analytics & comparison tool** | Analytics screens, trader-call logging & match rate | 1 week |
| **7. Paper-forward** | 3–4 weeks live, no money; fix and tune | 3–4 weeks |
| **8. Hardening & go-live** | 2FA, backups, monitoring, VPS deploy | 3–4 days |

The engine and backtester come **before** UI polish: if the strategy has no edge, the UI doesn't matter.

---

## 10. Repository layout (planned)

```
XAHOO/
├─ docs/PLAN.md
├─ engine/            # Python: data providers, candles, indicators, setups, scoring, tracker
│  ├─ providers/      # mt5_bridge, twelvedata, dukascopy, mcx
│  ├─ indicators/
│  ├─ strategy/       # bias.py, setups/*.py, filters.py, scoring.py, risk.py
│  ├─ backtest/
│  └─ tests/
├─ api/               # FastAPI app, auth, websocket, REST
├─ bot/               # Telegram worker
├─ web/               # Next.js terminal UI
├─ deploy/            # docker-compose, Caddyfile, backup scripts
└─ .env.example
```

---

## 11. Open questions for you

1. **His exact rules.** Which timeframe does he enter on, and does he enter on the touch of EMA12 or wait for a candle close? Where does he put his SL? Does he take TP1 at 1:1? The quickest way to answer these: send **3–5 screenshots or timestamps** from his live streams where he takes a trade, or allow me to fetch the video transcripts (it was blocked in this session).
2. **Data feed:** broker MT5 bridge, a paid API (≈ $30–80/month), or MCX via your Indian broker?
3. **Market:** spot XAUUSD/XAGUSD, MCX, or both?
4. **Telegram:** private channel (you only) or a group you might share later?
5. **Risk defaults:** account size, risk % per trade, maximum signals per day.
6. **Hosting:** do you already have a VPS / domain (e.g. a subdomain of nearbyescape.com), or should we keep this fully separate?

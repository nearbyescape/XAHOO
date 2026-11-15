# Direction-probability terminal (fresh build) — plan

Status: **plan only.** Nothing is built and nothing has been deleted yet. Written 2026-11-15.
This replaces the signal application (engine, dashboard, deploy files), which will be removed when the build starts.

## 1. What it is

A live, private, terminal-style screen that answers one question for 10 markets:
**"How likely is this market to be higher or lower in 1 minute, 5 minutes, 15 minutes, 1 hour, 4 hours and 1 day — and how far could it move?"**

Six horizons: **1m · 5m · 15m · 1h · 4h · 1d** (1m and 5m added 2026-11-15 at the owner's request).

It shows probabilities, not trade instructions. Every number on screen is a measured frequency from history,
and the screen keeps a public-to-you scorecard of how its past probabilities turned out.

## 2. Markets and data (checked 2026-11-15)

All data comes from **Binance USDⓈ-M futures** (perpetual contracts), which lists gold and silver next to crypto.

| # | Market | Symbol | History available |
|---|---|---|---|
| 1 | Bitcoin | BTCUSDT | prices since 2020, positioning data since Sep 2020 |
| 2 | Ethereum | ETHUSDT | 2020 / Dec 2021 |
| 3 | Solana | SOLUSDT | Sep 2020 / Dec 2021 |
| 4 | XRP | XRPUSDT | 2020 / Dec 2021 |
| 5 | BNB | BNBUSDT | Feb 2020 / Dec 2021 |
| 6 | Dogecoin | DOGEUSDT | Jul 2020 / Dec 2021 |
| 7 | Cardano | ADAUSDT | 2020 / Dec 2021 |
| 8 | Chainlink | LINKUSDT | 2020 / Dec 2021 |
| 9 | **Gold** | XAUUSDT | **since Dec 2025 only (11 months)** |
| 10 | **Silver** | XAGUSDT | **since Jan 2026 only (10 months)** |

The eight coins are large, long-listed and liquid; the list is a setting and can be changed (today's top 10 by
Binance volume also includes ZEC, NEAR and HYPE, which have much shorter history).

What Binance provides that the previous build never had:
- **Real buyer/seller volume.** Every candle carries "taker buy volume": how much was bought at the ask versus sold
  at the bid. Spot gold has no such data; here it is exact.
- **Positioning:** open interest, long/short account ratios, top-trader ratios, taker buy/sell ratio (every 5 min).
- **Funding rate and premium** (how crowded longs or shorts are).
- **Order-book depth** within ±0.2% to ±5% of price.
- **Liquidations** (forced closes) on the live stream.

Live data: Binance WebSocket streams (updates several times a second). History: Binance's public archive
(`data.binance.vision`), free, no key.

**Constraint found:** Binance's live API refuses connections from this cloud workspace (restricted region, HTTP 451).
The archive and the spot-data mirror work. So models are built and tested here on archive data, and the live
connection is tested on the VPS. First step of the build: run `curl -s -o /dev/null -w "%{http_code}\n" https://fapi.binance.com/fapi/v1/ping`
on the VPS; it must print 200.

## 3. How the probabilities are made

### 3.1 Principle
A probability is only shown if, on data the model never saw, **"X%" came true about X% of the time**
(calibration) **and** it beat the naive forecast. Where it doesn't, the screen shows "no edge" instead of a number.
Expect honest values mostly between 40% and 60%, occasionally 65–70% in strong conditions. A screen that shows
"87% up" all day would be wrong.

### 3.2 Four layers, each tested separately
| Layer | Question | Inputs | Why it may work |
|---|---|---|---|
| **A. Trend / regime** | Is the market trending, ranging or reversing on 4h–1d? | Price vs long averages, breakout state, trend strength | Trend persistence on 4h and daily bars held up over 17 years on gold, silver, oil and Nasdaq (runs 18–22) |
| **B. Order flow** | Who is pushing right now? | Taker buy − sell volume (CVD), its divergence from price, book-depth imbalance, large-trade bursts | Published work on order-flow imbalance shows short-horizon predictive power; never testable before because spot data lacked it |
| **C. Positioning** | Is one side crowded? | Open-interest change with price, funding rate, long/short ratios, liquidation clusters | Extreme funding and one-sided positioning tend to precede squeezes |
| **D. Cross-market** | What are the leaders doing? | BTC's move vs each coin, gold vs silver, correlation regime | Smaller coins follow BTC with a lag; silver follows gold |

### 3.3 Combining them
- One model per horizon (1m, 5m, 15m, 1h, 4h, 1d), trained across all coins together so each learns from ~5 years × 8 markets.
- Gradient-boosted trees, then isotonic calibration. Plain logistic regression is the baseline to beat.
- **Walk-forward testing only:** train on the past, test on the following months, roll forward. No shuffling.
- Scored by Brier score and calibration curve against two baselines: 50/50 and "same direction as the last move".
- Costs don't enter (this is a forecast screen), but a "tradable edge" flag marks forecasts whose expected move
  exceeds typical fees.

### 3.4 The 1-minute and 5-minute horizons
These two work differently from the longer ones:
- **Main input is order flow, not trend.** Research on order-flow imbalance finds its predictive power is strongest
  over seconds to a few minutes, so these are the horizons where layer B has the best chance. Inputs: buy − sell
  volume over the last 5–60 seconds, order-book imbalance near the price, trade bursts, liquidations, and BTC's
  last few seconds for the other coins.
- **Training data:** 1-minute candles with buyer/seller volume (5 years) plus order-book depth snapshots (every
  30 seconds in the archive). Tick-level trades are very large (gigabytes a month for BTC), so they are used for the
  most recent 3–6 months only.
- **Update rate:** recalculated every 2–5 seconds live; a 1m forecast resolves a minute later, so the scoreboard fills
  quickly: about 1,400 scored forecasts per market per day. Live accuracy becomes visible within the first day.
- **What to expect:** the moves are tiny. A typical 1-minute move in BTC is a few hundredths of a percent, about the
  size of trading fees and spread. So each 1m/5m cell shows the probability **and** the expected move size, with a
  "too small to trade" mark when the move is below typical costs. A good 1m model is right perhaps 52–56% of the time.
- **Latency matters here:** the forecast is only as fresh as the data path (Binance → VPS → your screen), so the
  screen shows the data age in milliseconds, and cells grey out if the feed lags.

### 3.5 Volatility and range (the most reliable part)
How far a market moves is far more predictable than which way. For each market and horizon the screen shows:
- the **expected range** (for example "68% chance BTC stays between 63,900 and 65,800 in the next 4h"),
- the chance of reaching chosen levels (previous day's high/low, round numbers),
- a volatility state: quiet, normal, expanding.

### 3.6 Gold and silver
Binance has under a year of gold/silver history, too little to train on alone. Plan: the metals use the shared
model's order-flow and positioning layers (learned on crypto, then checked on the metals' 10–11 months), and the
trend layer is trained on the 17 years of gold/silver prices already downloaded. Their probabilities carry a
"limited history" mark until a year of out-of-sample scoring exists. Gold and silver futures on Binance also trade
around the clock, including weekends when the underlying market is closed; weekend readings are flagged.

### 3.7 What happened last time I tried this
Run 10 trained a model on gold candles and it had no skill out of sample (AUC 0.51). The difference now is the
input data (true order flow and positioning) and five years across eight markets. It may still find little at some
horizons; phase 1 exists to find out before any screen is built around it.

## 4. The screen

Terminal style: dark, monospace, dense; more polished than the previous build. Motion carries information.

**Main board: 10 rows × 6 horizons (1m · 5m · 15m · 1h · 4h · 1d)**
- Each cell: probability of up (for example `▲ 58%`), tinted green→red by value, with a thin confidence bar.
- The 1m and 5m cells update every few seconds and carry a small countdown ring to the end of their window;
  the longer horizons update on each new candle.
- **Direction needle** per market: an animated gauge that swings as the blended probability changes. A second, faster
  needle shows the short-term (1m–5m) push, so you can see at a glance when short-term flow agrees or disagrees
  with the longer trend.
- **Probability ribbon:** a small strip behind each row showing how the probability evolved over the last hours.
- **Flow meter:** a live buy-versus-sell bar that pulses with each burst of trades.
- Numbers roll when they change; cells flash briefly on a meaningful change (≥ 3 points); a new liquidation cluster ripples.

**Detail view (click a market)**
- Live candlestick chart with a **projection cone**: the expected range fanning out over each horizon, redrawn live.
- "Why": which inputs push the probability up or down right now (trend, flow, positioning, BTC).
- Positioning panel: open interest, funding, long/short ratio, liquidations.
- **Track record for this market:** calibration chart and hit rate of past forecasts.

**Scoreboard**
- Every forecast is stored and resolves when its horizon ends; resolved forecasts tick over with ✓ or ✗
  (1m and 5m are sampled once a minute for the scoreboard so it stays readable).
- Running calibration: "said 60–65% → happened 61% (n = 412)". If live calibration drifts, the affected cells turn grey.

**Other**
- Market strip: session clocks, BTC dominance of the move, overall risk-on/off gauge.
- Alerts (optional): probability crossing a threshold, regime change, liquidation spike.
- Honors "reduce motion"; works on a phone; one screen fits a 1080p display for wall or second-monitor use.

## 5. Technology (fresh)

| Part | Choice |
|---|---|
| Collector | Python asyncio, Binance combined WebSocket streams (trades, 1m candles, book ticker, depth, mark price, liquidations) + REST polling for open interest and ratios |
| Storage | Parquet files for history and features; SQLite for forecasts and scores |
| Models | LightGBM + calibration; retrained weekly by a scheduled job; every model version recorded |
| API | FastAPI; one WebSocket pushes updates to the screen |
| Screen | TypeScript + Svelte, canvas charts (Lightweight Charts), CSS/canvas animation; built to static files |
| Deploy | One Docker container behind the existing nginx on the VPS |

## 6. Phases

| Phase | What | Result |
|---|---|---|
| **0. Clean slate** | Tag the current code (`v1-signals`) so it stays recoverable; remove engine, web app, deploy files and old docs from `main`; stop the old container on the VPS | Empty project with this plan |
| **1. Research** | Download archive data for the 10 markets; build layers A–D; walk-forward tests for all six horizons (the 1m/5m models on 1-minute and order-book data); calibration report | **Go / no-go per horizon and market**, with real numbers |
| **2. Live engine** | Collector, feature pipeline, model serving, forecast store and scoring; replay tests against archive data | Probabilities updating live on the VPS |
| **3. Screen** | Board, needles, ribbons, flow meters, detail view, scoreboard | The terminal |
| **4. Run-in** | Two weeks live; compare live calibration with the tests; tune update rates | Trustworthy numbers on screen |

## 7. Decisions needed

1. **Coins:** BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK — or a different eight?
2. **Privacy:** private with login as before, on `xahoo.chaliyaboy.com`? Keep the name XAHOO?
3. **Alerts:** screen only, or also Telegram / phone notifications?
4. **VPS check:** the result of the `curl` command in section 2 (200 = Binance reachable).

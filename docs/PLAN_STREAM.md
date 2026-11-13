# XAHOO Live: YouTube broadcast mode + probability & pro features (plan)

Status: **plan only, nothing built yet.** Waiting for the owner's go-ahead and the decisions in §6.

---

## 0. Before going public (owner action)

Streaming signals makes XAHOO a public recommendation service, not a private tool.
- **SEBI (finfluencer rules):** unregistered persons giving buy/sell recommendations or showing return claims publicly is
  restricted, and registered brokers may not associate with them. Get advice from a lawyer or CA who knows SEBI and FEMA.
- **FEMA / RBI:** Indian residents may only trade forex/CFDs through authorised channels. The RBI "Alert List" names
  unauthorised offshore platforms. Check the broker before showing or promoting it. **MCX gold/silver** is the compliant route.
- **Checked 2026-11-13 (secondary sources; confirm with a lawyer):**
  - The RBI Alert List names **both Exness and XM**. Residents dealing on alert-list platforms, including depositing
    money for it, face penal action under FEMA. The list also names websites that *promote* such platforms, including
    "training or advisory" sites.
  - SEBI has barred regulated entities from working with unregistered finfluencers (2024). It treats live buy/sell calls
    by unregistered persons as unregistered advice; education is allowed (one source: educational price data must be
    at least 3 months old).
  - Enforcement is real: e.g. orders against Avadhut Sathe's trading academy (Dec 2025) and against a YouTube channel
    (Ravindra Bharti) with disgorgement and penalties.
- **Safe paths:** (a) register with SEBI as a Research Analyst before publishing calls; or (b) education-only content:
  methods, backtests, and replays of past setups (≥ 3 months old), no live calls, no return claims, no affiliate links to
  alert-list brokers; (c) use MCX gold/silver in any content; (d) keep XAHOO private for your own analysis.
- Built into the stream view regardless: a permanent **"Educational only — not investment advice"** bar, no win-rate
  promises, and a public scorecard that shows **every** signal's result, losses included.

---

## 1. Broadcast view `/stream` (Phase A, your direct request)

A separate screen, designed for 1920×1080 in OBS (Browser Source). It shows only public-safe content: no admin
buttons, no stop-rule controls, no account sizes, and never the private address.

| Element | Behaviour |
|---|---|
| **Signal card (top-right, large)** | Slides in with a sound on every new signal; **stays until you close it** (✕ or `Esc`; `Enter` = close all). Shows side, symbol, entry, **add-lot-2 zone**, stop, target, R:R, and a live **progress bar from stop to target** with the current R. Several cards stack. Click a card to pin it on the chart. |
| **"Get ready" banner** | Amber banner while a setup is forming: trigger level and a countdown to the 5m candle close. Turns into the signal card if it triggers, fades out with "cancelled" if not. |
| **Live chart, continuous** | Candles update **every tick (~1–2 s)**, not every 30 s. New data is pushed from the server over one stream connection (Server-Sent Events). EMA12/EMA200 update live. |
| **On-chart annotations** | Impulse box, pullback zone, trigger line, add zone, stop and target lines, so viewers see *why* a setup counts. |
| **Header strip** | XAU/XAG live price and spread, session clock (Asia/London/NY), time to the 5m candle close, next high-impact news countdown. |
| **Footer** | Disclaimer bar (always on) and a scrolling ticker of today's signals and their results. |
| **Layout presets** | `1` full chart + cards · `2` chart + scorecard · `3` gold & silver side by side · `F` focus on active trade. |
| **Access** | Still private: opened with a **read-only stream key** (`/stream?key=…`) that can only view, never change anything. Revocable, and never shown on screen. |

Technical: `/api/stream` (Server-Sent Events) pushes quotes, the forming 1m/5m bar, alerts and trade updates; the
chart applies `series.update()` per tick. Falls back to polling if the connection drops.

---

## 2. Probabilities (Phase B): honest numbers, not promises

Every probability comes from **our own backtests (2024–2026) plus live results**, always shown with the **sample size**.
They are **calibrated**: we check that "60%" really happened about 60% of the time.

On every signal card / detail:

| Stat | Meaning | Source |
|---|---|---|
| **P(target before stop)** | Historical hit rate of the full target for similar signals | Backtest grouped by symbol × direction × session × news-impulse, with a 90% range |
| **P(lot 2 fills)** | How often price returns to the add zone | Same buckets |
| **P(reaches +1R → risk-free)** | How often the stop could be moved to average entry | Same buckets |
| **Expected R** | Average result per trade of similar signals (can be negative) | Same buckets |
| **Typical duration** | Median minutes to exit | Same buckets |
| **Live vs backtest** | Is this strategy currently performing like its history? | Strategy stop rules |

Example: *"Similar signals (gold, sell, NY session, n=142): target 31% · lot 2 fills 64% · reaches risk-free 52% ·
expected +0.18R ±0.15 · median 70 min."*

Only buckets with at least 30 past trades are shown; smaller ones fall back to the next broader group. Never presented as certainty.

---

## 3. Transparency & trust (Phase B)

- **Public scorecard page / stream panel:** every signal since go-live, results in R (and %), equity curve, win rate,
  average R, profit factor, max drawdown, best/worst trade. Losses are never hidden. Daily, weekly and monthly views.
- **Auto-generated result images** (1080×1080 and 1920×1080) at the end of each day/week for YouTube, Telegram and
  Instagram, showing the real numbers.
- **Trade replay:** an animated replay of any past signal (impulse → pullback → trigger → add → exit) for
  post-stream review videos.

---

## 4. Market context (Phase C)

- **Economic calendar** with an impact filter and countdown (free weekly calendar feed). The news-impulse tag
  links to the event.
- **Regime panel:** daily trend state (the strategy's main filter), volatility versus normal, gold/silver ratio, distance to
  the previous day's high/low and the Asian range.
- **Multi-timeframe mini-charts** (1m / 15m / 1h) beside the main 5m chart.
- **Strategy health light:** green / amber / red from the stop rules (active / half size / paused), so viewers
  understand when the system is standing aside.

---

## 5. Pro polish (Phase D)

- **Branding:** logo, colours, a "starting soon" / "break" / "ending" scene, and an intro animation for new signals.
- **Sound pack:** distinct, stream-safe sounds for get-ready, signal, lot 2, risk-free, target and stop.
- **Viewer-safe risk calculator:** % risk → lots, educational, no account data shown.
- **Hindi / English labels** toggle.
- **Optional:** auto-post to the Telegram channel and a pinned YouTube chat message (needs YouTube API, later).

---

## 6. Decisions needed from the owner

1. **Legal check done?** (§0) Go-live of the public stream waits for it; the build can start now.
2. **Brand name and logo** on stream (XAHOO? NearbyEscape? a new name?).
3. **Show results in R only, or also in % at a stated risk** (e.g. "0.5% per lot")? R-only is safest.
4. **Language:** English, Hindi, or both.
5. **Which broker/market to show**, given §0 (e.g. none, or MCX).

## 7. Order & effort

| Phase | Scope | Estimate |
|---|---|---|
| **A** | `/stream` view, live tick chart over a stream connection, sticky top-right signal cards, get-ready banner, annotations, disclaimer, stream key, OBS guide | 1st (largest value for streaming) |
| **B** | Probability engine + calibrated per-signal stats, public scorecard, result images | 2nd |
| **C** | Calendar, regime panel, mini-charts, health light | 3rd |
| **D** | Branding, sounds, scenes, language, replay | 4th |

Every phase ships with tests (including privacy tests: the stream key must never be able to change anything) and screenshots.

# XAHOO v2: High-win-rate daily signal plan

**Goal (from the owner):** ≥ 90% win rate, good returns, signals every trading day.
**Rule this plan follows:** a win rate only counts if the system **also makes money after costs**. The dashboard always shows both, side by side.

---

## 1. What the data says about a 90% win rate

Experiment (`engine/research/winrate_tradeoff.py`, BACKTEST.md run 6): the **same entry signals** across all of 2026, both metals. Only the stop and target placement change:

| Stop | Target | Risk : reward | Win rate | Avg R / trade |
|---|---|---|---|---|
| 1× | 1.5× | 1 : 0.7 | 39% | −0.03 |
| 1× | 0.25× | 4 : 1 | 76% | −0.05 |
| 2× | 0.25× | 8 : 1 | 86% | −0.03 |
| 3× | 0.25× | 12 : 1 | **89%** | −0.02 |

1. **Win rate is a setting, not skill.** A tiny target and a wide stop will produce 90% wins from almost any entry.
2. **Return comes only from an edge.** Without one, every row loses about the cost of the spread.
3. **At 90% wins the risk is lopsided.** With risk : reward of 12 : 1, one loss erases 12 wins. A high-win-rate system is only safe if the 10% of losers are rare *and* controlled.
4. **Break-even maths:** with win rate W, the average loss can be at most W / (1 − W) times the average win. At 90% that is 9× the average win. Every percentage point below 90% shrinks that allowance quickly.

So "90% win rate" is easy to build and easy to fake. The real goal is **90% wins *and* a positive average R**. That needs entries that are genuinely better than random, which v1 did not have.

---

## 2. How v2 gets there: be selective about entries, not just about stop and target

### 2.1 Ground truth first (this week)
- **The trader's own calls.** Export his Telegram/VIP channel (Telegram Desktop → Export chat history → JSON). For every call, XAHOO checks it against the 1-minute price data and reports his **real** TP1-hit %, how often the stop is hit, average R, and drawdown. This tells us whether "9 out of 10" is achievable on these instruments, and at what return.
- **His rules.** Transcripts of the strategy videos and 30 live streams (via Remote Control on the owner's computer, or uploaded `.vtt` files) are encoded as rules and tested **once** on all of 2026, with settings fixed in advance.

### 2.2 More history (running in background)
Download **2023–2025** for both metals from Dukascopy (about 1,500 more trading days). Three regimes (2023 range, 2024 trend, 2025–26 high volatility) let a filter learn conditions rather than one market mood.

### 2.3 Probability filter ("meta-labelling")
- The rule engine (his rules + v1 setups) proposes **many** candidate trades.
- A gradient-boosted model estimates **P(TP1 is reached before the stop)** for each candidate. Inputs:
  - trend on 1h/4h; distance to EMA12/EMA200 in ATR; slope of EMA200
  - ATR regime and ADX
  - session and hour (IST)
  - distance to previous-day high/low and Asian high/low; the latest swing structure
  - gold/silver agreement; spread
  - minutes since the last impulse move
  - outcomes of the last few signals on the same instrument
- **Walk-forward training only:** train 2023–24 → validate 2025 → **final test on 2026 once**.
- Probabilities are calibrated, so "92%" on the dashboard means about 92 out of 100 such signals reached TP1 in the test data.
- A signal is sent only if **P ≥ threshold** *and* the expected R at that probability is positive given its stop and target.

### 2.4 Trade structure built for high hit rates
- **TP1 = the nearest structural target** (the last swing, the EMA, or the range midpoint), usually 0.3–0.6R. Close 50–70% there and move the stop to entry, as the trader does.
- **Stop = the real invalidation point** (beyond the swept level or the swing), not a fixed multiple.
- Remainder trails to TP2/TP3. These runners are where the return comes from once the trade is risk-free.
- The **average loss must stay under 4× the average TP1 win.** Signals whose structure doesn't allow that are dropped.

### 2.5 Daily discipline
- Target **1–3 signals per day across both metals**, the best-ranked only. Some quiet or news-heavy days will have **no signal**. That's by design: forcing daily trades is how high-win-rate systems blow up.
- **Hard stop: one full stop-loss → engine is quiet for that instrument for the rest of the day.** Two in a week → risk is halved automatically.
- News blackout: ±30 min around CPI, NFP, FOMC, PCE (calendar feed).
- Risk per trade **0.5–1%**. With 12:1-type asymmetry, size must assume a loss can come at any time.

---

## 3. Go-live gate (all must pass, measured on data the model never saw + 4 weeks of paper trading)

| Metric | Target | Minimum to go live |
|---|---|---|
| TP1-hit rate | **90%** | 85% |
| Average R per trade (after spread) | ≥ +0.15R | > +0.05R |
| Days with ≥ 1 signal | ≥ 80% | 70% |
| Max drawdown | ≤ 6R | ≤ 10R |
| Paper results vs backtest | within 5 percentage points | within 10 percentage points |

If a target is not met, the dashboard says so in plain numbers. **We do not lower the bar or redefine "win" to reach 90%.**

---

## 4. What changes in the app

| Area | Change |
|---|---|
| Signal card / Telegram | Shows **P(TP1)**, expected R, the stop-to-TP1 ratio, and "why this signal" (top factors) |
| Analytics | New **calibration chart** (predicted vs actual hit rate), win rate *and* average R on every view, daily-signal coverage |
| Trader comparison | Imports his Telegram export; scores his calls; shows how often XAHOO agrees with him |
| Risk | Daily loss lock, weekly risk halving, news-blackout banner |
| Strategy | Threshold slider: see live how win rate, return and signals per day change together |

---

## 5. Timeline

| Step | What | Needs from owner | Est. |
|---|---|---|---|
| 1 | Score his Telegram calls; encode his rules from transcripts | Telegram export + transcripts | 2–3 days |
| 2 | Download 2023–2025 (background) | — | ~6 h of throttled download |
| 3 | Probability filter + walk-forward test | — | 1 week |
| 4 | App: probability on signals, calibration view, risk locks | — | 1 week |
| 5 | Live price feed + Telegram bot | Feed choice, bot token | 2–3 days |
| 6 | Paper trading, daily review | — | 4 weeks |
| 7 | Go-live gate review | Owner decision | — |

---

## 6. Honest expectation

- **Likely outcome:** a TP1-hit rate in the 80s with a small positive average R, on 1–2 signals a day. That is a good, tradable system.
- **Possible outcome:** if his calls really hit 90% and the filter can learn what he sees, we get close to his level.
- **Also possible:** the gate is not passed. Then XAHOO stays a research and alert tool, and no real money goes on its signals.
- No setup can guarantee 90%. Any service that does is counting breakeven trades as wins, leaving out losing trades, or measuring over too short a period.

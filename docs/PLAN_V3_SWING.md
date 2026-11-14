# XAHOO v3: swing trend strategies for gold, silver and crude oil (plan)

Status: **plan, not built.** Evidence: [BACKTEST.md](BACKTEST.md) runs 18–22 (17 years, 2009–2026).
Markets: XAUUSD, XAGUSD and WTI crude oil (added 2026-11-14 at the owner's request, after run 22).

## 1. What 17 years of data say

1. **The live scalping strategy does not hold up.** On 2010–2026 it lost 267R and had 11 losing years of 17
   (run 21). Its 2024–2026 profit was specific to those years. It should not be traded with real money.
2. **High win rate and profit pulled in opposite directions, again.** Dip-buying strategies won 55–66% of trades
   and lost money over 17 years. Trend-following won 44–48% and made money.
3. **Trend-following on gold and silver is the one edge that survived every check:**
   - profitable with 12 of 12 setting combinations (not a lucky setting),
   - profitable on daily and on 4-hour bars; it fades on 1-hour bars and below,
   - profitable in both bull periods, about flat in the 2013–2018 bear/range market,
   - also positive, untuned, on Nasdaq 100 and crude oil; **negative on EUR/USD, GBP/USD, USD/JPY**.

So v3 does not aim for a high win rate. It aims for a positive, durable expectancy with losses about half the size of wins.

## 2. The strategies

Both use the same logic, on two timeframes, for XAUUSD, XAGUSD and WTI crude oil.

### S1: Daily trend breakout (core)
| Rule | Definition |
|---|---|
| Trend | Long only if close > 200-day average **and** 50-day average > 200-day average. Short on the mirror. |
| Entry | Daily close above the highest high of the previous 20 days (short: below the lowest low) → enter at the next day's open. |
| Initial stop | 3 × ATR(20) from entry. This distance is 1R. |
| Exit | Trailing stop 3 × ATR(20) below the highest high since entry (short: above the lowest low). No profit target. |
| Check time | Once a day after the New York close (22:00 UTC = 03:30 IST). |

17-year result: 147 trades (~9 a year), 47.6% wins, +0.25R per trade, PF 1.84, max drawdown −5.6R, average hold 26 days.

### S2: 4-hour trend breakout, filtered by the daily trend
| Rule | Definition |
|---|---|
| Filter | Trade only in the direction of S1's daily trend state. |
| Trend / entry | Same rules on 4-hour bars: 50/200-bar averages, close beyond the 55-bar high/low → enter at the next bar's open. |
| Stop / exit | 3 × ATR(20) of 4-hour bars, same trailing rule. |

17-year result: 376 trades (~23 a year), 43.6% wins, +0.19R per trade, PF 1.61, max drawdown −11.4R, average hold 4 days.

### Combined (run 20)
| Per year | Win % | Avg win / loss | Avg R | Net | Max DD | Worst year | Longest losing streak |
|---|---|---|---|---|---|---|---|
| ~32 trades (2–3 a month) | 44.7 | +1.16R / −0.56R | +0.21 | +6.6R a year | −16.2R | −9.3R (2021) | 8 trades |

Losing years: 8 of 17, six of them smaller than −2R. Profit is concentrated: 2011, 2013, 2020, 2024, 2025 and 2026 carry most of it.

### With crude oil added (run 22, June 2011 → Oct 2026)
| | Trades a year | Win % | Avg R | R a year | Max DD | Losing years | Worst year |
|---|---|---|---|---|---|---|---|
| Gold + silver | 30 | 43 | +0.18 | 5.5 | −16.4R | 8 of 16 | −9.3R |
| **Gold + silver + WTI** | 43 (3–4 a month) | 43 | +0.15 | **6.7** | **−13.7R** | 7 of 16 | **−3.7R** |

- Oil on its own is the weaker edge: S1 +0.16R per trade, S2 +0.06R (Brent, as a cross-check: +0.21R and +0.08R).
  Still positive under a harsh holding-cost assumption.
- Its value is diversification: it trends at different times from the metals (2015: oil +16R, metals −5R), so the
  three-market portfolio earned more with a smaller drawdown and a much milder worst year.
- Oil's profit came from short trades; long trades were flat. S2 on oil is the thinnest piece of the plan and the first
  to drop if paper trading disappoints.
- Oil specifics: weekend and news gaps are larger than in gold (one 38% day in April 2020), so the 1% risk can be exceeded
  on a gap; holding costs for oil CFDs change with the futures curve; MCX crude oil futures are the route in India.
- Live price: no free real-time oil quote was found. Dukascopy's hourly files (about an hour behind) are enough for
  daily and 4-hour decisions; to be confirmed on the VPS during the build.

## 3. What to expect

- **At 1% risk per trade:** roughly +6–7% a year on average; +15–26% in strong-trend years; 0 to −9% in sideways years;
  drawdown to about −16%. At 1.5%: about +10% a year with drawdown to about −24%.
- **Not daily signals.** 2–3 trades a month, held for days to weeks. Monitoring takes minutes a day.
- **Win rate ~45%.** Eight losses in a row has happened. The system makes money because average wins are twice average losses.
- **Sideways markets are the weak spot.** 2014–2018 and 2021–2023 made nothing or lost a little.
- **Costs barely matter here.** A $0.30 spread against a $100+ stop is under 0.5% of risk (it was 5–25% in scalping).
  Overnight financing is included in the tests. MCX futures avoid financing and are the compliant route in India.

## 4. Risk rules
- 1% of the account per trade to start (R = entry-to-stop distance).
- Up to 6 positions can be open at once (3 markets × 2 timeframes). Cap total open risk at 3%.
- Gold and silver usually trend together: when both signal the same direction, take the second at half size.
- Stop rules (existing guard, re-tuned): half size at −10R drawdown, pause at −24R (1.5 × the backtest's worst).
- Never widen a stop. Never add to a losing position.

## 5. Build plan

| Phase | What | Detail |
|---|---|---|
| **1. Engine** | Swing engine alongside the current code | Daily (22:00 UTC close) and 4h bars from history + live feed; S1 and S2 signal generation; trailing-stop tracking; the same code used in backtests (parity tests as for the scalper). |
| **2. App** | Dashboard for position trading | Open positions with entry, current trailing stop, R so far, days held; "next check" countdowns; breakout watch ("gold is 0.4 ATR below its 20-day high"); alerts for entry, each trailing-stop change, exit. Scalper signals switched off by default. |
| **3. Second-feed check** | Re-run S1/S2 on Dukascopy 2024–2026 | Confirms the result doesn't depend on the data vendor (daily closes already match to the cent). |
| **4. Paper trading** | 2–3 months | Few trades, so it needs longer than the scalper did. Compare each signal with the backtest rules. |
| **5. Go live** | Small size | 0.5% per trade for the first 10 trades, then 1%. |

## 6. Research queue after the build (each tested on the 17 years before use)
1. **Pyramiding:** add to winning positions (the classic trend-following profit lever).
2. **Nasdaq 100** with the same rules (+0.13R per trade untuned): more trades, different trend timing from metals and oil.
3. **Volatility-scaled position size.**
4. **MCX gold option selling with capped risk:** the only route to a genuinely high win rate; needs MCX options history.

## 7. Tested and rejected (run 18–19)
RSI(2) dip-buying · three-down-closes · EMA-20 pullback with 2R target · 12-month momentum on its own · partial profits at
+1R/+2R · ADX and momentum filters · 1-hour version · major currency pairs · the current scalper (run 21).

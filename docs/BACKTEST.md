# Backtest log

All results are **net of spread** (XAU $0.25, XAG $0.025), on Dukascopy 1-minute BID candles.
Trade management: 50% closed at TP1 → SL moved to entry ("cost to cost") → 25% at TP2 → 25% at TP3.
If a stop and a target are touched inside the same 1-minute candle, the **stop is assumed first** (conservative).
Reproduce any line with `python -m xahoo.cli backtest --from … --to … --symbols …`.

> Because half the position is banked at TP1, a trade that reaches TP1 and then returns to entry is still a
> small winner. So "TP1 hit %" equals "win %" here. The trader's "9 out of 10" most likely counts trades the same way.

## Run 1: first-draft rules (2026-11-12)

Gold, 10 Aug – 6 Oct 2026, 1m + 5m + 15m entries, targets 1R / 2R / 3R.

| Signals | TP1 hit | Avg R | Net R | Profit factor | Max DD |
|---|---|---|---|---|---|
| 155 | 40.6% | −0.14 | −21.7 | 0.76 | −26.2R |

- **1m entries lost money** (104 trades, −16R). On 1m the stop is often only about $1, so the $0.25 spread costs about 25% of the risk on every trade.
- The EMA12 pullback was the main loser; range and liquidity-sweep setups were positive.

## Run 2: tuning (in-sample: gold 10 Aug – 30 Sep)

Grid: 15m-trend agreement on/off · minimum stop 0 / 8 / 14 spreads · minimum stop 0.6 / 1.0 ATR · targets (1, 2, 3)R vs (0.75, 1.5, 2.5)R · timeframes {1m, 5m, 15m} vs {5m, 15m}.

- Every combination that included **1m lost money**.
- **TP1 at 0.75R** beat 1R in every comparable pair.
- The 15m-agreement filter and the minimum-stop settings made little difference on 5m/15m.

Chosen (fixed **before** looking at October): 5m + 15m entries, targets 0.75R / 1.5R / 2.5R, other settings at their defaults.

| Window | Signals | TP1 hit | Avg R | Net R | PF | Max DD |
|---|---|---|---|---|---|---|
| In-sample, Aug 10 – Sep 30 | 97 | 57.7% | +0.07 | +6.8 | 1.17 | −8.1R |

## Run 3: out-of-sample (gold 1 – 27 Oct, not used for tuning)

| Signals | Per day | TP1 hit | Avg R | Net R | PF | Max DD |
|---|---|---|---|---|---|---|
| 47 | 3.1 | **61.7%** | **+0.15** | +6.9 | 1.38 | −4.0R |

Findings that repeated in both windows:
- **New York session (18:00–22:30 IST) beats London**: TP1 hit 65% / 70% vs 52% / 56%.
- 5m EMA12 pullback and 5m liquidity sweep were positive in both windows.

What did **not** repeat:
- The A+ grade (score ≥ 85) hit TP1 10 out of 11 times in-sample, but only 2 out of 5 in October. **The confidence score is not yet a reliable filter.** It needs a lot more trades before it can be calibrated.

## Run 4: more unseen data (silver never used for tuning)

Same settings as run 3, nothing changed.

| Window | Signals | TP1 hit | Avg R | Net R | PF | Max DD |
|---|---|---|---|---|---|---|
| Gold 28 Oct – 11 Nov | 26 | 65.4% | +0.21 | +5.4 | 1.67 | −2.6R |
| **Silver 10 Aug – 11 Nov** | 159 | 55.3% | **−0.03** | −5.4 | 0.92 | −17.1R |

By setup on silver: sweep 31 trades, 71% TP1, +0.22R · EMA12 pullback 102 trades, −0.08R · EMA200 retest 21 trades, −0.27R.

Consistent across every window so far:
- **Liquidity sweep** is the strongest setup on both metals (TP1 70–77%, positive avg R).
- **EMA200 retest** lost money in every window except one with 2 trades → **disabled by default**.
- EMA12 pullback works on gold, not (yet) on silver.
- The New York session edge on gold **did not repeat on silver** → not a rule yet.

Not changed on purpose: no silver-specific tuning until January–June gives another unseen test.

## Run 5: largest unseen test (both metals, 10 Feb – 30 Jun 2026), settings unchanged

| Signals | Per day | TP1 hit | Avg R | Net R | PF | Max DD |
|---|---|---|---|---|---|---|
| 514 | 5.2 | 53.7% | **−0.05** | −25.2 | 0.89 | −28.1R |

| Setup | n | TP1 hit | Avg R |
|---|---|---|---|
| EMA12 pullback | 418 | 56.0% | −0.03 (5m +0.01, 15m −0.11) |
| Liquidity sweep | 79 | 43.0% | **−0.24** |
| Range | 17 | 47.1% | +0.26 |

| Score | n | TP1 hit | Avg R |
|---|---|---|---|
| < 70 | 208 | 58.2% | +0.08 |
| 70–80 | 225 | 54.3% | −0.08 |
| 80–85 | 56 | 46.4% | −0.22 |
| ≥ 85 (A+) | 25 | **28.0%** | −0.48 |

### Verdict so far
- **No proven edge.** Over all unseen data (~770 trades) the rules are about break-even to slightly negative after spread. The positive October/November gold results did not repeat in February–June.
- The liquidity sweep, the best setup from August to November, was the worst one from February to June. A setup that flips like that is following the market's mood of the moment, not a stable edge.
- **The confidence score is inverted:** the more confluence factors line up, the worse the trade. Most likely high scores pick moves that are already stretched. The score must not be used to filter signals until this is fixed.
- All 2026 data has now been used. **Any further tuning must be checked on new data** (paper trading from here on), or it will only fit the past.
- **Do not trade real money on these signals.**

## Run 6: win rate vs return (all 2026, both metals, same entries)

Script: `engine/research/winrate_tradeoff.py`. Single exit at the target; stop and target in multiples of the original stop.

| Stop | Target | Risk:reward | Trades | Win % | Avg R | Net R | Worst DD |
|---|---|---|---|---|---|---|---|
| 1× | 0.25× | 4:1 | 1256 | 75.9 | −0.052 | −64.8 | −67.2 |
| 1× | 0.5× | 2:1 | 1145 | 62.6 | −0.059 | −67.1 | −73.1 |
| 1× | 1.0× | 1:1 | 970 | 47.5 | −0.048 | −46.9 | −59.5 |
| 1× | 1.5× | 1:1.5 | 881 | 39.0 | −0.032 | −28.4 | −43.8 |
| 2× | 0.25× | 8:1 | 1314 | 86.4 | −0.025 | −32.4 | −47.7 |
| 2× | 1.5× | 1.3:1 | 946 | 55.7 | −0.001 | −1.2 | −43.3 |
| 3× | 0.25× | 12:1 | 1301 | **89.3** | −0.021 | −26.8 | −37.0 |
| 3× | 1.0× | 3:1 | 1050 | 70.2 | −0.007 | −7.7 | −24.0 |

**Win rate moves from 39% to 89% by stop/target placement alone; average R stays negative in every row.**
A high win rate on its own is not evidence of an edge. Plan: [PLAN_V2_HIGH_WINRATE.md](PLAN_V2_HIGH_WINRATE.md).

## Run 7: the trader's own trade management (from 10 posted screenshots), all 2026, both metals

What the screenshots show: tight stop just beyond the last wick ($2.2–5.4 on gold), one far target at the next
liquidity pool (risk:reward 1:3 to 1:9), stop moved to entry early, all sessions including ~08:00 IST,
~2.5–3% account risk per trade (100 oz, ~$550 on a $17–24k account). His own panels show a day with 2 wins / 1 loss
and breakeven exits (+$3.74, +$3.63) displayed as green trades.

Check against our data: the 10 Nov 13:25 IST XM sell (4117.54 / SL 4121.95 / TP 4093.40) reaches TP, +5.5R.
The 30 Oct Exness sell had a $0.73 stop, smaller than typical broker-to-broker price differences, so it can't be verified.

Variants fixed before running (`engine/research/trader_style.py`). Same XAHOO entries, his management:

| Variant | Asia | Trades | /day | Green % (win+BE) | Real win % | Avg R | Net R | PF | Max DD |
|---|---|---|---|---|---|---|---|---|---|
| v1 baseline | no | 940 | 5.0 | 53.2 | 53.2 | −0.044 | −41.4 | 0.90 | −54.9 |
| BE@1R, TP 3R | no | 874 | 4.7 | 46.9 | 18.9 | −0.077 | −67.1 | 0.85 | −77.3 |
| BE@1R, TP 5R | no | 841 | 4.5 | 47.6 | 16.3 | −0.047 | −39.6 | 0.91 | −69.5 |
| BE@1R, TP liquidity 3–10R | no | 375 | 2.7 | 46.9 | 16.0 | **−0.015** | −5.5 | 0.97 | −23.0 |
| BE@1R, TP liquidity 3–10R | yes | 448 | 2.9 | 47.8 | 15.6 | −0.016 | −7.0 | 0.97 | −22.8 |
| BE@1R, TP liquidity 2–10R | no | 478 | 3.0 | 44.8 | 16.7 | −0.094 | −45.1 | 0.83 | −49.6 |
| liquidity 3–10R + EMA200 retest | no | 406 | 2.8 | 47.3 | 16.5 | −0.037 | −14.8 | 0.93 | −26.0 |

**Conclusion:** his management on XAHOO's entries is roughly break-even at best. Any edge he has is in **which trades he
picks** (discretionary reading of the chart), not in how he manages them. To capture that we need his **complete** call
history, losses included, so we can measure it and train the engine on his actual entries.

## Run 8: liquidity sweep + buyer/seller pressure (owner: "he checks liquidity, buyers and sellers pressure")

Pressure is measured from 1m volume. Each candle's volume is split into buying/selling by where it closed in its range.
Then: delta, volume relative to the same time-of-day (20-day average), net pressure over the last 3 bars.
Liquidity pools: equal highs/lows, previous-day high/low, Asian high/low, last swing high/low.
Setup `liquidity_pressure`: a pool is swept (wick through ≤ 0.6 ATR, close back inside), then a displacement candle
(body ≥ 0.8 ATR, volume ≥ 1.3× normal, delta in trade direction) with net pressure > 0.15; stop beyond the sweep wick.

**Development data only (2025: gold Feb–Dec, silver Feb–Aug). 8 variants fixed in advance** (`engine/research/liquidity_pressure.py dev`):

| Variant | Trades | Green % | Win % | Avg R | Net R | PF |
|---|---|---|---|---|---|---|
| A liquidity target 2–10R, BE@1R, no bias filter | 20 | 35.0 | 25.0 | −0.14 | −2.9 | 0.74 |
| A … with 1h-bias filter | 18 | 27.8 | 22.2 | −0.19 | −3.5 | 0.68 |
| B liquidity target 3–10R, BE@1R | 11 | 45.5 | 27.3 | −0.04 | −0.4 | 0.93 |
| B … with bias | 10 | 40.0 | 30.0 | −0.04 | −0.4 | 0.93 |
| C partials 0.75/1.5/2.5R | 75 | 54.7 | 53.3 | −0.11 | −8.2 | 0.74 |
| C … with bias | 70 | 51.4 | 50.0 | −0.15 | −10.6 | 0.66 |
| D fixed 2R, BE@1R | 75 | 46.7 | 25.3 | −0.23 | −17.1 | 0.52 |
| D … with bias | 70 | 44.3 | 24.3 | −0.26 | −18.0 | 0.49 |

No variant was positive on development data, so **it was not run on 2026** (that would only use up the test data).

### Does volume pressure predict anything? (`engine/research/pressure_event_study.py`, 2025, all 5m bars)

| Pressure, last 3 bars | Bars | Move next 60 min (ATR) | Up after 60 min |
|---|---|---|---|
| strong sell | 180 | +0.20 | 56.1% |
| sell | 18,368 | +0.11 | 54.4% |
| neutral | 64,379 | +0.09 | 53.1% |
| buy | 24,981 | +0.08 | 52.5% |
| strong buy | 385 | +0.10 | 51.4% |

After a sweep of highs with strong selling pressure, price went **up** 58% of the time (77 cases), the opposite of what the setup assumes.
**Conclusion:** pressure estimated from candle volume carries no usable signal on spot gold/silver. Spot metals have no
central exchange, so the platform's "volume" is only that broker's own trading activity. True buyer/seller pressure
(aggressor volume, order book) exists only on the futures exchange (COMEX gold/silver futures, or MCX in India) and would
need that data feed to test.

## Run 9: research-driven search (2026-11-12)

Literature checked: overnight-vs-day asymmetry in gold (Blose, Gondhalekar & Kort 2018, *J. Economics & Finance*);
intraday "hat-shaped" gold pattern (CBS thesis 2019); intraday momentum in gold/silver futures (Chinese futures studies);
time-series momentum (Moskowitz, Ooi & Pedersen 2012). RSI(2)-type dip buying: no reliable evidence on intraday gold.

**Hour-of-day drift (`research/seasonality.py`, 2025 vs 2026):** the only hour positive in both years and both metals is
22:00–23:00 UTC, the daily broker re-open with the widest spreads. That is a BID-price artefact (the bid drops when the
spread widens, then recovers), so it isn't tradable. All other hours: |t| ≲ 2 and sign flips between years → **rejected.**

**Daily trend + intraday pullback (`research/trend_pullback.py`).** Trend = yesterday's close vs 50-day EMA and 20-day
return; enter when price pulls back `depth` × daily ATR against the trend between 07:00 and 17:00 UTC; TP/SL in daily ATR;
flat by 20:00 UTC; at most one trade per day. 2025 grid (40 configs): the **trend filter improved results in every
comparable pair** on both metals. Best per metal on 2025 fixed, then run **once** on 2026:

| | Year | Trades | Win % | Avg R | Net R | Max DD | Long/short |
|---|---|---|---|---|---|---|---|
| Gold, depth 0.3, TP 0.4 / SL 0.6 dATR | 2025 (dev) | 185 | 60.0 | +0.070 | +12.9 | −6.9 | 178/7 |
| | **2026 (held out)** | 184 | 55.4 | **+0.026** | **+4.9** | −6.1 | 69/115 |
| Silver, depth 0.5, TP 0.25 / SL 1.0 dATR | 2025 (dev) | 149 | 71.8 | +0.030 | +4.5 | −3.2 | 141/8 |
| | 2026 (held out) | 107 | 59.8 | −0.011 | −1.1 | −5.3 | 43/64 |

**First result that survived a held-out year** (gold, positive in both a rising and a falling year), but the edge is
small: about +0.03 to +0.07R per trade, ~1 trade/day. The high-hit-rate variants (TP 0.15 / SL 0.5 dATR) hit 72–74% but
expectancy falls to ~0, which is the same trade-off as run 6. Next: confirm on 2023–2024, then a probability filter (Track C)
to keep only the best days.

## Run 10: probability filter (Track C), `engine/research/ml_filter.py`

Candidates: every 15m close 07:00–17:00 UTC, both directions, both metals (~37k in 2025). Fixed high-hit-rate structure:
TP 0.2 × daily ATR, SL 0.6 × daily ATR, flat 20:00 UTC (break-even win rate ≈ 75% before costs). 24 features: daily trend
and momentum, distance to the 50-day EMA, previous-day move, pullback/extension today, PDH/PDL distance, hour, weekday,
EMA12/200 on 15m, 15m/1h/4h bias, ADX, ATR ratio, volume pressure, relative volume, the other metal's move.
Gradient boosting, train Feb–Sep 2025, validate Oct–Dec 2025.

| | AUC |
|---|---|
| Train | 0.899 |
| **Validation** | **0.511** (0.50 = coin flip) |

Win rate and avg R by predicted decile on validation are flat (60–67% win, avg R −0.11 … +0.01); the most confident decile
was the worst. The model memorised 2025 and has **no predictive power out of sample**. Only "with the daily trend, long"
was ~break-even (n = 4,280, 67% win, +0.004R). Not run on 2026 (nothing to test).

**Conclusion across runs 1–10:** at intraday horizons, publicly available price/volume features don't predict gold or
silver well enough to beat costs, apart from the small daily-trend effect (run 9). That matches the research literature
on liquid markets.

## Run 11: the trader's own setup from his 12 Nov live stream (`research/trader_setup.py`)

Rules (see docs/trader/METHOD.md): fast impulse (≥ K × ATR within 12 bars) → shallow pullback to the 12 EMA
(≤ 60% retrace, 2–8 bars) → **5m candle closes beyond the pullback** ("breakdown") → stop beyond the pullback, 5m chart,
all sessions incl. Asia. 2025 dev grid (24 variants): bigger impulses and the daily-trend filter improved results almost
monotonically. Two finalists fixed, run once on unseen years:

| Finalist | 2026 trades / win % / avg R | 2024 trades / win % / avg R |
|---|---|---|
| A: impulse 5, daily trend, partials | 82 / 54.9 / −0.006 | 48 / 50.0 / +0.001 |
| B: impulse 5, daily trend, 2R, BE@1R | 82 / 29.3 / +0.021 | 47 / 31.9 / +0.034 |

→ Single-entry version ≈ break-even.

## Run 12: + his scale-in ("add quantity at the EMA") (`research/scale_in.py`)

Rule taken from the stream, not tuned: 1 lot at the breakdown close; **add 1 lot if price returns to the 12 EMA**
(value at signal time; if the EMA isn't between entry and stop, at entry ± 0.5R); one shared stop; target measured from
the first entry; stop moves to the average entry at +1R; flat after 5 h. Limit fill assumed at touch; if the add and the stop
are hit in the same minute, both count as filled and stopped. R = units of the first lot's risk.

| Variant | Year | Trades | Win % | Avg R | Net R | Worst | Lot added |
|---|---|---|---|---|---|---|---|
| impulse 4, TP 2R, 1 lot | 2024 / 2025 / 2026 | 119 / 222 / 183 | 28.6 / 36.0 / 31.7 | −0.016 / +0.055 / +0.076 | −1.9 / +12.2 / +13.9 | −1.0 | — |
| **impulse 4, TP 2R, scale-in** | 2024 / 2025 / 2026 | 119 / 222 / 183 | 31.9 / 39.6 / 32.8 | **+0.072 / +0.098 / +0.199** | **+8.6 / +21.9 / +36.4** | −1.8 | 63–68% |
| impulse 4, TP 1.5R, scale-in | 2024 / 2025 / 2026 | 119 / 222 / 183 | 38.7 / 44.1 / 36.6 | +0.082 / +0.082 / +0.131 | +9.8 / +18.3 / +24.0 | −1.8 | 63–67% |
| impulse 5, TP 2R, scale-in | 2024 / 2025 / 2026 | 46 / 89 / 80 | 32.6 / 39.3 / 32.5 | +0.168 / +0.247 / +0.209 | +7.7 / +22.0 / +16.7 | −1.7 | 60–66% |

All 6 variants × 3 years: **scale-in beat a single lot in 18/18 cases and was positive in 18/18**, including both
years not used for development. **First result in this project that is positive and consistent across three years.**
Limits: win rate 32–44% (profit comes from winners ≈ 2–3× losers, as in his own 12 Nov record); 0.5–1 signal per
trading day across both metals; worst trade ≈ −1.8R with both lots on; fills at touch on the EMA add; Dukascopy prices.

## Run 13: his 4h support/resistance filter on the scale-in setup (impulse 4, TP 2R)

Rule as he states it: skip the trade if the latest 4h swing low (for a sell) / swing high (for a buy) lies between
entry and target.

| | 2024 | 2025 | 2026 |
|---|---|---|---|
| Scale-in, no filter (trades / avg R) | 119 / +0.072 | 222 / +0.098 | 183 / +0.199 |
| Scale-in + 4h filter | 96 / **−0.018** | 178 / +0.100 | 158 / +0.298 |

Inconsistent (worse in 2024, equal in 2025, better in 2026), so **not adopted**.

## Run 14: drawdown and losing streaks, impulse 4 / TP 2R

| | Year | Net R | Max drawdown | Longest losing streak |
|---|---|---|---|---|
| 1 lot | 2024 / 2025 / 2026 | −1.9 / +12.2 / +13.9 | −11.0 / −11.5 / −16.5R | 5 / 6 / 5 |
| **Scale-in** | 2024 / 2025 / 2026 | +8.6 / +21.9 / +36.4 | **−15.4 / −17.7 / −18.8R** | 5 / 6 / 5 |

Drawdowns are about the size of a year's profit, so position size decides whether this is survivable.
At 0.5% account risk per lot: ≈ +4% to +18% a year, max drawdown ≈ −8% to −9%. At 1%: ≈ +9% to +36%, drawdown ≈ −15% to −19%.
At the trader's ~2.5% per lot, drawdowns of −40% to −47% would have occurred.

## Run 15: exit study on the live strategy (`engine/research/exits.py`), gold + silver

Same entries (StrategyParams.trader()), five exits fixed in advance. R = first lot's risk. Pessimistic same-bar rules.

| Exit | 2024 avg R / net | 2025 (dev) avg R / net | 2026 avg R / net | 3-yr net | Win % | Max DD |
|---|---|---|---|---|---|---|
| **E0 both lots at 2R, stop to avg at +1R (current)** | +0.072 / +8.6 | **+0.098 / +21.9** | +0.210 / +37.8 | **+68.3** | 32–40 | −15 … −18.5 |
| E1 after +1R trail 5m EMA12 (cap 5R) | +0.223 / +26.5 | +0.034 / +7.5 | +0.188 / +33.8 | +67.8 | 46–51 | −11 … −19 |
| E2 lot 1 at 1R, lot 2 trails EMA12 | +0.075 / +9.0 | +0.021 / +4.6 | +0.160 / +28.7 | +42.3 | 48–53 | −12 … −17 |
| E3 lot 1 at 1R, lot 2 at 3R | +0.013 / +1.6 | +0.015 / +3.4 | +0.173 / +31.1 | +36.1 | 48–53 | −12 … −20 |
| E4 E0 + exit if +1R not reached in 60 min | +0.105 / +12.5 | +0.072 / +16.1 | +0.076 / +13.7 | +42.3 | 37–40 | −9 … −22 |

**E0 stays the default** (best on the dev year, joint-best 3-year total). E1 makes about the same 3-year profit with a higher
win rate and smaller drawdowns in 2 of 3 years, but it was weak on the dev year. It is available as `exit_mode="trail_ema"`
(`--exit trail_ema`). Engine check, E0 vs E1: 2025 +0.084 vs +0.015R, 2026 +0.199 vs +0.173R.

## Run 16: same strategy, unchanged, on other markets (`engine/research/multi_market.py`)

Data: HistData.com free 1m (Nasdaq 100 = NSXUSD, S&P 500 = SPXUSD, EURUSD), 2024–2026; BTC and Dow not available from
the free sources here. Spreads: NAS100 1.2 pt, S&P 0.5 pt, EURUSD 0.8 pip. Nothing tuned.

| Market | 2024 avg R / net | 2025 avg R / net | 2026 avg R / net |
|---|---|---|---|
| Nasdaq 100 | −0.073 / −7.0 | −0.140 / −19.6 | +0.152 / +15.8 |
| S&P 500 | −0.127 / −13.7 | −0.308 / −44.0 | −0.209 / −20.3 |
| EURUSD | −0.270 / −31.1 | +0.028 / +3.3 | +0.154 / +13.6 |
| *Gold + silver (run 12)* | *+0.072 / +8.6* | *+0.098 / +21.9* | *+0.199 / +36.4* |

**The edge does not generalise:** losing in 6 of 9 market-years elsewhere. It is specific to precious metals in
2024–2026, a period of unusually strong trends. Conclusions: (1) don't trade other markets with it; (2) the gold/silver edge
may depend on that trending regime, so enforce the strategy stop rule (pause if live drawdown > 1.5× the backtest's worst,
or after 50 trades clearly below expectation) and re-test every quarter.

## Run 17: volatility-regime and news-impulse filters (`engine/research/filters.py`)

Volatility = 5m ATR at the signal vs the previous 20 days. News spike (no free historical calendar, so detected from
price): a 1m candle at :00/:30 between 12:00 and 19:30 UTC with range ≥ 5× its 20-day median. Fixed in advance; dev 2025.

| Variant | 2024 trades / avg R | 2025 (dev) | 2026 |
|---|---|---|---|
| none | 134 / +0.136 | 238 / +0.084 | 192 / +0.210 |
| V1 ATR ≥ median | 109 / +0.013 | 166 / +0.124 | 134 / +0.298 |
| V2 ATR ≥ 70th pct (best on dev) | 85 / +0.030 | 124 / +0.194 | 91 / +0.144 |
| V3 skip ATR > 95th pct | 118 / +0.078 | 205 / +0.055 | 175 / +0.199 |
| V4 median … 95th | 93 / −0.081 | 133 / +0.089 | 117 / +0.294 |
| **N1 only ≤ 90 min after a news spike** | **18 / +0.626 (55.6% win)** | **14 / +0.501 (57.1%)** | **12 / +0.515 (50.0%)** |
| N2 never ≤ 90 min after a news spike | 116 / +0.060 | 224 / +0.058 | 180 / +0.189 |

- Volatility filters: inconsistent across years → **none adopted**.
- **Post-news signals were 3–6× better than average in every year**, but are rare (44 in 3 years, t ≈ 2). Avoiding news
  would *lower* profit. Action: keep all signals and **tag** post-news ones; no size increase until confirmed live.

## Runs 18–21 (2026-11-14): 17-year tests, swing strategies, and the live scalper re-tested

Data: HistData.com 1-minute bars 2009 → Oct 2026 for gold and silver (4,550 trading days), rebuilt into daily
(New York close), 4h and 1h bars. Daily closes match Dukascopy to the cent on the overlapping 2024–2026 days.
Costs: spread ($0.30 gold, $0.03 silver) + overnight financing (longs 5%/yr of notional, shorts 1%/yr).
Signals at a bar's close, fills at the next bar's open, stops checked on highs/lows. R = initial stop distance.
Periods: 2009–2012 bull · 2013–2018 bear/range · 2019–2026 bull.

### Run 18: textbook swing strategies, daily bars, untuned (`engine/research/swing.py`)

| Strategy (gold + silver) | Trades | Win % | Avg R | PF | 2009–12 | 2013–18 | 2019–26 |
|---|---|---|---|---|---|---|---|
| T1 Donchian 55/20 breakout, long + short | 138 | 31 | +0.24 | 1.4 | +0.52 | −0.24 | +0.53 |
| **T2 50/200-day trend + 20-day breakout, 3-ATR trailing stop** | 147 | 47.6 | **+0.25** | **1.84** | +0.38 | 0.00 | +0.40 |
| T3 12-month momentum, monthly | 404 | 52 | +0.04 | 1.1 | +0.04 | +0.01 | +0.06 |
| P1 RSI(2) dip-buying in the 200-day trend | 330 | 58 | −0.06 | 0.7 | +0.03 | −0.09 | −0.08 |
| P2 three down closes in a trend | 349 | 60 | −0.05 | 0.8 | −0.06 | −0.06 | −0.04 |
| P3 pullback to the 20-day EMA, 2R target | 315 | 42 | +0.02 | 1.0 | 0.00 | −0.09 | +0.11 |

Trend-following made money; the high-win-rate dip-buying strategies (55–66% wins) lost money.

### Run 19: is T2 robust? (`swing_robust.py`, `swing_markets.py`)
- **Settings:** breakout 10/20/40/55 days × trail 2/3/4 ATR → **12 of 12 profitable** (avg R +0.10 … +0.33, PF 1.3–2.05).
  Weak spot in every version: 2013–2018 is flat to slightly negative.
- **Timeframes:** same rules on 4h bars (55-bar breakout): 661 trades, +0.137R, PF 1.43, positive in all three periods.
  On 1h bars the edge is nearly gone (+0.01 … +0.05R). **4h with the daily trend as filter:** 376 trades (~23/yr),
  43.6% wins, **+0.193R, PF 1.61, max DD −11.4R**.
- **Variants that did not help:** half off at +1R or +2R (win rate 48 → 50%, less profit), 12-month-momentum filter, ADX filter.
- **Other markets, same untuned daily rules, 2009/10–2026:** gold +0.26R, silver +0.24R, Nasdaq 100 +0.13R,
  crude oil +0.16R, S&P 500 +0.02R, **EUR/USD −0.12R, GBP/USD −0.22R, USD/JPY −0.08R**. Not a universal edge: it works
  on strongly trending markets (metals, oil, Nasdaq), not on major currency pairs.

### Run 20: proposed pair — daily T2 + 4h T2 (daily-filtered), gold + silver, 2010–2026

| Trades | Per yr | Win % | Avg win / loss | Avg R | PF | Net R | Max DD | Losing years | Worst year | Longest losing streak |
|---|---|---|---|---|---|---|---|---|---|---|
| 523 | 31.6 | 44.7 | +1.16R / −0.56R | **+0.209** | 1.67 | +109.3 (6.6R/yr) | −16.2R | 8 of 17 (6 of them within ±2R) | −9.3R (2021) | 8 |

By year (R): 2010 +9.3 · 2011 +17.4 · 2012 −0.4 · 2013 +16.3 · 2014 +0.2 · 2015 −5.0 · 2016 −0.2 · 2017 −1.0 ·
2018 −0.2 · 2019 +8.9 · 2020 +26.3 · 2021 −9.3 · 2022 −0.9 · 2023 −1.7 · 2024 +15.2 · 2025 +23.2 · 2026 +11.3.
Longs +0.28R (327 trades), shorts +0.09R (196). Gold and silver contribute about equally. Up to 4 positions open at once.

### Run 21: the live scalping strategy (`StrategyParams.trader()`) on 2010–2026 (`scalp_17y.py`)

| | Net R | Losing years | Gold | Silver |
|---|---|---|---|---|
| 2010–2026, rules unchanged | **−267R** | **11 of 17** | −54R | −213R |

Worst years −51R (2010), −53R (2015), −62R (2018), −66R (2020). Positive in 2011–2014, 2016 and 2026. On this feed
2024 = −4.7R and 2025 = −3.7R (gold positive, silver negative both years). The earlier positive 2024 result (run 12)
had most of 2024's silver data missing. **Conclusion: the scalper's 2024–2026 result does not hold up; it should
not be traded with real money.** See [PLAN_V3_SWING.md](PLAN_V3_SWING.md).

## Caveats
- ~150 trades in total on one metal. That is enough to tell clearly losing rules from promising ones, but not enough to prove an edge.
- Dukascopy prices differ slightly from any retail broker's prices; spread is modelled as fixed; no slippage; no news blackout yet (calendar feed not connected).
- Next step is the trader's actual rules (transcripts), tested once on the full Feb–Nov window with settings fixed in advance. Then paper-trade before any real money.

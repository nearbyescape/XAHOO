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

## Caveats
- ~150 trades in total on one metal. That is enough to tell clearly losing rules from promising ones, but not enough to prove an edge.
- Dukascopy prices differ slightly from any retail broker's prices; spread is modelled as fixed; no slippage; no news blackout yet (calendar feed not connected).
- Next step is the trader's actual rules (transcripts), tested once on the full Feb–Nov window with settings fixed in advance. Then paper-trade before any real money.

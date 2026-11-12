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

## Caveats
- ~150 trades in total on one metal. That is enough to tell clearly losing rules from promising ones, but not enough to prove an edge.
- Dukascopy prices differ slightly from any retail broker's prices; spread is modelled as fixed; no slippage; no news blackout yet (calendar feed not connected).
- Silver and January–June 2026 are still downloading. Next steps: re-run on those (more unseen data), then paper-trade live for 3–4 weeks.

# XAHOO research results

All numbers are **walk-forward**: every model is trained only on data before the period it is tested on.
Data: Binance USDⓈ-M futures archive (data.binance.vision), 1-minute bars, mark price, positioning metrics and
funding, 2022-01 → 2026-10. Target: is the **mark price** higher at the end of the horizon than now.
Test folds: 2024 H1, 2024 H2, 2025 H1, 2025 H2, 2026 Jan–Oct. Scripts are in `research/`.

## 1. Direction (8 coins pooled, 2024-01 → 2026-10)

AUC 0.50 = coin flip. Accuracy = share of forecasts whose more-likely direction came true.

| Horizon | Forecasts | AUC | Accuracy | Shown ≥ 55%: share / hit | ≥ 60%: share / hit | Avg move | AUC by fold |
|---|---|---|---|---|---|---|---|
| 1m  | 1,960,107 | 0.543 | 52.9% | 25.1% / 56.5% | 3.9% / 59.1% | 0.07% | .549 .551 .551 .537 .533 |
| 5m  | 1,185,462 | 0.532 | 52.3% | 11.0% / 55.5% | 0.4% / 59.6% | 0.15% | .537 .534 .534 .531 .527 |
| 15m |   792,026 | 0.535 | 52.5% | 13.8% / 55.8% | 0.7% / 58.6% | 0.26% | .539 .540 .533 .536 .531 |
| 1h  |   396,487 | 0.534 | 52.4% | 17.5% / 55.2% | 1.9% / 58.8% | 0.51% | .548 .537 .529 .538 .525 |
| 4h  |   198,313 | 0.532 | 52.2% | 23.1% / 55.0% | 3.1% / 57.5% | 1.04% | .552 .537 .538 .532 .515 |
| 1d  |    49,520 | 0.528 | 51.6% | 18.7% / 54.2% | 5.2% / 55.7% | 2.70% | .536 .528 .526 .518 .533 |

What this means:
- There is a **real but small** edge at every horizon on the coins: the more-likely direction is right about
  52–53% of the time overall and 55–56% when the screen shows 55% or more.
- The edge **fades over time** at 1m and 4h (later folds are weaker). The live scoreboard watches for this.
- At 1m the average move (0.07%) is smaller than a round-trip taker fee (~0.10%). The 1m/5m numbers are for
  reading pressure, not for trading on their own.
- Which inputs matter (AUC by layer, last two folds): at 1m order flow dominates (trend .508, flow .532,
  positioning .504, leader .511, all .534); at 1h the four layers contribute about equally (.525 .522 .520 .519,
  all .528).
- Raw model scores were slightly overconfident at the extremes; production probabilities pass through a
  calibration map fitted on all out-of-sample forecasts, so a "56%" means "went up about 56% of the time".

## 2. Expected range (68% / 95% bands)

Quantile models of the move size, scaled by recent volatility, with conformal correction.
68% bands covered 66.6–69.0% of outcomes and 95% bands 94.6–95.4% across horizons; they are 4.6–9.5% (68%) and
7–20% (95%) tighter than a plain volatility band for the same coverage, and coverage holds equally for narrow
and wide bands (a plain band covers 80% when narrow and 49% when wide).

## 3. Gold and silver

Binance listed gold (XAUUSDT) in December 2025 and silver (XAGUSDT) in January 2026, so history is short.
- The coin model transfers to gold at 1m (AUC 0.545 over 2026, 0.552 Aug–Oct) but works **against** silver
  (0.479 / 0.444). Metals-only and pooled models were no better.
- A trend-only model trained on 17 years of spot gold and silver (HistData) held up in every year at 4h
  (AUC 0.518, 10/10 years above 0.5), but on Binance 2026 data only 4h passed (gold 0.517, silver 0.530).
- Shown: gold 1m (weak), gold 4h (weak), silver 4h (weak). Everything else for the metals shows **no edge**;
  their ranges are still shown.

## 4. Skill tiers on screen

Per market and horizon: AUC ≥ 0.53 → shown; 0.515–0.53 → shown as "weak"; below → "no edge".
Coins 1m–4h are full tier, 1d weak. Only shown forecasts are scored on the live scoreboard.

## 5. Support and resistance (`research/levels_eval.py`)

Levels are computed exactly as the live server does: swing highs/lows on 15m and 1h bars, prior-day and 7-day
highs/lows and volume nodes from the last 7 days, merged when closer than ~0.12 of a day's typical move.

**Do prices turn at these levels?** Every 4 hours (2024-01 → 2026-10, 8 coins) the nearest resistance and
support were followed for 24 hours. An hour after price first touched them:

| | Touches | Back on the near side after 1h | Arbitrary prices, same distance |
|---|---|---|---|
| Resistance | 41,370 | 52.8% | 53.2% |
| Support    | 41,575 | 53.8% | 54.5% |

The differences (−0.4 and −0.6 points, standard error 0.35) mean the levels do **not** hold better than
arbitrary prices, and stronger levels (more swings, volume, reactions) did no better than weak ones. The
screen therefore shows them as reference prices, with the strength dots labelled "confluence", and says so.

**Reach chances** are measured, not assumed: the chance price trades at least k 68%-bands away within the
horizon (coins, 794,000 samples per horizon). Roughly: half a band away ≈ 60%, one band ≈ 33–36%,
two bands ≈ 9–12%, for every horizon from 15m to 1d. Gold and silver have their own table (59,000 samples).

## 6. What was tried before (previous version)

The removed v1 (commit `33e7d6f`, `docs/BACKTEST.md`) tested a 12/200 EMA scalping method and 21 other
variants. Over 17 years the scalper lost money in 11 of 17 years; the only durable edge found was slow
trend-following on daily/4h bars, with a win rate near 40% and profits coming from a few large trends.
A 90% win rate with a positive profit was not found in any honest test.

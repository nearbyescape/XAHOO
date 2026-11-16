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

## 7. Trying to make the probabilities more accurate (2026-11-16)

Same walk-forward folds and coins as section 1; AUC over 2024-01 → 2026-10 (higher is better, 0.50 = coin flip).

| Idea | 1h AUC | 4h AUC | Verdict |
|---|---|---|---|
| Current model | 0.5330 | 0.5324 | — |
| Whole-market layer (average trend/flow/positioning of the 8 coins, each coin vs the market, breadth) | 0.5306 | 0.5304 | worse — not used |
| Recent data weighted more (half-life 180 days) | 0.5311 | 0.5274 | worse |
| Recent data weighted more (half-life 365 days) | 0.5330 | 0.5303 | no gain |
| Only the last 365 days of training data | 0.5307 | 0.5274 | worse |
| **5 models averaged (different random seeds)** | **0.5346** | 0.5320 | **1h: better in all 5 folds — used** |
| 5 models + 365-day weighting | 0.5346 | 0.5306 | no extra gain |

At 15m: current 0.5357, 5 models averaged 0.5365 (better in all 5 folds — used); recency weighting and the
365-day window were worse there too. 1m and 5m were not re-tested (the 1m set has 2 million rows and the
averaged test would take hours on this machine); they keep the single model.

In production (models version 2026.11.16) the 15m and 1h forecasts come from 5 models averaged, recalibrated
on their own out-of-sample forecasts. 1h, coins pooled: AUC 0.5346, accuracy 52.4%, right 55.3% of the time
when the screen shows 55% or more (18.9% of forecasts).

**Agreement filters** (from the saved out-of-sample forecasts): requiring the other horizons and the market to
lean the same way barely changes the hit rate. 1h forecasts of 55%+ were right 55.2% of the time; when 15m,
4h and the market also agreed, 55.5% — while keeping only 15% of forecasts instead of 18%. Not worth hiding
the rest of the screen for.

What this says: the forecasts are already close to what these inputs can support. Bigger gains would need
new information (for example full order-book history), which the Binance archive does not provide in a form
that can be reproduced live.

## 8. Strong buyers and sellers (descriptive, not part of the forecast)

- **Order-book walls**: every ~15 s the server reads the top 1,000 bids and asks per market and marks bands
  (0.05% wide) holding at least 3× the typical band's resting orders; the screen shows the largest three per
  side with their size, distance and how long they have stood. Resting orders can be pulled at any time.
- **Big trades**: single aggressive trades above a size per market (BTC $250k, ETH $150k, SOL/XRP $60k,
  BNB/DOGE $40k, ADA/LINK $25k, gold $50k, silver $25k), plotted on the chart and summed over 15 minutes.
- **Buyer / seller zones**: 24 h of 1-minute bars split into 48 price bands with aggressive buy and sell
  volume; bands where one side dominated by at least 2× the typical imbalance are marked.

The archive has no order-book levels or single trades in a form that matches the live feed, so these are not
back-tested and are labelled on screen as live context. In replay mode they are simulated and labelled so.

## 9. Accuracy push before launch (2026-11-17)

Every idea below was run through the same walk-forward test (train on the past only, score the 8 screen coins
2024-01 → 2026-10) and adopted only if it helped consistently.

**New information**

| Idea | 5m | 15m | 1h | 4h | 1d | Verdict |
|---|---|---|---|---|---|---|
| Spot-market flow (spot taker buying/selling, spot share of volume, spot–futures basis, who moved first) | 0.5315 → 0.5321 (5/5 folds) | no change | +0.0003 | −0.0011 | +0.003 (3/5) | not adopted: the gain at 5m is 0.06 points and needs a second live feed |
| Futures premium index | +0.0004 | +0.0001 | +0.0003 | −0.0006 | +0.002 | not adopted |
| Training on 16 coins instead of 8 (LTC, BCH, AVAX, DOT, TRX, ATOM, ETC, NEAR added) | −0.0003 | −0.0011 | 0.0000 | −0.0005 | −0.0005 | not adopted |

Spot and futures prices are tied together by arbitrage, so spot flow mostly repeats what futures flow already
shows. More coins did not help either: the limit is how predictable the market is, not how much the model has
seen.

**Model settings** were chosen on the 2024 folds only (slower learning, smaller/bigger trees, fewer inputs per
tree, extra-randomised trees, stronger regularisation) and then checked on 2025-07 and 2026: the 2024 winner
did not hold up at 15m, 1h or 4h; at 5m it was better by 0.05 points, below the noise between random seeds.
Settings unchanged.

**Per-market calibration — adopted.** The single shared calibration leaves each coin with a small bias. A
two-number correction per coin and horizon (fitted on earlier folds, tested on later ones) shrinks the average
gap between the stated probability and what happened, and makes the strong calls more reliable:

| Horizon | Calibration gap (points) | "≥55%" calls right | Share of forecasts ≥55% |
|---|---|---|---|
| 1m | 0.46 → 0.17 | 56.5% → 56.8% | 23% → 20% |
| 5m | 0.39 → 0.22 | 55.3% → 55.6% | 12% → 10% |
| 15m | 0.45 → 0.32 | 55.8% → 56.5% | 15% → 8.5% |
| 1h | 0.82 → 0.26 | 54.9% → 55.3% | 16% → 9% |
| 4h | 1.48 → 0.68 | 54.4% → 54.8% | 19% → 5% |
| 1d | 1.56 → 1.07 | 55.5% → 53.4% | — (not adopted: worse) |

Overall direction accuracy is unchanged (it is the same model); what improves is that the probabilities are
honest per coin, so a strong reading on screen is rarer and more trustworthy. Models version 2026.11.17.

**Where this leaves accuracy.** With everything Binance publishes that can also be read live, the forecasts are
at about 52–53% overall and 55–57% on the strong calls, depending on horizon. The live scoreboard will show
whether that holds after launch.

## 10. Gold and silver re-check with per-market calibration (2026-11-17)

`research/metals_recheck.py`: walk-forward coin-model forecasts (gold/silver never in training), a gold- or
silver-specific calibration fitted on Jan–May 2026, tested on Jun–Oct 2026. Shown only if AUC ≥ 0.515 in both
halves and the calibrated forecast beats a coin flip.

| Horizon | Gold AUC Jan–May / Jun–Oct | Silver AUC Jan–May / Jun–Oct | Result |
|---|---|---|---|
| 1m | 0.547 / 0.543 | 0.529 / 0.434 | gold passes (already shown); silver flips sign |
| 5m | 0.514 / 0.525 | 0.512 / 0.465 | no (gold just short in Jan–May; calibrated probabilities stay within 45–55%) |
| 15m | 0.484 / 0.523 | 0.495 / 0.511 | no (below 0.5 in Jan–May) |
| 1h | 0.504 / 0.522 | 0.499 / 0.506 | no |
| 4h | 0.490 / 0.526 | 0.501 / 0.517 | no (the 17-year trend model, shown as weak, stays) |
| 1d | 0.484 / 0.510 | 0.520 / 0.515 | no (under 1,000 days of samples; calibration fails) |

Gold's later months look better than its early months, which is what a real but still-forming pattern and
plain luck both look like with this little history. The check should be repeated as Binance gold history grows.

**Gold momentum (research/metals_momentum.py).** In Jan–May 2026 gold continued short moves (after a 15-minute
fall the next minute was up only 41.6% of the time), but in Jun–Oct that faded to 48–49.5%. Adding momentum to
the gold calibration lowered the Jun–Oct AUC at 1m from 0.543 to 0.522, so it was not adopted. The screen now
labels the strength of a lean: NEUTRAL within 2 points of 50%, SLIGHT LONG/SHORT for 2–5 points, LONG/SHORT
from 55%.

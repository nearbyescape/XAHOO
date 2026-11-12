# The trader's method (from his posted trades + live stream of 12 Nov 2026)

Sources: 10 trade screenshots shared by the owner (this folder), and the owner-supplied recording of the
"Live Crypto & Gold Analysis — 12 November" stream (83 min, Hindi; transcribed/translated automatically,
so wording is approximate). Quotes are from the machine translation, lightly cleaned.

## Rules as he describes and shows them
1. **Direction first (15m view).** "My opinion is that I am going to sell." Bias decided before the entry.
2. **Counter-moves are liquidity traps.** "This is just to take liquidity… this was just a trap candle… because of this
   trap candle I cannot change my opinion."
3. **Entry on the 5m candle close, with rejection.** "Wait until the candle closes… if this red candle is made, I am
   selling the candle closing here." Looks for long rejection wicks.
4. **Scale in at the EMA12.** "We have to sell around the EMA… if the market comes near this, we will add quantity."
   Starts with 1 lot, adds 1–2 more on the pullback (average-price improvement).
5. **Targets where support/liquidity runs out.** "There is nothing in the market after that — the entire market is empty,
   so it will fall easily." Typical target ≈ $1,200–1,500 per 100 oz.
6. **Stop just beyond the trap/spike high.** Typically $2–6 on gold (screenshots).
7. **Stop to entry early, trail** ("cost to cost").
8. Sessions: streams at 13:00 and 21:00 IST; trades also around 08:00 IST.

## From the second half of the stream (his own statements)
- Claimed accuracy: "The VIP group is 90% of the trade. The live stream is almost 70%."
- Shows losses: "I will never say that I am just profit… 300 loss, 400 loss, 400 loss, 600 loss… targets 1,000, 1,500,
  1,075, 1,200" → losses ≈ $300–600 vs wins ≈ $1,000–1,500 (≈ 2.5 : 1). "Sometimes back to back 10 times loss."
- Selectivity: "90% of the time the market doesn't move… just 10% of the time we execute."
- Filter: "There is a lot of support on the 4-hour time frame, that's why I am not taking the entry here."
- "Risk management is very important… the market can give you big losses."

## His shown results
- 12 Nov 2026 closed trades (shown on stream at 1:00:00): +1,601 · +1,258 · +1,533 · +1,075 · +1,101 · −~675 · −521
  → 5 wins / 2 losses (71%), avg win ≈ $1,310, avg loss ≈ $600 (≈ 2.2 : 1).
- "Last 30 days" P&L on that account: +$20,816.89.
- 10 Nov (screenshot): 2 wins / 1 loss. 3 Nov: breakeven exits (+$3.74, +$3.63) shown as green.
- Size: 100 oz per position, ~$550 risk on ~$17–30k → ~2–3% per position, more when he adds.

## What XAHOO can reproduce (BACKTEST runs 7–8, 11)
Mechanical versions of 1–7 tested on 2024–2026 come out around break-even after spread. The parts that are hard to
encode: *which* impulses he trusts, when he calls a spike a trap versus a real reversal, and when to add.

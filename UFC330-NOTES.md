# UFC 330 — adjudicated reads (written Thu 8/13 night)

Winner column = 16-book consensus (cardread.py). The blend model (age/Elo,
no odds input) disagreed materially on four bouts; each disagreement was
walked back to the records and RESOLVED, not left as a shrug.

## The two flips, resolved

**Gore–Luque (market: Gore 51 / model: Luque 67) — MODEL WRONG, Elo lag.**
Luque since 2022: 3-5, KO'd by Neal and Buckley, subbed by Holland; wins
over Gorimbo, aging RDA, faded Gastelum. The blend still carries his
contender-era rating and cannot see the chin. Trust the market's coin
flip. Skip because 51/49 is a skip. His dec loss to JOEL ALVAREZ (2025)
quietly supports Alvarez -73% over Njokuani.

**Dern–Robertson (market: Dern 65 / model: Robertson 61) — MODEL ONTO
SOMETHING.** Robertson: six straight wins, and in Jan 2026 she BEAT
Amanda Lemos by decision — the same Lemos who beat Dern in 2024. Common-
opponent chain against the market's number; Dern's price is name value.
Sanctioned read: Dern ~60% (market minus the full rule-23 clamp).
Robertson's side is plus-money -> unbettable by standing rule. NOBODY
gets bet here, with reasons on paper.

## The favorites the model runs cool on

Orolbai 88 market / 77 model; Abdul-Malik 83 / 73; Makhachev 75 / 69.
Same Elo-convergence lag in reverse: six-fight careers have not pulled
Elo far from its prior, so risers read underrated. Market likely closer,
BUT for parlay pricing treat the market number as the CEILING: an 88%
leg that might be 80 is how a safe stack rots. Ribovics -700 carries a
form flag besides: two straight losses (sub, dec) before this booking.
Abdul-Malik comes off a KO loss at -720.

## Diagnosis MEASURED (ufc_lag_backtest, 8,686 fights, out of sample)

Confirmed the night it was written: the model underrates short-career
fighters on winning records by +5.7 points (n=733) and overrates 16+
fight careers by -4.8 (n=597). So: Orolbai's model 77 reads as lag (true
nearer the market's 88); Luque's model 67 reads as inflation (true nearer
the market's 49). Both adjudications above now carry a backtest, not a
narrative.

## Diagnosis worth keeping (also in IMPROVE.md)

Blend Elo converges slowly from its prior:
  - long-career fighter in decline -> OVERRATED (Luque)
  - short-career riser -> UNDERRATED (Orolbai)
  - mid-career streak, ~20 fights -> fully credited (Robertson)
Three receipts on one card. When blend and market split by 10+, check
career length + last-8 momentum before trusting either instrument.

## Bettable-by-our-rules Saturday shortlist (prices move; recheck)

Makhachev, Alvarez, Orolbai, D. Johnson (never lost), Ribovics only if
the price cools. Skip: Dern, Gore-Luque, both blind bouts (Eduardo
Henrique da Silva, Lucas Fernando), Turner-Fernandes methods (coin
toss). Method props: posted de-vigged price outranks everything here,
clamp 5pts (rule 27/23).

> **ON-DEMAND MODE since 2026-08-19** (Ryan: "have everything pull when i ask,
> not automatically"). Daily Routines and all workflow cron schedules are OFF.
> Every pull (board, scores, btts, form) fires only from an explicit ask, via
> trigger-file touch or workflow_dispatch. The 8/17 hold and 8/19 lift remain
> in git history.

# Live slips

## Week ledger (running)

## WON — Wed 8/12: 18-leg SGP+ @ +127, all 18 legs

First cash since 8/8. Placed 5:45pm CT at a model 37.2% (slips.py 38.98%,
Frechet band 38.3-42.5) against a 44.1% break-even -- a one-in-three bet that
landed, not an edge discovered.

  9 F5 unders, all top-or-deep rungs
  6 Leagues Cup goal-unders (U6.5 / U7.5)
  3 Double Chances: Orlando (2-2 DRAW), Toluca (3-1), San Diego (3-2)

Orlando is the whole case for rule 8 in one leg: a 2-2 draw cashes the DC and
loses the 3-way moneyline. Closest calls were SEA@NYY at 10 runs through five
against a 10.5 line, and Inter Miami-Leon finishing on exactly 5 goals against
a 6.5 under. CHC@WSH went to 17 total runs and still won on 8 through five --
rule 25's top-rung-only cap earning its keep.

Ryan built the SGP pairing himself; FanDuel priced it 4% ABOVE the naive
product, so the correlation ran in his favour.


| day | staked | back | net |
|---|---|---|---|
| Sat 8/8 | $1,180 | $2,346 | **+$1,166** |
| Mon 8/10 | $657 | $0 | −$657 |
| Tue 8/11 | $150 + 20-leg stake (not recorded) | $0 | −$150−? |

Rule 31 exists so that "not recorded" never appears in this table again:
stake goes into slips.json at placement.

## DEAD — Tue 8/11: all three slips down

**1. 20-leg @ +401 (15 F5 unders + Hasan KO + Wint ML + 3 WNBA)** — dead at
leg 3: CHC@WSH F5 U9.5, 10 runs through five (Washington run in the B5 was
the tenth). The game carried the slate's highest full-game total (U15.5
-1800) — the market had already named it the run-fest. Now rule 25.

**2. DWCS 5-leg, $50 @ boosted +3377 ($1,738.81)** — dead twice over:
Kunneman lost outright, and Escarrega won BY DECISION against a by-KO leg.
Pagliarulo DC and Hasan KO both cashed as legs.

**3. 7-pick, $100 @ +2634 ($2,734.02)** — dead at the same moment: its
Escarrega leg was KO/TKO/DQ +150, killed by the decision at 7:10p. The
banked legs (Pagliarulo KO +240, Hasan KO-R1 -300) and the Wint-R1 leg
were moot from there.

### The fight-card score, market vs my overrides
| leg | market | me | result |
|---|---|---|---|
| Pagliarulo DC | 31% | 49% | WON |
| Kunneman DC | 37% | 53% | lost |
| Hasan KO R1 fade ("worst number on the card") | 71% | 40% | KO R1 — market right |
| Escarrega decision fade | 14% | 9% | decision — market right |

1-for-4 overriding de-vigged prices off search-snippet research. Rules
23-27 written from this. Bright spots that were real: Hasan by KO cashed
(Ryan's call over my early swap-to-ML advice), Pagliarulo DC cashed
(built off Ryan's Mulumba-durability pushback).

## DEAD — Mon 8/10: NYM@ATL F5 Under 8.5 went over, all three slips gone

Three identical 11-leg slips, same spine, placed 2:42p CT.
**$657 staked, $0 back. Net -$657.**

- 2x $50 boosted (+160 boosted 50% to +240, $170.22 each)
- 1x $557 straight @ +160 ($1,449.29)
- Placement: **27.8% true (1 in 3.6)**

| # | CT | leg | price |
|---|---|---|---|
| 1 | 6:07p | BOS@TOR F5 Under 8.5 | -900 |
| 2 | 6:15p | NYM@ATL F5 Under 8.5 | -1000 |
| 3 | 6:40p | BAL@MIN F5 Under 8.5 | -900 |
| 4 | 6:46p | PHI@STL F5 Under 10.5 | -2000 |
| 5 | 7:00p | Atlanta Dream ML | -750 |
| 6 | 8:38p | TEX@LAA F5 Under 8.5 | -1200 |
| 7 | 8:40p | COL@ARI F5 Under 8.5 | -850 |
| 8 | 8:41p | TB@ATH F5 Under 9.5 | -750 |
| 9 | 8:41p | MIL@SD F5 Under 7.5 | -850 |
| 10 | 8:46p | HOU@SF F5 Under 8.5 | -1000 |
| 11 | 9:10p | KC@LAD F5 Under 8.5 | -1600 |

**Leg 2 killed it.** Seven runs in the first (grand slam), 8 by the top of
the 2nd, zero cushion the rest of the way. A home run in the top of the 3rd
put it at 9+ through five. The other early games (BOS@TOR, BAL@MIN,
PHI@STL) were all on zeros and the six late unders never got a chance.

Death path: 27.8% at placement -> 12% after the slam -> 3.8% at 8 runs
after the Braves went quiet in the 2nd -> dead in the top of the 3rd.

### Note for future live grading — Poisson undercounts zeros

Live reads on "need N more runs" were run on Poisson all night, which is
wrong in the direction that matters. Real MLB: **~72% of half-innings are
scoreless**; Poisson at the same run rate says ~62%. Run scoring is
overdispersed — more zeros AND more crooked numbers than Poisson allows.
For a "need zero runs across K halves" ask, use **0.68^K** in a game where
both starters got hit, ~0.72^K in a normal one. It roughly tripled the
number mid-game (2.7% -> 7%) when it mattered.

## SETTLED — Sat 8/8: T1 + T2 BOTH CASHED, $2,346

11-leg all-fight parlays at El Cortez, identical spines.
**T1 $500 @ +231 -> $1,655.17 · T2 $200 @ +246 -> $691.34**

Legs (all won): Stevie McKenna KO1 · Mauro Silva UD · Hassan Azim (T1) ·
Gradus Kraus TKO1 (T2) · Sam Hickey KO7 · Callum Walsh · Ty Miller TKO3 ·
Dainier Pero TKO3 · Yadier DelValle KO1 · Jan Paul Rivera-Pizarro ·
Tammara Thibeault.

Peak-to-cash path: 25% at placement -> 47% after Leeds -> 58% after Ty
Miller -> 70% after Pero -> 76% after Rosado -> paid.

### Same-day losers
- T4 $65 @ +2398 — Boston lost
- T5 $200 @ +3107 — Boston lost
- T6 $100 @ +2340 — baseball leg
- T7 $100 @ ~+1000 — Salkilld finished instead of decisioning
- Daily card $15 @ +79900 — Boston -2
- UFC props $40 @ +4341 — needed Miller BY DECISION (won by TKO) and
  Asplund BY KO (won by decision). Method markets, both ways.

Saturday: $1,180 staked, $2,346 back. **Net +$1,166.**


## Slip A — 20-leg @ +2803 — DEAD Sat 8/8: PSV DREW (3-way ML, a draw loses)

**15/20 won, then PSV drew v Fortuna Sittard. Dead at leg 16 of 20.** The draw risk was flagged and priced at 11.5%; it landed. Liberty won 92-86 Wednesday. 5 open, all Saturday. **True chance ≈32%** (fresh 8/6 14:18 board where priced; Kraus off today's pull, carried at .898 from 8/5; Walsh re-posted ≈-630 per the FD app Thu, de-vig ≈.84).

- [x] Wed 8/5 — New York Liberty ML — WON 92-86
- [x] Fri 8/7 — Saskatchewan Roughriders ML — WON 42-20
- [ ] Sat 8/8 2:00p — PSV Eindhoven ML — -600 · p 0.839 (heavied from -550)
- [ ] Sat 8/8 3:00p — Gradus Kraus (boxing) — off today's pull · carried p 0.898
- [ ] Sat 8/8 4:00p — Aaron McKenna (boxing) — -450 · p 0.797
- [ ] Sat 8/8 ~3:15p — Callum Walsh (boxing, v Denny, Dublin co-feature) — ≈-630 per FD app · p ≈0.84
- [ ] Sat 8/8 8:15p — Ty Miller ML (UFC) — -430 · p 0.790 (heavied from -350)

## Slip C — 22-leg @ +2656 — DEAD Fri night, leg 1 (Cappelozza UD Moldavsky, 29-28 30-27 29-28)

Every Fri+Sat fight/CFL/soccer favorite on the board plus Walsh. All
moneylines; PSV and Sporting are the two 3-ways (a draw kills them). Last
legs ~10p CT Saturday. Ryan is in Vegas all weekend — Nevada blocks
wagering actions including cash-out, so this one rides to the end.
**All six of Slip A's open legs sit inside this slip** — A cannot cash
without C's spine holding, and one shared upset kills both.

- [ ] Fri 7:00p CT — Valentin Moldavsky ML (v Cappelozza, PFL) — -520
- [ ] Fri 7:50p CT — Denis Goltsov ML (v Mezhiev, PFL) — -400
- [ ] Fri 8:00p CT — Saskatchewan Roughriders ML (CFL) — -400 *(also Slip A)*
- [ ] Fri 8:30p CT — Josh Fremd ML (v Gregory, PFL) — -420
- [ ] Fri 9:00p CT — Lewis McGrillen ML (v Lewis, PFL) — -900
- [ ] Sat 6:00a CT — David Nyika (v Masson, boxing) — -600
- [ ] Sat 10:00a CT — Ted Jackson (v Tompkins, boxing) — -2400
- [ ] Sat 12:00p CT — Mauro Silva (v Christopher, boxing) — -450
- [ ] Sat 12:30p CT — Hassan Azim (v Martin, boxing) — -950
- [ ] Sat 1:00p CT — PSV Eindhoven ML 3-way (v Fortuna Sittard) — -650 *(also Slip A)*
- [ ] Sat 1:10p CT — Diego Krasimirov (v Eales, boxing) — -450
- [ ] Sat 2:00p CT — Gradus Kraus (v Hemphill, boxing) — -1100 *(also Slip A)*
- [ ] Sat 2:30p CT — Sporting Lisbon ML 3-way (v Estrela) — -550
- [ ] Sat 3:00p CT — Callum Walsh (v Denny, boxing) — -650 *(also Slip A)*
- [ ] Sat 4:00p CT — Aaron McKenna (v Oliha, boxing) — -410 *(also Slip A)*
- [ ] Sat 5:00p CT — Jan Paul Rivera-Pizarro (boxing) — -2400
- [ ] Sat 6:00p CT — BC Lions ML (CFL, v Hamilton) — -410
- [ ] Sat 7:00p CT — Krystal Rosado (v Yamileth, boxing) — -950
- [ ] Sat 7:15p CT — Ty Miller ML (v Goff, UFC) — -420 *(also Slip A)*
- [ ] Sat 8:00p CT — Dainier Pero (v Whitfield, boxing) — -4500
- [ ] Sat 8:15p CT — Yadier DelValle ML (v Elkins, UFC) — -750
- [ ] Sat 8:50p CT — Tamm Thibeault (v Robinson, boxing) — -450

Times are the FD slip's (CT), which is the authority — the feed's fight
times have been junk all week.

## Slip B — 17-leg @ +4140 — DEAD Wed night (2 legs lost, 10 won)

Killed by **NYM@CLE Under 10.5** (5-5 through nine, Mets won 6-5 in the 10th — 11 runs, the extra frame did it) and **SD@ARI Under 11.5** (D-backs 10-4, a six-run 4th — 14 runs). Everything else hit, for the record:

- [ ] LAA@BAL F5 Under 6.5 — WON (O's HRs in the 4th, ≤3 through five; final 5-2)
- [ ] ATH@CIN Under 13.5 — WON (3-2, 5 runs)
- [ ] NYM@CLE Under 10.5 — **LOST** (6-5 in 10, 11 runs)
- [ ] WSH@PHI F5 Under 8.5 — WON (4-4 through regulation → F5 ≤ 8; final 10-4 in 11)
- [ ] New York Liberty ML — WON (92-86)
- [ ] STL@NYY Under 11.5 — WON (3-1, 4 runs)
- [ ] CWS@BOS F5 Under 6.5 — WON (shutout, 4 total)
- [ ] MIA@ATL Under 11.5 — WON (4-1, 5 runs)
- [ ] PIT@MIL F5 Under 6.5 — WON (1-0 through five; final 4-2)
- [ ] MIN@KC Under 11.5 — WON (2-1, 3 runs)
- [ ] DET@SEA Under 10.5 — WON (4-2, 6 runs)
- [ ] SD@ARI Under 11.5 — **LOST** (10-4, 14 runs)
- Fri legs (Moldavsky, Roughriders, Goltsov, Fremd, McGrillen) — moot, slip dead.

Legs left unticked so the hub's Live tab grades them from the source itself; the checkmark above is reserved for recorded wins on live slips.

## Dead this week

- Slip B, 17-leg @ +4140 — dead Wed 8/5 (above).
- HR trio, 100% boost — lost Tue 8/4.

---
Slip A's week: Roughriders Friday 9:00p ET, then four Saturday legs. If the FD app disagrees with a price here, the app is the truth.

## 16-leg SGP+ W1 — +116 — DEAD Thu 8/13 (lost)

Placed ~12:15pm CT in the noon scramble; killed same evening. **Legs were
never recorded** — rules 29/31 got skipped at placement and the exact legs
lived only in the app screenshot, so no per-leg post-mortem is possible
unless the screenshot resurfaces. Structure: six SGP pairs (match DC or
to-advance + that match's U6.5) + four F5 unders. The stated ~44% carried
~3pts/leg of pre-calibration quote inflation on the six soccer pairs
(hand.py pins the Besiktas measurement); true chance was nearer 36-38%.
placed.py exists as of tonight so a rushed slip can never go unwritten
again.

## UFC330 bonus 4-leg — +2405 — placed 2026-08-14T15:24Z

- [ ] Joel Alvarez by KO/TKO or Submission (v Njokuani) — -150 (model 47.0%)
- [ ] Mansur Abdul Malik by KO/TKO (v Stoltzfus) — -105 (model 40.0%)
- [ ] Kaue Fernandes by KO/TKO (v Turner) — +250 (model 20.0%)
- [ ] Islam Makhachev by Points (v Garry) — +120 (model 35.0%)

## UFC330+boxing 16-leg SGPx A — +1557 — placed 2026-08-14T22:05Z

- [ ] U5.5 Total Goals (Alverca v CF Estrela) — -20000
- [ ] SGP: U5.5 + Tie-or-Porto DC (Porto v Rio Ave) — -900
- [ ] Ashleyann Lozada — -1200
- [ ] Casey Dixon — -2000
- [ ] Jaquan McElroy — -1600
- [ ] Daniel Mercado — -10000
- [ ] Shannel Butler — -1600
- [ ] Myktybek Orolbai — -1050
- [ ] Atif Oberlton — -2000
- [ ] Joel Alvarez — -305
- [ ] Esteban Ribovics — -700
- [ ] Kaue Fernandes to Win by KO/TKO/DQ or Decision — +150
- [ ] Troy Isley — -650
- [ ] Claressa Shields — -3000
- [ ] Islam Makhachev by Decision — +120

## UFC330+boxing 16-leg SGPx B — +2800 — placed 2026-08-14T22:05Z

- [ ] U5.5 Total Goals (Alverca v CF Estrela) — -20000
- [ ] SGP: U5.5 + Tie-or-Porto DC (Porto v Rio Ave) — -900
- [ ] Ashleyann Lozada — -1200
- [ ] Casey Dixon — -2000
- [ ] Jaquan McElroy — -1600
- [ ] Daniel Mercado — -10000
- [ ] Shannel Butler — -1600
- [ ] Myktybek Orolbai — -1050
- [ ] Atif Oberlton — -2000
- [ ] Joel Alvarez — -305
- [ ] Esteban Ribovics — -700
- [ ] Kaue Fernandes to Win by KO/TKO/DQ or Decision — +150
- [ ] Troy Isley — -650
- [ ] Claressa Shields — -3000
- [ ] Ian Machado Garry ML — +285

## UFC330 7-leg C — +3305 — placed 2026-08-15T19:37Z

- [ ] Myktybek Orolbai ML (v Wells) — -687
- [ ] Donte Johnson ML (v McConico) — -251
- [ ] Joel Alvarez ML (v Njokuani) — -241
- [ ] Esteban Ribovics ML (v Barboza) — -504
- [ ] Mansur Abdul Malik ML (v Stoltzfus) — -490
- [ ] Kaue Fernandes by KO/TKO (v Turner) — +227
- [ ] Islam Makhachev by Submission (v Garry) — +217

- [ ] Myktybek Orolbai ML (v Wells) — -687
- [ ] Donte Johnson ML (v McConico) — -251
- [ ] Joel Alvarez ML (v Njokuani) — -241
- [ ] Esteban Ribovics ML (v Barboza) — -504
- [ ] Mansur Abdul Malik ML (v Stoltzfus) — -490
- [ ] Kaue Fernandes by KO/TKO (v Turner) — +227
- [ ] Islam Makhachev by Submission (v Garry) — +217

## UFC330 7-leg D — +2864 — placed 2026-08-15T19:37Z

- [ ] Myktybek Orolbai ML (v Wells) — -813
- [ ] Donte Johnson ML (v McConico) — -270
- [ ] Joel Alvarez ML (v Njokuani) — -258
- [ ] Esteban Ribovics ML (v Barboza) — -572
- [ ] Mansur Abdul Malik ML (v Stoltzfus) — -554
- [ ] Kaue Fernandes by KO/TKO (v Turner) — +221
- [ ] Islam Makhachev by Submission (v Garry) — +211

- [ ] Myktybek Orolbai ML (v Wells) — -813
- [ ] Donte Johnson ML (v McConico) — -270
- [ ] Joel Alvarez ML (v Njokuani) — -258
- [ ] Esteban Ribovics ML (v Barboza) — -572
- [ ] Mansur Abdul Malik ML (v Stoltzfus) — -554
- [ ] Kaue Fernandes by KO/TKO (v Turner) — +221
- [ ] Islam Makhachev by Submission (v Garry) — +211

## Mon 25-leg soccer SGPx — +535 — placed 2026-08-17T17:10Z — **LOST 8/17**

DEAD ~3:50p CT: U5.5 Casa Pia v Benfica went over at 0–7 (~65'). Six legs had banked, Benfica's own DC included. Remaining legs still graded individually for calibration.

- [x] U5.5 Hacken v Halmstads (SGP) — +0 (model 93.4%)
- [x] Hacken And Draw DC (SGP) — +0 (model 89.8%)
- [x] U5.5 Brondby v Sonderjyske (SGP) — +0 (model 95.2%)
- [x] Brondby And Draw DC (SGP) — +0 (model 89.5%)
- [ ] U5.5 Casa Pia v Benfica (SGP) — +0 (model 95.6%)  **<< DEAD 0-7**
- [x] Benfica And Draw DC (SGP) — +0 (model 94.6%)
- [ ] U5.5 Almeria v Eldense (SGP) — +0
- [ ] Almeria And Draw DC (SGP) — +0 (model 88.9%)
- [ ] U5.5 Velez v Defensa y Justicia (SGP) — +0 (model 96.9%)
- [ ] Velez And Draw DC (SGP) — +0 (model 80.4%)
- [ ] U5.5 Pachuca v Puebla (SGP) — +0 (model 95.3%)
- [ ] Pachuca And Draw DC (SGP) — +0 (model 84.5%)
- [ ] U5.5 Internacional v Remo (SGP) — +0 (model 94.7%)
- [ ] Internacional And Draw DC (SGP) — +0 (model 85.6%)
- [ ] U4.5 Felgueiras v AVS Futebol — +0
- [x] U5.5 Arka Gdynia v Puszcza Niepolomice — +0 (model 94.8%)
- [ ] U5.5 AB Argir v Klaksvikar Itrottarfelag — +0
- [ ] U4.5 FK Decic v FK Bokelj — +0
- [x] U4.5 Deportivo v Elche — +0 (model 86.2%)
- [x] U5.5 Cardiff v Wrexham — +0 (model 95.4%)
- [ ] U4.5 Lanus v CA Independiente — +0 (model 93.5%)
- [ ] U4.5 Gimnasia Mendoza v Talleres — +0 (model 93.5%)
- [ ] U5.5 Necaxa v Leon — +0 (model 94.6%)
- [ ] U5.5 Atl Tucuman v Instituto (SATURDAY) — +0 (model 97.1%)
- [ ] U5.5 Sporting Gijon v Burgos (SUNDAY) — +0

## Wed X-0/draw 5-leg — +11045 — placed 2026-08-19T21:04Z — **LOST 8/19**

Died on the 5p window: Cerro-Palmeiras finished 0-1 (draw leg gone), Bragantino won 2-1 in Belo Horizonte (Mineiro DC gone). Atleti X-0 banked 2-0. Scores per Ryan live; feed confirmation pending.

- [ ] Atletico Madrid to win 1-0 2-0 or 3-0 (v Malaga) — +200 (model 33.0%)
- [ ] Draw ML Cerro Porteno v Palmeiras — +220 (model 33.0%)
- [ ] Atletico-MG And Draw DC (v Bragantino) — -280 (model 73.0%)
- [ ] Draw ML Santa Fe v River Plate — +190 (model 32.0%)
- [ ] Draw ML Torque v Tigre — +195 (model 33.0%)

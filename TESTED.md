# What is tested, and what the tests rejected

Everything here was measured out-of-sample on five seasons of nflverse weekly
data (2022-2026), leave-one-player-out, scored by Brier. The point of the file is
that none of it has to be argued about again.

## The two things I priced every prop with, both wrong

**A player's own hit rate at the posted number over-predicts**, and worst at the
volumes we actually bet:

| trailing targets | over-prediction |
|---|---|
| under 4 | −1.5 pts |
| 4 to 6 | **+5.8** |
| 6 to 8 | **+8.2** |
| 8 or more | **+11.8** |

Juwan Johnson read 77% on his own 13 games against a 61.5% price; the tested
number was 61%. Brock Purdy read 42% over two seasons against 33.6%; his career
was 24%. Both were this bias, not insight.

**The defensive matchup is worth about 15% of its face value.** Tested as
`cal * (1 + alpha*(defence_rate/league_rate - 1))`, Brier bottoms out at
alpha=0.15 for receiving and 0.30 for rushing. At alpha=1.0 — which is what
"rank on the weaker of form and matchup" amounts to — it is **worse than
ignoring the defence entirely**: 0.1477 against 0.1373 at receptions 3.5.

## What the model does instead

Projection = trailing volume x trailing efficiency, over the games this team's
**current starter** played, decayed with a five-game half-life. Then into an
empirical bucket of comparable projections, bias-corrected by volume band,
nudged 15% toward the matchup and 50% toward the game environment.

Brier, five seasons:

| | own rate | calibration | shrunk | cal + bias |
|---|---|---|---|---|
| receptions 3.5 | .1451 | .1373 | .1388 | **.1371** |
| rec yards 69.5 | .0789 | .0735 | .0747 | **.0734** |
| rush yards 87.5 | .0817 | .0820 | — | **.0814** |

CAL+B wins 19 of 21 bars. **Shrinking the own rate toward the calibration is
worse than dropping it entirely** — once the projection is known, the player's
own history at that bar adds nothing.

## Where the model has no skill at all

Skill = the fraction of a base-rate guess's error the model removes.

| stat | 0-10% | 10-30% | 30-60% | 60%+ |
|---|---|---|---|---|
| receptions | +0.9% | +7.5% | +28.8% | +46.1% |
| receiving yards | +0.6% | +4.5% | +21.3% | +32.1% |
| rushing yards | +1.4% | +7.9% | +28.3% | +23.2% |
| passing yards | +4.5% | +19.5% | +42.2% | +8.4% |
| carries | +0.4% | +14.6% | +41.5% | +4.2% |

Bands are `|projection − bar| / projection`. **Inside 10% the model knows
nothing** — and that is exactly where a book posts its main line, because it sets
the number at the projection on purpose. Every main-line edge is noise.

## The two instability gates

**Role drift** — `|share of team volume over his last 3 games − over the earlier
ones|`, refused above 0.103. Brier is 64% worse for the shifting third at
receptions 3.5, 91% worse at 4.5.

**Cast change** — `1 − Jaccard overlap of the top three OTHERS taking his
position group's volume`, recent three games against earlier, refused above 0.50
**but only when his own share is under 15%**. Above 22% share he is the focal
point and turnover around him predicts nothing:

| his share of team targets | effect of a changed cast |
|---|---|
| under 8% | +17% worse |
| 8-15% | +16% worse |
| 15-22% | −3% |
| over 22% | +3% |

The first version gated everyone and removed Drake London at 31% share. Kamara
at 9% is who it is for: four of his six games with Shough shared a backfield with
Devin Neal, two with Travis Etienne.

## The game environment

| RB clearing 87.5 rushing, by his team's spread | |
|---|---|
| −14 (heavy dog) | 6% |
| pick'em | 12% |
| +14 (heavy favourite) | 15% |

| WR clearing 84.5 receiving, by game total | |
|---|---|
| 33-point game | 4% |
| 45 | 6% |
| 54-point game | 10% |

Receiving keys off the total, rushing off the spread. Alpha 0.50.

## REJECTED — do not add these back

- **Venue.** Splitting the calibration by home/away makes it worse (.1366 →
  .1370; rushing .0809 → .0826). The Atlanta home/road split that killed a
  night's worth of picks was a small-sample artifact.
- **Position split.** .1366 → .1369.
- **Snap share.** Snap *trend* is flat across falling/flat/rising (.1220 /
  .1247 / .1297 — rising is slightly worse). Snap *level* correlates only
  because low-snap players never clear the bar. Volume is already downstream of
  being on the field, so the projection contains it.
- **Output recalibration.** Fitted on 2022-2024 and tested on 2025-2026, both a
  linear and a binned map are worse than leaving the probability alone at every
  bar. The 5-point reliability errors are small-n noise.
- **Opponent adjustment at face value.** See above — actively harmful.
- **Shrinkage toward the calibration.** Worse than dropping the own rate.

## Week of season

Skill is lower early, and more so for rushing:

| | wk 1-6 | wk 7-11 | wk 12-18 |
|---|---|---|---|
| receptions 3.5 | +25.8% | +28.9% | +30.4% |
| receiving yards 69.5 | +21.1% | +18.4% | +20.7% |
| rushing yards 69.5 | +13.2% | +17.9% | +22.1% |

It is week 4, so every edge on the current board is modestly overstated — about
15% relatively on receptions, around 40% on rushing. Not enough to flip a
direction; enough that a +12 should be read as a +10.

## Settled parameters

Bucket width ±15% and a 30-row minimum are both already optimal. Four prior
games is right: skill is flat from 2-3 through 10-15 and *drops* past 16, because
long samples span role changes.

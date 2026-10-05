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

---

# Session 2026-10-05, week 4: the injury report, and the touchdown market

## The injury report was never read

score2.py priced lines for players who were ruled out. What a designation is
worth, 2022-2025, every designated skill player with four prior games, measured
against **his own** trailing six-game volume so a star being a star does not read
as health:

| report status | listings | played | play % | volume when he played | production |
|---|---|---|---|---|---|
| Out | 399 | 0 | **0.0%** | — | — |
| Doubtful | 25 | 0 | **0.0%** | — | — |
| Questionable | 328 | 196 | **59.8%** | 95.1% | 102.5% |
| on the report, no designation | 904 | 783 | 86.6% | 103.2% | 107.2% |

Out and Doubtful are absolute — 0 of 424. Those lines are refused outright.

Questionable splits by practice, but **not usefully**: Limited 61.2% (n=209),
Full 58.2% (n=67), Did Not Participate 51.2% (n=43). The ordering is sensible and
the samples are too thin to act on. Conditional on playing, a Questionable player
is **himself** — 98.5% of his usual volume on the Limited line. So the cost of
Questionable is not a diminished player, it is a **40% chance of no game at all**.
That does not make the price wrong, so it is priced and flagged, never refused.

This mattered immediately: Noah Fant was the **top edge on the week-4 board**
(Over 3.5 receptions, +370) while listed Questionable with an abdomen injury.

## Missing linebackers are worth about three yards

The Saints played week 4 without Kaden Elliss (77, 58, 70 defensive snaps — every
snap of all three games), Carl Granderson (59/39/36, a declining share that says
the ankle was already bothering him) and Anfernee Jennings (18/17/18), with Pete
Werner questionable and not practising. Every 2026 Saints defensive rate was
recorded by a unit that no longer existed — the same contamination that made
"Saints allow 15 of 20 under 87.5" wrong.

So the effect was measured league-wide instead. 2,174 defence-games, 2022-2025,
each game de-meaned within its own defence-season, bucketed by the share of the
season's linebacker snaps missing. Top decile = 47% of the room gone:

| | mean, vs that defence's own average | games above its own average |
|---|---|---|
| RB rushing yards | **+3.48** | 108/218 — a coin flip |
| RB carries | +0.37 | 115/218 |
| RB receptions | −0.02 | 96/218 |
| TE receptions | −0.15 | 92/218 |
| TE receiving yards | **−1.69** | 86/218 |
| yards per carry | 4.487 vs 4.297 | +0.19 |

The quartile pattern is non-monotonic (−1.17, +0.29, −2.41, +3.16, +3.48), which
is what noise looks like; a real dose-response climbs. A paired within-defence
version agreed: with two or more of the top four linebackers out, RB rushing
*fell* 3.0 yards over 39 defence-seasons.

**A defence missing half its linebacker room gives up about three and a half
rushing yards and a fifth of a yard per carry. Nothing else moves, and tight ends
do slightly worse, not better.** "They're missing their linebackers" is not an edge.

## And missing pass rushers makes the opponent pass LESS

Same design on the four highest-snap front-seven players. Top decile of
depletion, against that defence's own average: opposing passing yards **−9.50**
(86/218 above average), attempts −1.11, WR receiving yards −9.51.

The mechanism is game script, not defence: a team facing a depleted front seven is
usually ahead, so it runs and stops throwing. That also explains the small rushing
bump above. Per-play efficiency barely moves.

(A `sacks` column in that first run was summed from a key that does not exist —
the field is `sacks_suffered`. It printed 0.00 for all 218 games. It was not a
measurement and is not reported.)

## Anytime touchdown: 10.2% skill, and a hard ceiling

Of 1,415 lines in a one-game sweep, score2.py prices 183. `player_anytime_td` —
the most-bet prop in football — was ungraded. `anytd.py` now grades it.
16,380 player-games, 2022-2025, base rate 20.3%:

| method | Brier | skill over base |
|---|---|---|
| base rate for everyone | .16200 | 0.0% |
| his own rate of scoring games | .15922 | 1.7% |
| his own touchdowns per touch | .15044 | 4.0% |
| **shrunk rate, calibrated** | **.14554** | **10.2%** |

Leave-one-**player**-out gives .14556 — the same 10.2%, so nothing leaks through
his own rows.

**The rate cannot be his own.** Touchdowns per touch from a player's own history
projected **4,517 of 16,380 player-games at zero** — 28% of the board declared
impossible — because a back with no touchdown in three games has a measured rate
of exactly 0.000. Drake London, Alvin Kamara, Kyle Pitts and Jahan Dotson all
came out at 0.0% for week 4. Shrinking toward the position's league rate by
pseudo-touches, tuned not chosen:

| pseudo-touches | 0 | 10 | 25 | 50 | 100 | **200** | 400 |
|---|---|---|---|---|---|---|---|
| Brier | .15044 | .14834 | .14701 | .14606 | .14561 | **.14554** | .14570 |
| projected at ~zero | 4517 | 278 | 276 | 274 | 274 | 274 | 274 |

League touchdowns per touch: RB .0304 (one every 32.9), **TE .0519 (one every
19.3)**, WR .0478 (one every 20.9) — a tight end scores on a touch *more* often
than a receiver.

**The ceiling.** The top projection bucket scored 55.5% (n=364) and no bucket
reaches 60%. Predicted tracks actual within 1.1 points everywhere, so this model
needs no bias correction — unlike the yardage one:

| projection | n | predicted | actual |
|---|---|---|---|
| 0.00-0.08 | 3113 | 4.4% | 5.5% |
| 0.08-0.15 | 3673 | 11.4% | 11.0% |
| 0.15-0.25 | 4074 | 19.9% | 19.4% |
| 0.25-0.35 | 3171 | 29.6% | 30.1% |
| 0.35-0.50 | 1985 | 40.9% | 40.7% |
| 0.50-1.01 | 364 | 55.0% | **55.5%** |

**So an anytime price of −150 or worse cannot be right about anyone.** No
player-game profile in four seasons has a true rate above ~56%. The model caps
there and says so.

## Rejected: requiring games from the current season

The sixth feature to be refused by its own measurement. A projection built
entirely on last season was expected to be worse. It is not:

| prior games from the current season | n | skill over base |
|---|---|---|
| none — all of it last season | 812 | **11.1%** |
| one | 802 | 11.4% |
| two | 796 | 6.7% |
| three or four | 3344 | 10.9% |
| five or more | 11630 | 10.1% |

Flat at 10-11% everywhere. Kevin Austin Jr. stays on the board at +1300 on a
projection with one 2026 appearance in it, because there is no measured reason to
refuse him. What the model cannot tell you is whether he gets those 4.5 touches
tonight — that is a depth-chart question, not a calibration question.

## What anytd.py still does not know

Nothing in it is aware of how many points a team is expected to score. Atlanta
has five offensive touchdowns in three games; the model reads only each player's
touches and the league rate per touch. A team expected to score twice and one
expected to score five times get identical treatment at equal volume. It also has
no red-zone term, so four screen touches and four goal-line touches look the same.
**Its biggest claimed edges sit at the longest prices, which is exactly where
those two gaps bite hardest.** There are no historical prices here, so none of
this has been backtested against a closing line: the 10.2% is probability
accuracy, not demonstrated profit.

## A rule in main() is a rule nothing checks — the fourth time

`anytd.py` shipped its starter filter inside `main()`. Two mutations escaped
until it was extracted to `starter_games()`. The previous three were
`spec in COMPARE`, the history-unavailable line, and the score2 gates.

The mutation harness itself was also wrong: a search string that does not appear
leaves the file unchanged, the suite passes, and the run prints **caught** for a
rule nothing tests. It now reports that case as BROKEN. That is what the
long-standing "history not sorted" MISS actually was.

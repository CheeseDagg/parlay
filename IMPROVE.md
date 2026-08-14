# Improvement backlog — measured gaps, largest first

The continuous-improvement pass (1pm CT Routine) takes the TOP item, finishes
it end to end (measure -> build -> selftest -> ship -> report), moves it to
DONE with the number that justified it, and re-sorts what remains. An item
with no measurable payoff written next to it does not belong on this list.

## OPEN
1. **Finish the 8/14 field audit** (fields carried, read by NO report):
   fighter_bouts.csv's kd/kd_abs (chinhist) and sig_l/sig_a, td_l/td_a
   (defhist) are now SHIPPED. STILL unused there: ctrl (control seconds)
   and the sub column. ufc_ratings still hides
   finish_rounds, finishes, best_wins, physical, style8, archetype,
   legkick, strike_location/position, model_score, vs_avg_pct,
   overall_pct, ranked/recent ratings. MLB slate raw_total is unused
   (raw vs adj IS the park+weather adjustment). f5hist histogram unused.
   Payoff: measured, not assumed -- the kd_abs pass found the audit's own
   headline claim was WRONG, which is worth more than shipping it.
1. **Cross-market SGP correlation library**: FanDuel priced DC+under 4% ABOVE
   naive product once (n=1). Collect every SGP quote Ryan screenshots vs our
   naive product in a csv; after n>=20, fit the haircut per pairing type.
2. **Veteran-side blend correction** (16+ fights overrated ~6 pts out of
   sample): the term REFUSED to derive on 2021-23 -- signal too weak. Needs
   another season before retrying; until then the stated distrust rule
   stands. Do not force a constant.
4. **F5 rung x posted-line conditioning** (WAITING ON ITS OWN DATA): history
   is measured-absent -- srcprobe round 3 showed sportsbookreviewsonline is
   an affiliate shell now, every archive path serves the same marketing page,
   zero file links. So linelog.py records our own: every refresh snapshots
   the board's MLB alt-total rungs, last pregame look wins, started games
   never overwrite. Revisit when the csv holds ~2 months of dates; until
   then there is nothing to fit.

## DONE (the number that justified it)
- edge.py: every totals leg vs its OWN history (52,710 soccer closing-odds
  matches, 6,681 first-fives with parks, 321 CFL games), sorted by
  measured-minus-implied, with the model's hot-game read DISQUALIFYING
  league-base unders (its first live run ranked TEX@ATH F5 unders top of
  the MLB list while hot_games had the game at adj 10.04 -- the gate
  caught the tool). Both ends print: candidates AND traps. First live
  scan flagged legs the board's own candidate tickets carry: Alavés-
  Getafe U4.5 -4500 reads 11 points above its league table, and the
  shallow MLS overs read 9-15 points high, consistent with the 0-0
  lesson. Form scorelines print beside every soccer row because the
  league base does NOT transfer to teams like Inter Miami [1,5,10,2,8].
  13/13.
- Strength-of-schedule + activity as blend features: REFUSED, and the
  refusal is the finding. Ryan called Orolbai-Wells (SoS +20.7 pct, 4
  fights/24mo vs 1, Wells 287d idle) and every fact checks out -- but as a
  model term across 8,439 age-complete bouts, career mean-opponent-Elo
  scores +0.00056 holdout / 3-3 periods against a BEST-OF-24-PLACEBO of
  +0.00051, and activity scores +0.00063 against a best placebo of
  +0.00117 -- a shuffled column beating the real one outright. Last-5
  opponent Elo was NULL before it got that far. The power probe shows why
  the 3/3 meant little: with the effect genuinely planted at the fitted
  strength, the pipeline recovers a robust win in 1 panel of 3. Elo
  already pays for beating good fighters, so SoS is mostly priced before
  the term sees it. Nothing shipped; the placebo harness is permanent and
  carries the verdicts so neither gets re-proposed off one card.
- Striking rates, measured: on 3,897 bouts with prior career on both sides,
  against prior win rate, on an untouched 2019+ tail -- strikes ABSORBED
  per minute ADDS (p=0.048, accuracy 57.2 -> 58.6%) and striking ACCURACY
  ADDS (p=0.048) but is worth under a point of win probability, so it is
  printed and never leaned on. The rate every preview quotes -- striking
  DEFENCE % -- was REFUSED: negative gain out of sample, ladder not even
  monotone (42/47/54/47/54). Takedown defence has a clean monotone ladder
  (44.9 -> 57.8%) and still missed the bar at p=0.095; printed, not priced,
  and recorded as refused so it is not re-proposed. Fixing the antisymmetry
  the selftest caught (the fit was buying the alphabetically-first corner a
  standing edge) was the difference between a matchup model and an artefact.
  12/12 + 37/37.
- Chin, measured instead of assumed: the 8/14 audit called kd_abs "a better
  chin proxy" than counting finishes in losses. It is NOT. Out of sample on
  5,170 untouched bouts it LOSES to the naive proxy solo (0.43403 vs
  0.43295) -- but it ADDS to it (joint 0.43193), and none of 20 shuffles of
  kd_abs alone came near that gain (best null +0.00005 vs real +0.00102,
  p=0.048). So both print and neither is called better. The pass also found
  a second thing nobody asked for: "never been dropped" is worth 14.1% on
  under an hour of tape and 8.7% on 150+ minutes, so a rate is now read on
  its own EXPOSURE ladder -- Kaue Fernandes' 38 minutes reads 14%, not the
  pooled 12.5% that flattered a chin nobody has tested. 15/15 + 26/26.
- LIVE gate: Ernesto Mercado sat on Saturday's ticket at 95.6% for hours
  after FanDuel took the whole bout down between the 14:27 and 18:07 pulls.
  Fifteen gates read the leg as written; none re-read the board. Now one
  does -- and it caught its own false positive on its first live run (an
  app-quoted rung under a self-named group is confirmed at FIXTURE level,
  not failed as vanished). 79/79.
- Board ships past a bad quote: 8/14 noon refresh FAILED entirely because one
  degenerate 3-way derived a 99.88% DC @ -102284 -- nothing committed, board
  froze at 11:20a on a night Ryan was betting, and the 4pm/6:30pm runs would
  have died the same way. Degenerate groups are now quarantined and NAMED;
  the other ~1,200 legs ship. 52/52.
- Career-length blend correction: +0.25 logits for 3-8-fight sides on 70%+
  last-5 wins, derived 2021-23 and verified on untouched 2023-26 -- the
  short-winning flag cleared (+6.6 -> +1.8) and Brier improved 0.2322 ->
  0.2306. The veteran term refused to derive; recorded, not guessed.
- socform carries per-match SCORELINES: an average of 2.6 goals hides a 4-3.
  Ryan 8/14: "recommend them because they are going to go under". 17/17.
- fightprops.py: a posted method ladder de-vigs WHOLE (6-outcome power,
  rule 30) instead of leg-by-leg with the assumed 2% one-sided haircut --
  and the first ladder measured why that mattered: the haircut is
  price-dependent, ~11% on the favourite outcome to ~73% on a +3000.
  A flat 2% was structurally wrong, and so would be a mean; lone quotes
  now price off the haircut at their price level. Also prints each
  fighter's method-market win% beside the pin's moneyline consensus, so
  a repriced ladder shows its drift instead of absorbing it. 10/10.
- cflhist: 321 of ~324 games 2022-25 from per-team Wikipedia pages, every
  game cross-checked against BOTH teams' tables (one real page disagreement
  caught and excluded). CFL was the only carried sport with zero grounding.
  The build process itself proved the discipline: the first parse silently
  lost every game after July (abbreviated months) and let preseason leak
  in -- mean total 48.6 vs the true 51.48, U49.5 said 56% when it is 46.7%.
  A 9-point lie on the most bettable rung, caught by dumping the real rows
  (round 4d) before trusting the parser. Odds history measured-absent on
  every probed route; linelog-style self-collection is not worth it for a
  sport bet a few times a season -- the results base is the deliverable.
- WNBA monthly probe workflow: the market-only declaration re-tests itself
  first Monday each month and prints a build-wnbahist verdict if any route
  opens. Closed by machinery instead of memory.
- Widget form panel: Wins-by split + Durability row (NEVER FINISHED
  highlighted) on every fighter card, from the method data already inside
  the page. Shipping it exposed a second bug and fixed it: the refresh gate
  skipped rebuilds when prices were unchanged, so template changes could
  not reach readers until the market moved -- the 259-hours bug mirrored.
  Render inputs now hash into the publish decision.
- sgplog.py: SGP quotes -> correlation rows, refuses to fit under n=20, and
  refused its own first seed (a whole-slip quote logged against three legs).
- solve2 --hand: UEFA legs solved, not assembled (8/13 took five manual
  re-solves). One market per real match via token join, so a pasted DC and
  total can never stack. The smoke test caught the solver's defaults doing
  worse than the feature: THREE shallow Over-0.5s and WNBA totals in one
  six-leg build. Both now default-excluded (0-0 is 5-9% real vs ~1% implied;
  'no wnba totals' 8/13), --allow flags to restore. Retired --power/--mult:
  they printed a de-vig that was no longer in force.
- hand legs through the gates: kickoff tokens ("@ 7:30pm", rollover-safe),
  STALE fails a started app-quoted leg and WARNs a tokenless one BY NAME,
  and the fixture found a real hole -- TIE matched only the tie-name's
  second half, so favourite-named hand legs walked past rule 40. Gate fixed.
- soclive.py: the Hammarby arithmetic computed one way (9/9 against the 8/13
  trajectory). The tested model says the red-card state was ~29%, not the
  ~17% improvised live -- ad-hoc numbers ran 12 points hot under pressure.
- MLBTool pre-dawn cron: both morning passes ran before the earliest slate
  build EVERY day by construction (8/13: slate stale until 14:38Z). 08:37Z
  cron lands the board ~04:50 CT, ahead of both.
- hand.py paste-parser: pasted FanDuel lines -> de-vigged legs in one command
  (2-way mult / 3-way power / DC 0.80 factor), typo'd pastes refused on vig
  bands. Found its own justifying number in its fixtures: the 8/13 to-advance
  legs were quoted ~3 points high (97.8 vs a measured 94.4 on Besiktas).
- Per-family de-vig: MLB mult 1.35 vs power 4.46; soccer power 0.68 vs mult
  1.24; NFL power 1.47 vs mult 1.94. Overround shape decides.
- Empirical F5 ladder + park table (6681 games; Coors U10.5 85.8% vs AmFam 96.4%).
- Soccer league priors 40347 matches + 52710 with closing odds; Argentina
  draw 30.2% / 2.23 goals.
- Form: MLB starters (Nola 2.89 confirmed), soccer teams (Sparta 0.17 caught),
  UFC last-5 with win-by/lose-by (Garry: never finished).
- NFL grounded preseason: spread->winprob table, ML/totals reliability.
- 12 preflight gates; routines rewired to the almanac; PAT triggers deleted.

# Improvement backlog — measured gaps, largest first

The continuous-improvement pass (1pm CT Routine) takes the TOP item, finishes
it end to end (measure -> build -> selftest -> ship -> report), moves it to
DONE with the number that justified it, and re-sorts what remains. An item
with no measurable payoff written next to it does not belong on this list.

## OPEN
0b. **UFC-ODDS widget form panel**: the phone widget Ryan and his friend use
   Saturday shows model-vs-odds but none of ufcform's last-5 / win-by /
   lose-by. Surface it per bout. Payoff: 'Garry has never been finished' on
   the screen where the method props get picked.
2. **Cross-market SGP correlation library**: FanDuel priced DC+under 4% ABOVE
   naive product once (n=1). Collect every SGP quote Ryan screenshots vs our
   naive product in a csv; after n>=20, fit the haircut per pairing type.
3. **F5 rung x posted-line conditioning**: f5hist has rung x park; the sharper
   split is rung x the game's own posted main line (market's info, then the
   empirical tail past it). Needs historical F5 lines -- probe if any source
   carries them before promising it.
5. **WNBA retry monthly**: all routes dead 8/13 (stats timeout, ESPN/data 403).
   Re-probe first Monday each month; if a route opens, build wnbahist mirroring
   nflhist. Until then the coverage.json market-only note stands.
6. **CFL history**: fixturedownload 404'd; find results+odds source before a
   CFL leg is ever priced above a hunch.

## DONE (the number that justified it)
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

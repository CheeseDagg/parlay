# Improvement backlog — measured gaps, largest first

The continuous-improvement pass (1pm CT Routine) takes the TOP item, finishes
it end to end (measure -> build -> selftest -> ship -> report), moves it to
DONE with the number that justified it, and re-sorts what remains. An item
with no measurable payoff written next to it does not belong on this list.

## OPEN
1. **UEFA screenshot workflow**: on Europa/Conference nights the feed is
   structurally blind (no catalog key). Build a paste-parser: Ryan pastes the
   app's DC/total prices as text or screenshot transcription, a script de-vigs
   each with devig_n, writes them into a hand.py feed file the board merges
   with an (app-quoted) tag. Kills the 3-hour scramble of 8/13 permanently.
2. **Cross-market SGP correlation library**: FanDuel priced DC+under 4% ABOVE
   naive product once (n=1). Collect every SGP quote Ryan screenshots vs our
   naive product in a csv; after n>=20, fit the haircut per pairing type.
3. **F5 rung x posted-line conditioning**: f5hist has rung x park; the sharper
   split is rung x the game's own posted main line (market's info, then the
   empirical tail past it). Needs historical F5 lines -- probe if any source
   carries them before promising it.
4. **Live win-prob for soccer** (live.py is MLB-only): a Hammarby-style
   in-match DC number from score+minute+red-card state, Poisson with the
   sococalib league lambdas. Selftest against the 8/13 Hammarby trajectory.
5. **WNBA retry monthly**: all routes dead 8/13 (stats timeout, ESPN/data 403).
   Re-probe first Monday each month; if a route opens, build wnbahist mirroring
   nflhist. Until then the coverage.json market-only note stands.
6. **CFL history**: fixturedownload 404'd; find results+odds source before a
   CFL leg is ever priced above a hunch.

## DONE (the number that justified it)
- Per-family de-vig: MLB mult 1.35 vs power 4.46; soccer power 0.68 vs mult
  1.24; NFL power 1.47 vs mult 1.94. Overround shape decides.
- Empirical F5 ladder + park table (6681 games; Coors U10.5 85.8% vs AmFam 96.4%).
- Soccer league priors 40347 matches + 52710 with closing odds; Argentina
  draw 30.2% / 2.23 goals.
- Form: MLB starters (Nola 2.89 confirmed), soccer teams (Sparta 0.17 caught),
  UFC last-5 with win-by/lose-by (Garry: never finished).
- NFL grounded preseason: spread->winprob table, ML/totals reliability.
- 12 preflight gates; routines rewired to the almanac; PAT triggers deleted.

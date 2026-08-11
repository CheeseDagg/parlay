# Standing rules

Read this before building anything. These are Ryan's, not suggestions, and
every one of them was paid for. Where a rule has a date, that is the day the
loss that created it landed.

## Bet construction

1. **FanDuel only.** Every parlay prices there. Other books are for
   comparison, never for the slip.
2. **Nothing lighter than -350 on any leg.** No exceptions, including
   "it's only one leg."
3. **No plus-money legs.** Ever.
4. **Hit probability over value.** Verbatim: *"i'm only looking for bets
   that are going to hit. not good value."* Do not pitch +EV longshots.
5. **No pitcher or hitter props.** The K ladder is deliberately empty.
6. **No MLB moneylines** (`--nofam=ML`). Totals and F5 unders only.
7. **The less baseball the better.** Baseball is the fallback, not the plan.
8. **Never 3-way soccer moneylines — Double Chance only.** *(8/11, after
   PSV drew v Fortuna Sittard 8/8 and killed a 20-leg slip sitting at
   15/20.)* A draw is a real outcome with real probability and it loses a
   3-way outright. The feed carries 3-way only, so derive DC: de-vig all
   three outcomes with `devig_n`, then DC = 1 - p(underdog). The derived
   number is fair value; FanDuel prints shorter, especially past -1500.
   Always say so rather than quoting the derived price as a quote.
9. **Method-of-victory props are a distinct failure mode.** "Wins" and
   "wins by KO" are different bets. A UFC props slip died 8/8 needing
   Miller BY DECISION (won by TKO) and Asplund BY KO (won by decision) —
   both legs right on the winner, both lost.
10. **At a fixed target price, fewer legs beats more legs.** Five at -407
    is 30.9% for +200; twenty at -1771 is 24.6% for the same +200. Adding
    legs to reach a number strictly lowers hit chance.

## Reporting

11. **Yes/no questions get "Yes" or "No" as the first word.**
12. **Concise means tables and short lines.** Never make him scroll left to
    right on a phone. Keep tables to 3-4 narrow columns.
13. **Pushback stays technical** — arithmetic, correlation, data quality.
    Never moralize about betting.
14. **Never present feed-only output as "the heaviest available."** The
    feed has missed real, heavier markets repeatedly: Callum Walsh -630,
    Plymouth -1100, Stevie McKenna, Sam Hickey. Say "this is the feed" and
    treat it as a floor, not a ceiling.
15. **Always convert times to CT explicitly.** The container runs UTC and
    `astimezone()` with no argument returns UTC, which looks like a local
    time and is not. This shipped a whole Monday afternoon of times an hour
    wrong and he caught it by seeing a grand slam before my stated first
    pitch. Build the CT tzinfo by hand.
16. **Never call a game before it happens.** "It looks like they're going
    to give up 9" is not "they gave up 9."

## Live grading

17. **Do not use Poisson for "need N more runs."** It undercounts zeros
    badly. Real MLB: ~72% of half-innings are scoreless; Poisson at the
    same run rate says ~62%. Run scoring is overdispersed — more zeros AND
    more crooked numbers than Poisson allows.
    - Need zero runs across K half-innings: **0.72^K** normally,
      **0.68^K** in a game where both starters have been hit.
    - This understated a live leg threefold (2.7% vs a real ~7%) on 8/10.
18. **F5 is not settled at the middle of the 5th.** The home half can still
    lose an under. `selftest-parlay.js` pins this.
19. **"Under 8" and "Under 7.5" are the same bet** on a whole-number board.
    Don't say a rung doesn't exist because the label differs.

## Working agreement

20. He pings, you check — except for the scheduled morning runs he asked
    for, which do research passes ahead of build passes so nothing like Ben
    Rice's 0-for-14 surfaces after he's already placed.
21. All work lands on `main` so the site, BOARD.md and the scheduled runs
    share one branch.
22. Never print tokens. Pipe push output through
    `sed -E 's/(github_pat_[A-Za-z0-9_]+)/***/g'`.

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

## Fight cards (added 8/12, paid for on 8/11)

23. **The de-vigged price is the number. Research adjusts it ±5 points, no
    more.** On 8/11 I overrode the market by 10+ points four times, on
    fighters I knew only through search snippets. Score: 1-for-4 (Pagliarulo
    DC won; Kunneman DC lost, the Hasan-R1 fade lost, the Escarrega-decision
    fade lost). Search-summary research is for choosing among fairly priced
    legs and for vetoing legs — it does not mint double-digit edges.
24. **Retired: "DWCS fighters chase finishes, so shade decisions down."**
    Two of five fights on the 8/11 card went the distance. This adjustment
    talked Ryan off Escarrega by decision at +600. It cashed.
25. **F5 rung selection follows the game's run environment, not a uniform
    price target.** *(Corrected same night: the first version of this rule
    keyed on "FG total 14.5+", which was a LADDER TOP, not the game total —
    most games post a U15.5 rung. The real quantities:)* a game is HOT when
    the model's park/weather-adjusted total is **10 or higher**, or sits
    **1.5+ runs above the market's main line** (heat the market hasn't
    priced). CHC@WSH on 8/11: adj 10.52 — hottest of fifteen games — against
    a market main of just 8.5. Its F5 U9.5 died on 10-through-five and
    killed a 20-leg slip, while the flag sat unread in MLBTool's slate.json
    all day. Hot games are F5 **top rung only**, or off the card. Enforced
    in code: `board.hot_games()`, applied by default in solve2 (`--nohot`
    lifts), surfaced in BOARD.md. Requires a FRESH slate — run
    `git -C ../MLBTool pull` every morning; the board banners when it's
    stale.
26. **One answer per fight.** State the range once, pick once, stop moving
    the number with each new snippet. On 8/11 I moved Kunneman four times
    and flipped the lightweight pick twice; Ryan called it out both times.
    When the evidence is thin, say "55, plus or minus 10" — do not
    re-litigate.
27. **When the pick is the WINNER, the default instrument is the moneyline
    or the KO-or-points double chance — never a single method.** Method
    legs are where slips die (rule 9, and again 8/11: Escarrega by KO lost
    to Escarrega winning on points; KO-or-points at -105 would have
    cashed). Narrow to one method only when Ryan explicitly wants payout
    over hit rate, and say what it costs.
28. **Before a second slip goes in, report the overlap.** Name every shared
    leg and the probability that one event kills the whole night. On 8/11
    the Escarrega decision took out two slips at 7:10p ($150 of stakes on
    one fight's method), and Hasan+Wint sat on both big tickets all night
    (35% chance of a dead night by 7:30p, computed only after both were
    placed). Compute it BEFORE.
29. **Every quoted probability goes in calibration.csv at placement, and
    gets an outcome at settle** — date, leg, de-vigged market p, my p,
    won/lost. Seeded 8/12 with the eight verified 8/10-8/11 rows. This file
    is the only way "my numbers beat the market" ever becomes a checkable
    claim instead of a mood; rules 23 and 27 came from its first eight rows
    (overrides past five points: 1-for-4). `python3 calibration.py` prints
    the scoreboard; the clamp loosens only when its edge line goes positive.
30. **Live reads run through `python3 live.py`, not hand arithmetic.**
    `--line --runs --state [--outs] [--hot]` — it is rule 17's math with
    rule 18's half-inning accounting, and it exists because the same
    numbers were derived by hand, message by message, two nights running,
    once with the wrong distribution.
31. **A slip goes into slips.json when it is PLACED.** slips.py has computed
    cross-slip kill probabilities since 8/1 — and graded nothing on 8/10 or
    8/11 because nobody fed it. The tool was never the gap; the habit was.

## Working agreement

20. He pings, you check — except for the scheduled morning runs he asked
    for, which do research passes ahead of build passes so nothing like Ben
    Rice's 0-for-14 surfaces after he's already placed.
21. All work lands on `main` so the site, BOARD.md and the scheduled runs
    share one branch.
22. Never print tokens. Pipe push output through
    `sed -E 's/(github_pat_[A-Za-z0-9_]+)/***/g'`.

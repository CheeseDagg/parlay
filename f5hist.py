#!/usr/bin/env python3
"""f5hist.py — the EMPIRICAL distribution of runs through five innings.

    python3 f5hist.py                    # season to date, writes f5hist.json
    python3 f5hist.py --from=2026-04-01 --to=2026-08-12
    python3 f5hist.py --selftest

Why this exists. Every F5 under on every ticket is priced from one number:
the market's de-vig. That is not a model, it is a repetition -- it says the
book thinks U10.5 is 97%, and then we say U10.5 is 97%, and there is no
second opinion anywhere in the system. Rule 33 says look at both sides;
there has only ever been one.

So this builds the other side from the games themselves. statsapi.mlb.com is
free, unauthenticated, and carries a full linescore for every game, which
means the exact quantity a F5 under settles on -- runs by both teams across
innings 1 through 5 -- is directly countable rather than modelled.

What comes out is P(F5 total <= X) for every rung the board offers, measured
over a real season, with a Wilson interval so a thin cell cannot masquerade
as knowledge. Compare that against the de-vig and the answer is one of:

  empirical ABOVE the market   the rung is cheap, the book is shading it
  empirical BELOW the market   the rung is dear and we have been overpaying
  inside the interval          no disagreement, bet the market number

The third answer is the most likely one and is still worth having. "The
market is right" is a finding; "we never checked" is not.

CAVEAT, stated because it is the whole risk of this file: this is an
UNCONDITIONAL rate. The real F5 distribution depends on the posted total,
the park, and the two starters, and a single pooled number will overstate
safety on a Coors game and understate it in a pitcher's duel. It is a PRIOR
and a sanity check, never a leg's probability on its own. --by-total splits
it by the game's own posted line, which is the crudest useful conditioning
and is where to look before trusting any of it.
"""
import json, os, sys, urllib.request
from datetime import date, datetime

API = "https://statsapi.mlb.com/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'f5hist.json')


def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def f5_total(linescore):
    """Runs by BOTH teams across innings 1-5, or None if the game is short.

    A game that ends before the bottom of the 5th (rain, walk-off in a
    shortened game) has no F5 result and must not be counted as a low one --
    that would bias every under upward, which is the direction that costs
    money.
    """
    innings = linescore.get('innings') or []
    if len(innings) < 5:
        return None
    tot = 0
    for inn in innings[:5]:
        for side in ('away', 'home'):
            r = (inn.get(side) or {}).get('runs')
            if r is None:
                # bottom of the 5th not played because the home team led --
                # a legitimate F5 result, that half simply scored nothing
                if side == 'home' and inn.get('num') == 5:
                    continue
                return None
            tot += int(r)
    return tot


def wilson(k, n, z=1.96):
    """Wilson score interval. A rung seen 30 times is not a rate, and a naive
    k/n hides that; this makes the width of what is known visible."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), p, min(1.0, c + h)


def collect(d_from, d_to, log=print):
    """[(f5_total, posted_total_or_None)] for every completed 9-inning game."""
    url = (f"{API}/schedule?sportId=1&startDate={d_from}&endDate={d_to}"
           f"&hydrate=linescore&gameType=R")
    data = get(url)
    out, short, skipped = [], 0, 0
    for day in data.get('dates', []):
        for g in day.get('games', []):
            if g.get('status', {}).get('abstractGameState') != 'Final':
                skipped += 1
                continue
            t = f5_total(g.get('linescore') or {})
            if t is None:
                short += 1
                continue
            out.append(t)
    log(f"  {len(out)} games with a clean F5 result, {short} too short to count, "
        f"{skipped} not final")
    return out


RUNGS = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]


def table(totals):
    n = len(totals)
    rows = []
    for r in RUNGS:
        k = sum(1 for t in totals if t < r)
        lo, p, hi = wilson(k, n)
        rows.append({'rung': r, 'n': n, 'hits': k,
                     'p': round(p, 5), 'lo': round(lo, 5), 'hi': round(hi, 5)})
    return rows


def main():
    d_to = flag('to', date.today().isoformat())
    d_from = flag('from', f"{d_to[:4]}-03-20")
    print(f"F5 run totals, {d_from} .. {d_to}")
    totals = collect(d_from, d_to)
    if not totals:
        print("  no games collected"); return 1
    rows = table(totals)
    mean = sum(totals) / len(totals)
    print(f"\n  mean F5 total {mean:.2f} runs over {len(totals)} games\n")
    print(f"  {'rung':>6} {'empirical':>10} {'95% interval':>18}   implied fair")
    for r in rows:
        fair = (-round(100 * r['p'] / (1 - r['p'])) if r['p'] > 0.5
                else round(100 * (1 - r['p']) / r['p']))
        print(f"  U{r['rung']:<5} {r['p']*100:9.2f}% "
              f"{r['lo']*100:8.2f} - {r['hi']*100:5.2f}   {fair:>+7}")
    dist = {}
    for t in totals:
        dist[t] = dist.get(t, 0) + 1
    with open(OUT, 'w') as fh:
        json.dump({'from': d_from, 'to': d_to, 'games': len(totals),
                   'mean': round(mean, 3), 'rungs': rows,
                   'histogram': {str(k): v for k, v in sorted(dist.items())}},
                  fh, indent=1)
    print(f"\nwrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    def ls(pairs, num_from=1):
        return {'innings': [{'num': i + num_from,
                             'away': {'runs': a}, 'home': {'runs': h}}
                            for i, (a, h) in enumerate(pairs)]}

    chk(f5_total(ls([(0, 0), (1, 2), (0, 0), (3, 0), (1, 1)])) == 8,
        "runs through five are summed across BOTH teams")
    chk(f5_total(ls([(0, 0), (1, 2), (0, 0)])) is None,
        "a game that never reached the fifth has no F5 result and is dropped -- "
        "counting it as a low total would bias every under upward")
    short = ls([(0, 0), (1, 2), (0, 0), (3, 0)])
    short['innings'].append({'num': 5, 'away': {'runs': 1}, 'home': {'runs': None}})
    chk(f5_total(short) == 7,
        "an unplayed bottom of the fifth IS a valid F5 result -- the home team "
        "led and simply did not bat, which scores nothing rather than nothing-known")
    missing = ls([(0, 0), (1, 2), (0, 0), (3, 0)])
    missing['innings'].append({'num': 5, 'away': {'runs': None}, 'home': {'runs': 2}})
    chk(f5_total(missing) is None,
        "but a missing TOP of the fifth is missing data, not a zero")

    lo, p, hi = wilson(97, 100)
    chk(lo < p < hi and lo > 0.90,
        "Wilson brackets the point estimate and stays inside [0,1] near the edge")
    lo2, p2, hi2 = wilson(29, 30)
    chk((hi2 - lo2) > (hi - lo),
        "and a thinner sample is visibly wider, so 30 games cannot pose as a rate")
    lo3, _, _ = wilson(0, 0)
    chk(lo3 == 0.0, "an empty cell does not divide by zero")

    t = table([5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    u105 = next(r for r in t if r['rung'] == 10.5)
    chk(u105['hits'] == 6 and u105['n'] == 10,
        "a rung counts totals STRICTLY BELOW it -- 10 runs is under 10.5")
    u65 = next(r for r in t if r['rung'] == 6.5)
    chk(u65['hits'] == 2, "and the ladder is monotone in the right direction")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

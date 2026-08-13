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
import json, math, os, sys, urllib.request
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
    """[{f5, away, home, venue, date}] for every completed game.

    The pooled number answers "what is an F5 under worth on an average game",
    which is not the question anyone actually has. Carrying the identity of the
    game is what lets the same data answer "what is it worth on THIS one" --
    the whole point of rule 25 existing and, on 2026-08-13, of it not firing:
    CIN@CWS modelled at 9.13, below the hot threshold, and put up 12 runs
    before the fifth.
    """
    # ONE SEASON IS NOT ENOUGH POWER, so this chunks by year and pools. With
    # ~120 games per team the dispersion test only reliably detects a team at
    # THREE TIMES the league blowup rate; a team genuinely twice as wild is
    # missed four times out of five. That is not "teams do not differ", it is
    # "one season cannot tell", and the two get reported very differently.
    # Three seasons roughly triples the per-team sample. Chunked because a
    # multi-year schedule request is large enough to time out.
    days = []
    y0, y1 = int(d_from[:4]), int(d_to[:4])
    for y in range(y0, y1 + 1):
        a = d_from if y == y0 else f"{y}-03-01"
        b = d_to if y == y1 else f"{y}-11-15"
        url = (f"{API}/schedule?sportId=1&startDate={a}&endDate={b}"
               f"&hydrate=linescore,team,venue&gameType=R")
        try:
            days += get(url).get('dates', [])
        except Exception as e:
            log(f"  {y}: {type(e).__name__} -- season skipped")
    out, short, skipped = [], 0, 0
    for day in days:
        for g in day.get('games', []):
            if g.get('status', {}).get('abstractGameState') != 'Final':
                skipped += 1
                continue
            t = f5_total(g.get('linescore') or {})
            if t is None:
                short += 1
                continue
            tm = g.get('teams') or {}
            out.append({
                'f5': t,
                'away': ((tm.get('away') or {}).get('team') or {}).get('abbreviation', '?'),
                'home': ((tm.get('home') or {}).get('team') or {}).get('abbreviation', '?'),
                'venue': (g.get('venue') or {}).get('name', '?'),
                'date': day.get('date', ''),
            })
    log(f"  {len(out)} games with a clean F5 result, {short} too short to count, "
        f"{skipped} not final")
    return out


def by_key(games, keyf, label, floor=40, top=12):
    """P(F5 >= 11) and mean F5, grouped -- who actually produces the blowups.

    A blowup is what kills a deep under, and the pooled 6% rate is useless for
    deciding whether to take one on a specific game. If the rate is flat across
    teams then the leg is a coin the schedule cannot help you weight; if it is
    concentrated, the pooled number is hiding the only thing worth knowing.
    """
    import collections
    g = collections.defaultdict(list)
    for x in games:
        for k in keyf(x):
            g[k].append(x['f5'])
    rows = []
    for k, v in g.items():
        if len(v) < floor:
            continue
        blow = sum(1 for t in v if t >= 11)
        lo, p, hi = wilson(blow, len(v))
        rows.append({'k': k, 'n': len(v), 'mean': sum(v) / len(v),
                     'blow': p, 'lo': lo, 'hi': hi})
    rows.sort(key=lambda r: -r['blow'])
    # IS THIS SIGNAL OR IS IT THIRTY COINS? With 30 groups and a 95% band, one
    # or two WILL clear it by chance, and the top of a sorted leaderboard is the
    # single most likely place for noise to look like a finding. So before any
    # row gets read as a tendency, ask whether the spread across groups is
    # bigger than binomial noise alone would produce. Pearson chi-square on the
    # blowup counts against the pooled rate, df = groups - 1.
    base = sum(1 for x in games if x['f5'] >= 11) / len(games)
    chi = sum((r['blow'] * r['n'] - base * r['n']) ** 2 / (base * (1 - base) * r['n'])
              for r in rows)
    df = len(rows) - 1
    # Wilson-Hilferty: chi-square -> standard normal, good enough past df~10 and
    # avoids needing scipy in a file that otherwise has no dependencies.
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / ((2 / (9 * df)) ** 0.5)
    pv = 0.5 * math.erfc(z / math.sqrt(2))
    print(f"\n  {label} -- P(F5 total >= 11), league base rate {base*100:.2f}%")
    print(f"  dispersion across {len(rows)} groups: chi2={chi:.1f} df={df} "
          f"p={pv:.3f}  -> {'REAL spread' if pv < 0.05 else 'CONSISTENT WITH NOISE'}")
    print(f"  {'':<26}{'n':>5} {'mean F5':>9} {'blowup':>8} {'95% band':>15}")
    for r in rows[:top] + [None] + rows[-3:]:
        if r is None:
            print(f"  {'...':<26}")
            continue
        print(f"  {str(r['k'])[:25]:<26}{r['n']:>5} {r['mean']:>9.2f} "
              f"{r['blow']*100:>7.2f}% {r['lo']*100:>6.2f}-{r['hi']*100:5.2f}")
    return rows


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
    games = collect(d_from, d_to)
    totals = [g['f5'] for g in games]
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
    teams = by_key(games, lambda x: (x['away'], x['home']),
                   'BY TEAM (each game counts for both)')
    venues = by_key(games, lambda x: (x['venue'],), 'BY VENUE', floor=50, top=8)
    dist = {}
    for t in totals:
        dist[t] = dist.get(t, 0) + 1
    with open(OUT, 'w') as fh:
        base = sum(1 for t in totals if t >= 11) / len(totals)
        json.dump({'from': d_from, 'to': d_to, 'games': len(totals),
                   'mean': round(mean, 3), 'rungs': rows,
                   'blowup_base': round(base, 5),
                   # Saved so the board can USE them, not only so a human can
                   # read them. A venue multiplier of 2.3 (Coors) or 0.34 (Rate
                   # Field) against a 6.2% base is the difference between a
                   # deep F5 under being the safest leg available and being the
                   # one that ends the ticket.
                   'venue': {str(r['k'][0] if isinstance(r['k'], tuple) else r['k']):
                             {'n': r['n'], 'mean': round(r['mean'], 3),
                              'blowup': round(r['blow'], 5),
                              'mult': round(r['blow'] / base, 3) if base else None,
                              'lo': round(r['lo'], 5), 'hi': round(r['hi'], 5)}
                             for r in venues},
                   'team': {str(r['k']): {'n': r['n'], 'blowup': round(r['blow'], 5),
                                          'mult': round(r['blow'] / base, 3) if base else None}
                            for r in teams},
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

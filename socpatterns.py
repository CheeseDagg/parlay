#!/usr/bin/env python3
"""socpatterns.py — what is happening consistently, across every club on file.

    python3 socpatterns.py            # rank every live streak and split
    python3 socpatterns.py --selftest

THE FIRST VERSION OF THIS ANSWERED THE WRONG QUESTION. It rendered six
signals for a fixture you had to name, which only helps once you already
know where to look. A signal is the opposite: something a club is doing
CONSISTENTLY, surfaced without being asked about that club.

So this scans every club in socextra's five leagues and reports the runs and
splits that are actually live, ranked by how unlikely each is against its own
league's base rate.

RARITY IS COMPUTED, NOT ASSERTED. A run of k matches at league rate p is
p**k. Quoting that alone would be dishonest, because we look at hundreds of
club-and-pattern combinations at once and the longest run in a big sample is
supposed to look unlikely. Every report therefore carries the EXPECTED number
of runs that long across everything scanned, so a "1 in 300" that turns up
when 400 chances were examined reads as what it is: ordinary.

AND A STREAK IS NOT A FORECAST. These are descriptions of results already
played. Nothing here establishes that a run continues, and the page says so
out loud, because "seven unders in a row" is exactly the shape that reads as
a prediction when it is only a history.
"""
import json, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'socextra.json')
OUT = os.path.join(HERE, 'socpatterns.json')

MIN_RUN = 3          # below this, nothing is remarkable
GOAL_LINE = 2.5
MIN_SIDE = 4         # matches needed on each side before a split is a split
SPLIT_GAP = 1.00     # points-per-game gap that makes a home/away split notable


def timeline(dated):
    """{club: [(date, gf, ga, opp, side)]} in date order, oldest first."""
    by = defaultdict(list)
    for d, h, a, hg, ag in sorted(dated):
        by[h].append((d, hg, ag, a, 'H'))
        by[a].append((d, ag, hg, h, 'A'))
    return by


def run_of(rows, pred):
    """Length of the CURRENT run satisfying pred, counting back from newest."""
    n = 0
    for r in reversed(rows):
        if pred(r):
            n += 1
        else:
            break
    return n


def ppg(rows):
    pts = sum(3 if gf > ga else (1 if gf == ga else 0) for _d, gf, ga, _o, _s in rows)
    return pts / len(rows) if rows else 0.0


def league_rates(dated):
    """Base rates measured on THIS league, never borrowed from another."""
    n = len(dated)
    if not n:
        return {}
    under = sum(1 for _d, _h, _a, hg, ag in dated if hg + ag < GOAL_LINE) / n
    # Per-club-appearance rates: each match contributes two appearances.
    apps = 2 * n
    cs = sum((1 if ag == 0 else 0) + (1 if hg == 0 else 0)
             for _d, _h, _a, hg, ag in dated) / apps
    fts = sum((1 if hg == 0 else 0) + (1 if ag == 0 else 0)
              for _d, _h, _a, hg, ag in dated) / apps
    btts_no = sum(1 for _d, _h, _a, hg, ag in dated if hg == 0 or ag == 0) / n
    draws = sum(1 for _d, _h, _a, hg, ag in dated if hg == ag)
    wins = (n - draws) / n
    # NOT 0.5. Every match makes one winner and one loser, or two draws, so per
    # club-appearance P(does not lose) = (n + draws) / 2n -- and P(does not win)
    # is the same by symmetry. Hardcoding a coin flip here overstated rarity
    # enormously: at Peru's 24% draws the honest figure is 0.62, so a 21-match
    # winless run reads 1 in 21,000 rather than the 1 in 2,097,152 that 0.5**21
    # produces. That is the difference between 'remarkable' and 'a bad team'.
    nolose = (n + draws) / (2 * n)
    return {'under': under, 'over': 1 - under, 'cs': cs, 'fts': fts,
            'btts_no': btts_no, 'decisive': wins,
            'unbeaten': nolose, 'winless': nolose}


def rarity(p, k):
    """1-in-N for a run of k at per-match probability p."""
    if not (0 < p < 1) or k <= 0:
        return None
    x = p ** k
    return (1.0 / x) if x > 0 else None


PATTERNS = [
    # (key, category, predicate, base-rate key, sentence)
    ('under',    'Goals',     lambda r: r[1] + r[2] < GOAL_LINE, 'under',
     'under {line} in {k} straight'),
    ('over',     'Goals',     lambda r: r[1] + r[2] > GOAL_LINE, 'over',
     'over {line} in {k} straight'),
    ('cs',       'Defence',   lambda r: r[2] == 0, 'cs',
     'clean sheet in {k} straight'),
    ('fts',      'Attack',    lambda r: r[1] == 0, 'fts',
     'failed to score in {k} straight'),
    ('btts_no',  'Goals',     lambda r: r[1] == 0 or r[2] == 0, 'btts_no',
     'both teams did NOT score, {k} straight'),
    ('unbeaten', 'Form',      lambda r: r[1] >= r[2], 'unbeaten',
     'unbeaten in {k}'),
    ('winless',  'Form',      lambda r: r[1] <= r[2], 'winless',
     'winless in {k}'),
    ('wins',     'Form',      lambda r: r[1] > r[2], 'decisive',
     'won {k} straight'),
    ('losses',   'Form',      lambda r: r[1] < r[2], 'decisive',
     'lost {k} straight'),
]


def scan_league(league, entry):
    """Every live run and split in one league, plus how many chances were looked at."""
    dated = [tuple(x) for x in (entry.get('dated') or [])]
    if not dated:
        return [], 0
    base = league_rates(dated)
    tl = timeline(dated)
    out, chances = [], 0

    for club, rows in tl.items():
        if len(rows) < MIN_RUN:
            continue
        newest = rows[-1][0]
        for key, cat, pred, bkey, sentence in PATTERNS:
            chances += 1
            k = run_of(rows, pred)
            if k < MIN_RUN:
                continue
            p = base.get(bkey)
            r = rarity(p, k)
            ev = [{'date': d, 'gf': gf, 'ga': ga, 'opp': o, 'side': s}
                  for d, gf, ga, o, s in rows[-k:]][::-1]
            out.append({
                'league': league, 'club': club, 'category': cat, 'key': key,
                'text': sentence.format(k=k, line=GOAL_LINE),
                'k': k, 'base': round(p, 4) if p else None,
                'one_in': round(r) if r else None,
                'newest': newest, 'evidence': ev[:8]})

        # Home/away split: a club that is a different team at home is a
        # standing fact, not a run, so it is measured over the whole season.
        hm = [r for r in rows if r[4] == 'H']
        aw = [r for r in rows if r[4] == 'A']
        chances += 1
        if len(hm) >= MIN_SIDE and len(aw) >= MIN_SIDE:
            gap = ppg(hm) - ppg(aw)
            if abs(gap) >= SPLIT_GAP:
                strong, weak = ('home', 'away') if gap > 0 else ('away', 'home')
                out.append({
                    'league': league, 'club': club, 'category': 'Home/Away',
                    'key': 'split',
                    'text': (f'{ppg(hm):.2f} ppg at home vs {ppg(aw):.2f} away '
                             f'— {abs(gap):.2f} stronger {strong}'),
                    'k': min(len(hm), len(aw)), 'base': None, 'one_in': None,
                    'gap': round(gap, 3), 'newest': rows[-1][0], 'evidence': []})
    return out, chances


def expected(rows, chances):
    """How many runs this rare we'd EXPECT from chance alone, given how many
    club-and-pattern combinations were examined. Without this the longest run
    in a large sample always looks like a discovery."""
    for r in rows:
        if r.get('one_in'):
            r['expected_by_chance'] = round(chances / r['one_in'], 2)
            r['notable'] = r['expected_by_chance'] < 1.0
        else:
            r['expected_by_chance'] = None
            r['notable'] = abs(r.get('gap') or 0) >= SPLIT_GAP
    return rows


def build(doc):
    rows, chances = [], 0
    for league, entry in (doc or {}).items():
        got, ch = scan_league(league, entry)
        rows.extend(got)
        chances += ch
    rows = expected(rows, chances)
    # Rarest first; splits (no rarity) sort by gap beneath them.
    rows.sort(key=lambda r: (-(r['one_in'] or 0), -abs(r.get('gap') or 0)))
    return {'chances': chances, 'patterns': rows}


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    # Six matches, all low-scoring, one club on a long under run.
    dated = []
    # Two high-scoring matches between other clubs keep the league's under-rate
    # off 1.0; a base rate of exactly 1 makes a run unremarkable by definition
    # and rarity correctly refuses to score it.
    for i, (h, a, hg, ag) in enumerate([
            ('Alpha', 'B', 1, 0), ('C', 'Alpha', 0, 1), ('Alpha', 'D', 1, 0),
            ('E', 'Alpha', 0, 0), ('Alpha', 'F', 2, 0), ('G', 'Alpha', 1, 1),
            ('B', 'C', 3, 2), ('D', 'E', 4, 1)]):
        dated.append((f'2026-0{i+1}-01', h, a, hg, ag))
    doc = {'L': {'dated': [list(x) for x in dated]}}

    tl = timeline(dated)
    chk(len(tl['Alpha']) == 6, 'a club appears once per match, home or away')
    chk([r[0] for r in tl['Alpha']] == sorted(r[0] for r in tl['Alpha']),
        'the timeline is oldest-first so runs count back from the newest')

    res = build(doc)
    P = {(r['club'], r['key']): r for r in res['patterns']}
    chk(('Alpha', 'under') in P, "Alpha's under run is found")
    chk(P[('Alpha', 'under')]['k'] == 6, f"and is 6 long, got {P[('Alpha','under')]['k']}")
    chk(P[('Alpha', 'under')]['evidence'][0]['date'] == '2026-06-01',
        'evidence leads with the NEWEST match')
    lr = league_rates(dated)
    chk(abs(lr['unbeaten'] - (len(dated) + 2) / (2 * len(dated))) < 1e-9,
        'the unbeaten base is MEASURED from the draw rate, never hardcoded to 0.5')
    chk(rarity(1.0, 5) is None,
        'a pattern that happens in every match scores no rarity -- it is not a signal')
    chk(('Alpha', 'unbeaten') in P and P[('Alpha', 'unbeaten')]['k'] == 6,
        'an unbeaten run is found over the same matches')
    chk(('Alpha', 'losses') not in P, 'a run that is not happening is not reported')

    r = P[('Alpha', 'under')]
    chk(r['one_in'] and r['one_in'] >= 1, f"rarity is computed, got {r['one_in']}")
    chk(r['expected_by_chance'] is not None,
        'every rarity carries how many such runs chance alone would produce')
    chk(res['chances'] >= len(PATTERNS),
        'the number of chances examined is counted and reported')

    # The look-elsewhere correction must actually demote a common run.
    common = {'league': 'L', 'one_in': 4, 'gap': 0}
    demoted = expected([common], chances=400)[0]
    chk(demoted['expected_by_chance'] == 100.0 and not demoted['notable'],
        'a 1-in-4 run across 400 chances is NOT notable (100 expected)')
    rare = expected([{'league': 'L', 'one_in': 2000, 'gap': 0}], chances=400)[0]
    chk(rare['expected_by_chance'] == 0.2 and rare['notable'],
        'a 1-in-2000 run across 400 chances IS notable (0.2 expected)')

    # Home/away split needs enough matches on BOTH sides.
    thin = {'L': {'dated': [['2026-01-0%d' % i, 'X', 'Y', 3, 0] for i in range(1, 6)]}}
    sp = [r for r in build(thin)['patterns'] if r['key'] == 'split']
    chk(not sp, 'a club with no away matches yields no home/away split')

    base = league_rates(dated)
    chk(0 < base['under'] <= 1, 'league base rates are measured on this league only')
    chk(rarity(0.5, 3) == 8.0, 'rarity of a 3-run at 50% is 1 in 8')
    chk(rarity(0, 3) is None and rarity(0.5, 0) is None, 'degenerate inputs return None')

    chk(build({})['patterns'] == [], 'an empty source yields no patterns, not a crash')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


def main():
    try:
        doc = json.load(open(SRC))
    except Exception as e:
        print(f'socpatterns: cannot read socextra.json ({type(e).__name__})')
        return 1
    res = build(doc)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    pats = res['patterns']
    note = [p for p in pats if p.get('notable')]
    print(f"socpatterns: {len(pats)} live patterns from {res['chances']} chances examined; "
          f"{len(note)} clear the look-elsewhere bar")
    for p in pats[:18]:
        odds = f"1 in {p['one_in']:,}" if p.get('one_in') else f"gap {p.get('gap')}"
        exp = p.get('expected_by_chance')
        tail = f"  [{odds}; {exp} expected by chance]" if exp is not None else f"  [{odds}]"
        print(f"  {'*' if p.get('notable') else ' '} {p['club'][:22]:22} "
              f"{p['text'][:44]:44} {p['league'][:18]:18}{tail}")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

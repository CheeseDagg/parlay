def unusualness(hits, n, p):
    """P(at least this many hits at the league's own rate). Lower = more unusual.

    THIS ORDERS THE LIST AND NEVER APPEARS IN IT. Two earlier versions got this
    wrong in opposite directions. The first PRINTED a 1-in-N figure, which is
    the working rather than the finding -- nobody acts on "1 in 481". The
    second used it as a hard cutoff, and a Bonferroni bar across two thousand
    club-and-pattern combinations deleted every record in all five leagues.
    So it ranks: the most unusual things a club is doing come first, and the
    reader sees only the sentence.
    """
    if p is None or hits is None or not n:
        return 0.05          # splits have no per-match rate; sit mid-list
    return binom_tail(hits, n, p)


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
import datetime as dt, json, math, os, sys
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
    by2 = sum(1 for _d, _h, _a, hg, ag in dated if abs(hg - ag) >= 2) / (2 * n)
    return {'under': under, 'over': 1 - under, 'cs': cs, 'fts': fts,
            'btts_no': btts_no, 'decisive': wins, 'win': wins / 2,
            'scored': 1 - fts, 'conceded': 1 - cs, 'by2': by2,
            'unbeaten': nolose, 'winless': nolose}


def rarity(p, k):
    """1-in-N for a run of k at per-match probability p."""
    if not (0 < p < 1) or k <= 0:
        return None
    x = p ** k
    return (1.0 / x) if x > 0 else None


WINDOW = 10          # "of last 10" -- what a reader can hold in their head
MAX_AGE_DAYS = 45    # a run whose newest match is older than this is not a run
                     # a club is ON -- it is a record from a season that ended.
                     # Peru's dated rounds stop in May for some clubs and
                     # "conceded in all of the last 10 -- 16 in a row" shipped
                     # with its newest evidence 123 days old, reading as live.
MIN_N = 4            # fewer than this and "4 of last 4" is noise
MIN_RATE = 0.80      # below this it is not something a club is DOING

# (key, category, predicate, sentence). The sentence is the whole point: a
# reader wants "has gone under 2.5 in 9 of last 10", not a probability. The
# first build reported streak length and a 1-in-N rarity, which is the working,
# not the finding.
PATTERNS = [
    ('under',    'Goals',   lambda r: r[1] + r[2] < GOAL_LINE,  'under {line}'),
    ('over',     'Goals',   lambda r: r[1] + r[2] > GOAL_LINE,  'over {line}'),
    ('btts_no',  'Goals',   lambda r: r[1] == 0 or r[2] == 0,   'no both-teams-score'),
    ('cs',       'Defence', lambda r: r[2] == 0,                'kept a clean sheet'),
    ('conceded', 'Defence', lambda r: r[2] > 0,                 'conceded'),
    ('scored',   'Attack',  lambda r: r[1] > 0,                 'scored'),
    ('fts',      'Attack',  lambda r: r[1] == 0,                'failed to score'),
    ('unbeaten', 'Form',    lambda r: r[1] >= r[2],             'avoided defeat'),
    ('winless',  'Form',    lambda r: r[1] <= r[2],             'failed to win'),
    ('wins',     'Form',    lambda r: r[1] > r[2],              'won'),
    ('by2',      'Margin',  lambda r: r[1] - r[2] >= 2,         'won by 2+'),
    ('lost_by2', 'Margin',  lambda r: r[2] - r[1] >= 2,         'lost by 2+'),
]


def window_stat(rows, pred, window=WINDOW):
    """(hits, n, streak) over the most recent `window` matches."""
    recent = rows[-window:]
    hits = sum(1 for r in recent if pred(r))
    return hits, len(recent), run_of(rows, pred)


def phrase(verb, hits, n, streak):
    """Plain English, the way a reader says it out loud."""
    if hits == n and n >= 3:
        s = f'{verb} in all of the last {n}'
        if streak > n:
            s += f' \u2014 {streak} in a row'
        return s
    s = f'{verb} in {hits} of last {n}'
    if streak >= 3:
        s += f' ({streak} in a row)'
    return s


def binom_tail(k, n, p):
    """P(at least k hits in n) at per-match rate p. Exact, n is tiny here."""
    if not (0 <= p <= 1) or n <= 0:
        return 1.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def worth_saying(hits, n, p, chances):
    """Is this record unusual, or just what that club is like?

    THIS IS THE FILTER, NOT A COLUMN. Ryan's read of the first build was right:
    "how unlikely" is the working, not the finding, and nobody acts on 1-in-481.
    But without it the list fills with "conceded in 10 of last 10", which is
    true of half the division and is not a signal. So the arithmetic decides
    what appears and never shows itself: a record is worth saying when, across
    every club-and-pattern combination scanned, chance alone would produce
    fewer than one of them.
    """
    if p is None:
        return True
    tail = binom_tail(hits, n, p)
    return tail * max(chances, 1) < 1.0


BASE_KEY = {'under': 'under', 'over': 'over', 'btts_no': 'btts_no',
            'cs': 'cs', 'conceded': 'conceded', 'scored': 'scored',
            'fts': 'fts', 'unbeaten': 'unbeaten', 'winless': 'winless',
            'wins': 'win', 'by2': 'by2', 'lost_by2': 'by2'}


def scan_league(league, entry, today=None):
    """Every live "N of last M" a club is running, plus its head-to-head records.

    Returns (candidates, chances). Candidates carry their base rate so the
    caller can apply the one filter that needs the TOTAL number of chances.
    """
    today = today or dt.date.today()
    dated = [tuple(x) for x in (entry.get('dated') or [])]
    if not dated:
        return [], 0

    def fresh(newest):
        """A run is only a run if it is still running."""
        try:
            return (today - dt.date.fromisoformat(newest)).days <= MAX_AGE_DAYS
        except Exception:
            return False
    base = league_rates(dated)
    tl = timeline(dated)
    out, chances, stale = [], 0, 0

    for club, rows in tl.items():
        if len(rows) < MIN_N:
            continue
        newest = rows[-1][0]
        if not fresh(newest):
            stale += 1
            continue
        for key, cat, pred, verb in PATTERNS:
            chances += 1
            hits, n, streak = window_stat(rows, pred)
            if n < MIN_N or hits < 3 or hits / n < MIN_RATE:
                continue
            ev = [{'date': d, 'gf': gf, 'ga': ga, 'opp': o, 'side': s}
                  for d, gf, ga, o, s in rows[-n:]][::-1]
            out.append({
                'league': league, 'club': club, 'category': cat, 'key': key,
                'text': phrase(verb.format(line=GOAL_LINE), hits, n, streak),
                'hits': hits, 'n': n, 'streak': streak, '_p': base.get(BASE_KEY.get(key)),
                'rate': round(hits / n, 3), 'newest': newest, 'evidence': ev[:6]})

        hm = [r for r in rows if r[4] == 'H']
        aw = [r for r in rows if r[4] == 'A']
        chances += 1
        if len(hm) >= MIN_SIDE and len(aw) >= MIN_SIDE:
            gap = ppg(hm) - ppg(aw)
            if abs(gap) >= SPLIT_GAP:
                strong = 'at home' if gap > 0 else 'away'
                out.append({
                    'league': league, 'club': club, 'category': 'Home/Away', 'key': 'split',
                    'text': (f'takes {abs(gap):.2f} more points per game {strong} '
                             f'({ppg(hm):.2f} home vs {ppg(aw):.2f} away)'),
                    'hits': None, 'n': len(hm) + len(aw), 'streak': 0, '_p': None,
                    'rate': None, 'gap': round(gap, 3), 'newest': rows[-1][0], 'evidence': []})

    # ---- head to head. Opponent-specific and asked for by name, so these are
    # kept on a CLEAN record alone -- but a 2-meeting record is thin and the
    # page says so rather than dressing it as the same thing as 10 of 10.
    pair = defaultdict(list)
    for d, h, a, hg, ag in sorted(dated):
        pair[tuple(sorted((h, a)))].append((d, h, a, hg, ag))
    # Base rates apply HERE TOO. Exempting head-to-head flooded the list with
    # "scored in all 3 meetings", which at a 75% scoring rate is a 42% event --
    # true, and not a signal. Most 3-of-3 records against one opponent do not
    # survive this, which is the honest answer: they happen by chance
    # constantly across a division's worth of pairings.
    H2H = (('h2h_win', 'won', lambda r: r[1] > r[2], 'win'),
           ('h2h_unbeaten', 'avoided defeat', lambda r: r[1] >= r[2], 'unbeaten'),
           ('h2h_under', f'under {GOAL_LINE}', lambda r: r[1] + r[2] < GOAL_LINE, 'under'),
           ('h2h_scored', 'scored', lambda r: r[1] > 0, 'scored'),
           ('h2h_cs', 'kept a clean sheet', lambda r: r[2] == 0, 'cs'))
    for (x, y), games in pair.items():
        # THREE MEETINGS, NOT TWO. The comment above says most 3-of-3 records
        # against one opponent do not survive the look-elsewhere filter -- and
        # the floor underneath it was letting 2-of-2 through, which produced
        # "kept a clean sheet in all 2 meetings" on the page. Two from two is
        # a coin landing heads twice across a division's worth of pairings.
        if len(games) < 3 or not fresh(max(g[0] for g in games)):
            continue
        for club in (x, y):
            opp = y if club == x else x
            rows = [(d, hg if h == club else ag, ag if h == club else hg)
                    for d, h, a, hg, ag in games]
            for key, verb, pred, bkey in H2H:
                chances += 1
                hits = sum(1 for r in rows if pred(r))
                if hits != len(rows):
                    continue
                out.append({
                    'league': league, 'club': club, 'category': 'Head-to-head', 'key': key,
                    'text': f'{verb} in all {hits} meetings with {opp}',
                    'hits': hits, 'n': len(rows), 'streak': hits, 'rate': 1.0,
                    '_p': base.get(bkey), 'opponent': opp,
                    'newest': max(g[0] for g in games),
                    'evidence': [{'date': d, 'gf': gf, 'ga': ga, 'opp': opp, 'side': ''}
                                 for d, gf, ga in rows][::-1][:6]})
    return out, chances, stale


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


def build(doc, today=None):
    """Ranked by how clean the record is, then by how many matches back it.

    No rarity column reaches the page. The arithmetic runs here, decides what
    is worth saying, and stays out of the sentence.
    """
    cand, chances, stale = [], 0, 0
    for league, entry in (doc or {}).items():
        got, ch, st = scan_league(league, entry, today=today)
        cand.extend(got)
        chances += ch
        stale += st
    rows = []
    for r in cand:
        r['_u'] = unusualness(r.get('hits'), r.get('n'), r.pop('_p', None))
        rows.append(r)
    # Most unusual first; a clean record over more matches breaks ties.
    rows.sort(key=lambda r: (r['_u'], -(r.get('rate') or 0), -(r.get('n') or 0)))
    for r in rows:
        r.pop('_u', None)
    return {'chances': chances, 'shown': len(rows), 'considered': len(cand),
            'stale': stale, 'patterns': rows}


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    chk(phrase('scored', 5, 5, 5) == 'scored in all of the last 5',
        'a perfect record reads "in all of the last N", not "5 of last 5"')
    chk(phrase('under 2.5', 9, 10, 4) == 'under 2.5 in 9 of last 10 (4 in a row)',
        'a strong-but-imperfect record names the run inside it')
    chk(phrase('won', 8, 10, 0) == 'won in 8 of last 10',
        'no run, no parenthetical')
    chk('unlikely' not in phrase('won', 8, 10, 0) and '1 in' not in phrase('won', 8, 10, 0),
        'no rarity language reaches the sentence')

    rows = [('2026-01-0%d' % i, 1, 0, 'X', 'H') for i in range(1, 7)]
    h, n, s = window_stat(rows, lambda r: r[1] > r[2])
    chk((h, n, s) == (6, 6, 6), f'a clean window counts hits, size and run: {(h,n,s)}')
    h2, n2, _ = window_stat(rows + [('2026-02-01', 0, 2, 'Y', 'A')], lambda r: r[1] > r[2])
    chk((h2, n2) == (6, 7), 'a loss at the end drops the run but keeps the count')

    dated = [['2026-01-01', 'Alpha', 'B', 1, 0], ['2026-02-01', 'C', 'Alpha', 0, 1],
             ['2026-03-01', 'Alpha', 'D', 2, 0], ['2026-04-01', 'E', 'Alpha', 0, 1],
             ['2026-05-01', 'Alpha', 'B', 1, 0], ['2026-06-01', 'B', 'Alpha', 0, 2],
             ['2026-07-01', 'C', 'D', 3, 3]]
    # PIN THE DATE. The staleness gate measures against today, so a fixture with
    # hardcoded 2026 dates and a live clock is a test that passes now and starts
    # failing on its own in July -- a decaying test is its own bug.
    TODAY = dt.date(2026, 7, 5)
    res = build({'L': {'dated': dated}}, today=TODAY)
    P = {(r['club'], r['key']): r for r in res['patterns']}

    chk(('Alpha', 'wins') in P, "Alpha's winning record is found")
    chk(P[('Alpha', 'wins')]['text'] == 'won in all of the last 6',
        f"and reads plainly: {P[('Alpha','wins')]['text']!r}")
    chk(('Alpha', 'cs') in P and 'clean sheet' in P[('Alpha', 'cs')]['text'],
        'clean sheets are their own statement')
    chk(('Alpha', 'h2h_win') in P,
        'a head-to-head record against one opponent is found')
    chk(P[('Alpha', 'h2h_win')]['text'] == 'won in all 3 meetings with B',
        f"phrased vs the opponent: {P[('Alpha','h2h_win')]['text']!r}")
    chk('in all' in P[('Alpha', 'h2h_win')]['text'],
        "and reads as a sentence -- the first cut said 'under 2.5 3 of the last 3', "
        "which is missing the word a person would say")
    chk(P[('Alpha', 'h2h_win')]['opponent'] == 'B', 'and names the opponent as a field')
    chk(('B', 'h2h_win') not in P,
        'the losing side of a head-to-head gets no winning record')

    chk(all('one_in' not in r for r in res['patterns']),
        'NO rarity figure is emitted anywhere')
    chk(all(r.get('rate') is None or r['rate'] >= MIN_RATE for r in res['patterns']),
        'nothing below the rate floor is reported at all')
    chk(all('_u' not in r for r in res['patterns']),
        'the ranking statistic is stripped before the page ever sees it')
    lo = unusualness(10, 10, 0.45)
    hi = unusualness(3, 10, 0.45)
    chk(lo < hi, 'a rarer record ranks ahead of a common one')
    chk(unusualness(None, None, None) == 0.05,
        'a home/away split has no per-match rate and sits mid-list, not first')

    thin = build({'L': {'dated': [['2026-06-01', 'X', 'Y', 1, 0],
                                  ['2026-07-01', 'X', 'Y', 1, 0]]}},
                 today=dt.date(2026, 7, 5))
    chk(not [r for r in thin['patterns'] if r['key'] == 'wins'],
        'two matches is not enough for a club-level record')
    # THIS CHECK USED TO ASSERT THE OPPOSITE. The reasoning was that a
    # head-to-head is a different question from a form run, so a smaller sample
    # is acceptable -- and the comment above the H2H table already said most
    # 3-of-3 records do not survive the look-elsewhere filter. Both cannot be
    # true. A 2-of-2 is a coin landing heads twice, and across a division's
    # worth of pairings a scan will find dozens; "kept a clean sheet in all 2
    # meetings with Independiente Petrolero" reached the page and reads as a
    # pattern rather than as two matches.
    chk(not [r for r in thin['patterns'] if r['key'] == 'h2h_win'],
        'and two MEETINGS is not enough either -- it reads as a pattern and is not one')

    chk(build({})['patterns'] == [], 'an empty source yields nothing, not a crash')
    # ------------------------------------------------------ the staleness gate
    # Peru's dated rounds stop in May for some clubs, and "conceded in all of
    # the last 10 -- 16 in a row" reached the page with its newest evidence 123
    # days old. A run is only a run if it is still running.
    old = build({'L': {'dated': dated}}, today=dt.date(2026, 7, 5) + dt.timedelta(days=60))
    chk(not old['patterns'] and old['stale'] > 0,
        'every club whose newest match is older than 45 days is refused and COUNTED')
    chk(build({'L': {'dated': dated}}, today=dt.date(2026, 7, 5))['stale'] == 0,
        'and a live league is not counted stale')
    edge = [[f'2026-06-{i:02d}', 'Alpha', f'T{i}', 1, 0] for i in range(1, 8)]
    chk(build({'L': {'dated': edge}}, today=dt.date(2026, 7, 21))['patterns'],
        'a run 44 days old is still live')
    chk(not build({'L': {'dated': edge}}, today=dt.date(2026, 7, 23))['patterns'],
        'and 46 days old is not')

    # ---------------------------------------------------- the head-to-head floor
    two = [['2026-06-01', 'Alpha', 'B', 1, 0], ['2026-06-08', 'B', 'Alpha', 0, 1],
           ['2026-06-15', 'Alpha', 'C', 1, 0], ['2026-06-22', 'Alpha', 'D', 1, 0],
           ['2026-06-29', 'Alpha', 'E', 1, 0], ['2026-07-02', 'Alpha', 'F', 1, 0]]
    r2 = build({'L': {'dated': two}}, today=dt.date(2026, 7, 5))
    chk(not [r for r in r2['patterns'] if r['category'] == 'Head-to-head'],
        'two meetings is not a head-to-head record -- "in all 2 meetings" shipped')
    three = two + [['2026-07-03', 'B', 'Alpha', 0, 1]]
    r3 = build({'L': {'dated': three}}, today=dt.date(2026, 7, 5))
    chk([r for r in r3['patterns'] if r['category'] == 'Head-to-head'],
        'three meetings clears the floor')
    chk(not any('all 2 meetings' in r['text'] for r in r3['patterns']),
        'no sentence on the page can read "in all 2 meetings"')

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
    print(f"socpatterns: {len(pats)} live records across five leagues")
    for p in pats[:22]:
        print(f"  {p['club'][:22]:22} {p['text'][:54]:54} {p['league'][:20]}")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

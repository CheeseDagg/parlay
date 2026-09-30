#!/usr/bin/env python3
"""socextra.py — league tables for the countries football-data does not publish.

    python3 socextra.py              # runner only (Wikipedia is egress-blocked here)
    python3 socextra.py --selftest

WHY THIS EXISTS. On 2026-09-30 an international break emptied the big-5 and
the real slate was Colombia, Peru, Chile, Bolivia, El Salvador and USL.
socbase priced NONE of them -- not because the board was broken but because
sococalib and socform are both fed by football-data.co.uk, whose entire
country list is ARG/AUT/BRA/CHN/DNK/FIN/IRL/JPN/MEX/NOR/POL/ROU/RUS/SWE/
SWZ/USA. Those leagues are not "thin data", they are NO data, and the tool
said UNMEASURED on a day the whole slate lived there.

WHAT IT READS. Wikipedia season pages carry a results MATRIX: home teams
down the side, the same teams across the top, every league fixture in one
grid. srcprobe rounds 5-6 confirmed the runner reaches Wikipedia and that
Colombia and Peru publish two matrices each (Apertura + Clausura).

WHAT A MATRIX CAN AND CANNOT SAY. It has every result and it has NO DATES.
So it grounds anything order-free -- league base rates, home/away splits,
head-to-head -- and it CANNOT ground recent form. That limit is enforced in
code: no 'form' key is written here, ever. socform stays the only source of
form, and it stays silent on these leagues until a dated source turns up.

THE AXIS GUARD IS THE WHOLE INTEGRITY STORY. Column i is assumed to be the
same club as row i -- standard for these grids, and catastrophic if it is
ever false, because every result would be attributed to the wrong pair
while looking perfectly well-formed. So every matrix must have a DASHED
DIAGONAL (no club plays itself) before a single result is taken from it. A
matrix that fails is refused by name and counted, never silently skipped.
"""
import json, os, re, sys, urllib.parse, urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'socextra.json')
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Slugs are PINNED, not searched. srcprobe round 6 asked Wikipedia's own
# opensearch for "2026 Chilean Primera Division season" and got 2012, 2011,
# 2010 -- the search ranks old seasons above the current one, so a resolver
# built on it would quietly grade this year against a fourteen-year-old
# league. Pin the slug; when a season rolls over, the fetch 404s loudly.
LEAGUES = {
    # Full URLs, not slugs: Uruguay's season lives on SPANISH Wikipedia only,
    # and the page that carries a league is not always on the wiki you expect.
    'Colombia Primera A': ['https://en.wikipedia.org/wiki/2026_Categor%C3%ADa_Primera_A_season'],
    'Peru Liga 1':        ['https://en.wikipedia.org/wiki/2026_Liga_1_(Peru)'],
    # Chile RENAMED the competition: it is "Liga de Primera" now, which is the
    # entire reason every 2026_Chilean_Primera_Division slug 404'd through
    # three probe rounds. The league did not vanish, its name moved.
    'Chile Liga de Primera': ['https://en.wikipedia.org/wiki/2026_Liga_de_Primera',
                              'https://es.wikipedia.org/wiki/Liga_de_Primera_2026'],
    'Uruguay Primera':    ['https://es.wikipedia.org/wiki/Campeonato_Uruguayo_de_Primera_Divisi%C3%B3n_2026'],
    'Bolivia Profesional': ['https://en.wikipedia.org/wiki/2026_FBF_Divisi%C3%B3n_Profesional'],
}

RUNGS = (1.5, 2.5, 3.5, 4.5, 5.5)
SCORE = re.compile(r'^(\d{1,2})\s*[-–—]\s*(\d{1,2})$')
DASH = re.compile(r'^[\s—–-]*$')       # '—', '–', '-', or empty


class Tables(HTMLParser):
    """Every <table class=wikitable> as (preceding heading, rows of cells)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.head = [], ''
        self.t = self.row = self.cell = None
        self.in_h = 0
        self._hbuf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('h2', 'h3', 'h4'):
            self.in_h, self._hbuf = 1, []
        elif tag == 'table' and 'wikitable' in (a.get('class') or ''):
            self.t = []
        elif self.t is not None and tag == 'tr':
            self.row = []
        elif self.row is not None and tag in ('td', 'th'):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3', 'h4') and self.in_h:
            self.in_h, self.head = 0, ' '.join(self._hbuf).strip()
        elif tag == 'table' and self.t is not None:
            self.out.append((self.head, self.t))
            self.t = None
        elif tag == 'tr' and self.row is not None:
            if self.row:
                self.t.append(self.row)
            self.row = None
        elif tag in ('td', 'th') and self.cell is not None:
            self.row.append(re.sub(r'\s+', ' ', ' '.join(self.cell)).strip())
            self.cell = None

    def handle_data(self, d):
        if self.in_h:
            self._hbuf.append(d)
        elif self.cell is not None:
            self.cell.append(d)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')


# ----------------------------------------------------------------- the matrix
def is_matrix(rows):
    """>=20 bare score cells and a 'Home' corner: a results grid, not a table
    of hat-tricks that happens to contain scores."""
    if not rows or len(rows) < 4:
        return False
    corner = rows[0][0].lower() if rows[0] else ''
    # es.wikipedia writes the corner as 'Local \\ Visitante'. A grid is a grid.
    if not any(w in corner for w in ('home', 'local', 'equipo')):
        return False
    return sum(1 for r in rows for c in r if SCORE.match(c.strip())) >= 20


def diagonal_ok(rows):
    """Cell [i][i] must be a dash for every club: nobody plays themselves.

    This is the ONLY thing standing between 'column i is row i's club' and
    every result in the league being attributed to the wrong pair. It is
    cheap, it is total, and a matrix that fails it is not used."""
    bad = []
    for i in range(1, len(rows)):
        row = rows[i]
        if i >= len(row):
            continue
        if not DASH.match(row[i].strip()):
            bad.append((i, row[0][:24], row[i][:12]))
    return (not bad), bad


def read_matrix(rows):
    """[(home, away, hg, ag)] from one grid. Blank cells = not yet played."""
    teams = [r[0].strip() for r in rows[1:]]
    out = []
    for i, row in enumerate(rows[1:]):
        home = row[0].strip()
        for j, cell in enumerate(row[1:], start=0):
            if j >= len(teams) or j == i:
                continue
            m = SCORE.match(cell.strip())
            if not m:
                continue
            out.append((home, teams[j], int(m.group(1)), int(m.group(2))))
    return out


def rates(matches):
    """socbase-shaped rates. Deliberately no 'form' key -- see the docstring."""
    n = len(matches)
    if not n:
        return None
    hw = sum(1 for _, _, h, a in matches if h > a)
    dr = sum(1 for _, _, h, a in matches if h == a)
    goals = [h + a for _, _, h, a in matches]
    res = {'n': n,
           'home': round(hw / n, 5),
           'draw': round(dr / n, 5),
           'away': round((n - hw - dr) / n, 5),
           'mean_goals': round(sum(goals) / n, 3)}
    und = {str(r): round(sum(1 for g in goals if g < r) / n, 5) for r in RUNGS}
    return {'result': res, 'under': und, 'src': 'wikipedia-matrix'}


def splits(matches):
    """Per-team home/away splits and head-to-head -- the two signals a dateless
    grid CAN honestly support."""
    home, away, h2h = {}, {}, {}
    for hm, aw, hg, ag in matches:
        h = home.setdefault(hm, {'p': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0})
        a = away.setdefault(aw, {'p': 0, 'w': 0, 'd': 0, 'l': 0, 'gf': 0, 'ga': 0})
        for d, gf, ga in ((h, hg, ag), (a, ag, hg)):
            d['p'] += 1
            d['gf'] += gf
            d['ga'] += ga
            d['w' if gf > ga else ('d' if gf == ga else 'l')] += 1
        h2h.setdefault('|'.join(sorted((hm, aw))), []).append(
            {'home': hm, 'away': aw, 'hg': hg, 'ag': ag})
    for d in (home, away):
        for t, v in d.items():
            v['ppg'] = round((v['w'] * 3 + v['d']) / v['p'], 3) if v['p'] else 0
    return {'home': home, 'away': away, 'h2h': h2h}


def build(fetch=get):
    doc, report = {}, []
    for league, slugs in LEAGUES.items():
        html = None
        for s in slugs:
            try:
                html = fetch(s)
                used = s
                break
            except Exception as e:
                report.append(f'  {league}: {s.rsplit("/", 1)[-1]} -> {type(e).__name__}')
        if html is None:
            report.append(f'  ABSENT  {league}: no pinned slug resolved')
            continue
        p = Tables()
        p.feed(html)
        matches, refused = [], []
        for head, rows in p.out:
            if not is_matrix(rows):
                continue
            ok, bad = diagonal_ok(rows)
            if not ok:
                refused.append(f'{head or "?"} (diagonal: {bad[:2]})')
                continue
            matches.extend(read_matrix(rows))
        # A club can meet another twice in a split season; the grid holds one
        # cell per ordered pair per stage, so duplicates across stages are real
        # fixtures, not double-counting. Identical rows are not deduped.
        if not matches:
            report.append(f'  EMPTY   {league}: page found, no usable matrix'
                          + (f' (refused {len(refused)})' if refused else ''))
            continue
        doc[league] = {'slug': used, 'rates': rates(matches),
                       'splits': splits(matches),
                       'matches': [list(m) for m in matches],
                       'refused_matrices': refused}
        r = doc[league]['rates']['result']
        report.append(f'  OK      {league}: {r["n"]} matches  home {r["home"]:.3f} '
                      f'draw {r["draw"]:.3f} away {r["away"]:.3f} goals {r["mean_goals"]}'
                      + (f'  [{len(refused)} matrix refused]' if refused else ''))
    return doc, report


# ------------------------------------------------------------------- selftest
def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    grid = [['Home \\ Away', 'AAA', 'BBB', 'CCC'],
            ['Alpha', '—', '2–1', '0–0'],
            ['Beta', '1–3', '—', ''],
            ['Gamma', '2–2', '0–1', '—']]
    chk(is_matrix(grid) is False, 'a 3-club grid has too few scores to be trusted as a matrix')

    big = [['Home \\ Away'] + [f'T{i}' for i in range(8)]]
    for i in range(8):
        row = [f'Team{i}']
        for j in range(8):
            row.append('—' if i == j else f'{(i + j) % 4}–{(i * j) % 3}')
        big.append(row)
    chk(is_matrix(big), 'an 8-club full grid reads as a matrix')
    es = [r[:] for r in big]
    es[0][0] = 'Local \\ Visitante'
    chk(is_matrix(es), 'a SPANISH grid (Local \\ Visitante) is still a matrix')
    en_only = [r[:] for r in big]
    en_only[0][0] = 'Player'
    chk(not is_matrix(en_only), 'a scores table that is not a grid is refused')
    chk(diagonal_ok(big)[0], 'a clean grid passes the diagonal guard')

    m = read_matrix(big)
    chk(len(m) == 56, f'8 clubs -> 56 ordered pairs, got {len(m)}')
    chk(all(h != a for h, a, _, _ in m), 'no club is ever its own opponent')

    bent = [r[:] for r in big]
    bent[3][3] = '1–0'                      # a result on the diagonal
    okd, bad = diagonal_ok(bent)
    chk((not okd) and bad, 'a result on the diagonal FAILS the guard (axes misaligned)')

    r = rates([('A', 'B', 2, 1), ('B', 'A', 0, 0), ('A', 'C', 1, 3)])
    # tolerances match the PERSISTED precision (home 5dp, goals 3dp) -- comparing a
    # rounded field against an exact fraction at 1e-9 is a broken test, not a bug.
    chk(r['result']['n'] == 3 and abs(r['result']['home'] - 1 / 3) < 1e-5,
        'rates count home wins from the home column only')
    chk(abs(r['result']['mean_goals'] - 7 / 3) < 1e-3, 'mean goals is total goals per match')
    chk(r['under']['3.5'] == round(2 / 3, 5), 'under 3.5 counts 3 and 0 but not 4')
    chk('form' not in r and 'form' not in str(list(r)),
        'NO form key is emitted -- a dateless grid cannot support recent form')

    s = splits([('A', 'B', 2, 1), ('A', 'B', 0, 0), ('B', 'A', 3, 1)])
    chk(s['home']['A']['p'] == 2 and s['home']['A']['w'] == 1, "A's home record is 2 played, 1 won")
    chk(s['away']['A']['p'] == 1 and s['away']['A']['l'] == 1, "A's away record is separate from home")
    chk(len(s['h2h']['A|B']) == 3, 'head-to-head keys both orientations into one pair')

    def fake(url):
        if 'Peru' in url:
            return ('<table class="wikitable"><tr><th>Home \\ Away</th>'
                    + ''.join(f'<th>T{i}</th>' for i in range(8)) + '</tr>'
                    + ''.join('<tr><td>Team%d</td>' % i
                              + ''.join('<td>%s</td>' % ('—' if i == j else '1–0')
                                        for j in range(8)) + '</tr>'
                              for i in range(8)) + '</table>')
        raise urllib.error.HTTPError(url, 404, 'no', None, None)

    doc, rep = build(fetch=fake)
    chk(list(doc) == ['Peru Liga 1'], 'only the league that resolved is written')
    chk(doc['Peru Liga 1']['rates']['result']['n'] == 56, 'the fake page yields all 56 pairs')
    chk(any('ABSENT' in line for line in rep), 'leagues whose slug 404s are REPORTED, not dropped')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


def main():
    doc, report = build()
    print('socextra -- leagues football-data does not publish')
    for line in report:
        print(line)
    if not doc:
        print('\nnothing resolved; socextra.json NOT overwritten')
        return 1
    json.dump(doc, open(OUT, 'w'), indent=1)
    tot = sum(v['rates']['result']['n'] for v in doc.values())
    print(f'\nwrote {OUT} -- {len(doc)} leagues, {tot} matches')
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

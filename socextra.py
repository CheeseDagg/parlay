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
    # Uruguay publishes NO results grid anywhere (srcprobe round 8: nine
    # tables, zero score cells -- standings evolution only). It does publish
    # dated round tables, on three separate tournament pages. So it is a
    # DATED-ONLY league: no matrix URL here, everything comes from ES_ROUNDS.
    'Uruguay Primera':    [],
    'Bolivia Profesional': ['https://en.wikipedia.org/wiki/2026_FBF_Divisi%C3%B3n_Profesional'],
}

# Spanish Wikipedia publishes the same seasons as DATED round-by-round tables
# ("Local | Resultado | Visita | Estadio | Fecha | Hora"). srcprobe round 9
# found them after the matrix work was already done -- they are strictly
# better, because order is what Recent Form needs and a matrix has none.
# The matrix stays as the fallback: some leagues have one and not the other.
ES_ROUNDS = {
    'Chile Liga de Primera': ['https://es.wikipedia.org/wiki/Liga_de_Primera_2026'],
    'Bolivia Profesional':   ['https://es.wikipedia.org/wiki/Primera_Divisi%C3%B3n_de_Bolivia_2026'],
    # Colombia and Peru split the year into two tournaments and put the round
    # tables on the TOURNAMENT pages, not the season page (which 404s). Both
    # are read and merged -- Apertura alone stops in May, which is what made
    # September's form look four months stale.
    'Colombia Primera A':    ['https://es.wikipedia.org/wiki/Torneo_Finalizaci%C3%B3n_2026_(Colombia)',
                              'https://es.wikipedia.org/wiki/Torneo_Apertura_2026_(Colombia)'],
    'Peru Liga 1':           ['https://es.wikipedia.org/wiki/Torneo_Clausura_2026_(Per%C3%BA)',
                              'https://es.wikipedia.org/wiki/Torneo_Apertura_2026_(Per%C3%BA)',
                              'https://es.wikipedia.org/wiki/Liga1_2026_(Per%C3%BA)'],
    # Uruguay runs THREE tournaments in a year and pages each separately.
    'Uruguay Primera':       ['https://es.wikipedia.org/wiki/Torneo_Apertura_2026_(Uruguay)',
                              'https://es.wikipedia.org/wiki/Torneo_Intermedio_2026',
                              'https://es.wikipedia.org/wiki/Torneo_Clausura_2026_(Uruguay)'],
}

MONTHS = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5,
          'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9,
          'octubre': 10, 'noviembre': 11, 'diciembre': 12}

YEAR = 2026
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
        # ROWSPAN IS NOT COSMETIC HERE. These fixture tables print ONE date
        # cell spanning every match played that day, so rows 2..N of a day
        # arrive one cell short and a flat parser silently loses the date --
        # which is precisely how half of every league's results came back
        # "scored but undated" and Colombia's form looked four months stale.
        self._spans = []
        self._pending = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('h2', 'h3', 'h4'):
            self.in_h, self._hbuf = 1, []
        elif tag == 'table' and 'wikitable' in (a.get('class') or ''):
            self.t = []
        elif self.t is not None and tag == 'tr':
            self.row, self._spans = [], []
        elif self.row is not None and tag in ('td', 'th'):
            self.cell = []
            try:
                self._cellspan = max(1, int(a.get('rowspan') or 1))
            except (TypeError, ValueError):
                self._cellspan = 1

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3', 'h4') and self.in_h:
            self.in_h, self.head = 0, ' '.join(self._hbuf).strip()
        elif tag == 'table' and self.t is not None:
            self.out.append((self.head, self.t))
            self.t = None
            self._pending = {}
        elif tag == 'tr' and self.row is not None:
            self._close_row()
            if self.row:
                self.t.append(self.row)
            self.row = None
        elif tag in ('td', 'th') and self.cell is not None:
            self.row.append(re.sub(r'\s+', ' ', ' '.join(self.cell)).strip())
            self._spans.append(getattr(self, '_cellspan', 1))
            self.cell = self._cellspan = None

    def _close_row(self):
        """Re-insert cells that are still spanning down from an earlier row,
        at the column they occupied, then tick their counters."""
        for col in sorted(self._pending):
            rem, txt = self._pending[col]
            at = min(col, len(self.row))
            self.row.insert(at, txt)
            self._spans.insert(at, 1)
        for col in list(self._pending):
            self._pending[col][0] -= 1
            if self._pending[col][0] <= 0:
                del self._pending[col]
        for i, sp in enumerate(self._spans):
            if sp > 1 and i < len(self.row):
                self._pending[i] = [sp - 1, self.row[i]]

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


ES_SCORE = re.compile(r'^(\d{1,2})\s*[-\u2013\u2014:]\s*(\d{1,2})$')
ES_DATE = re.compile(r'(\d{1,2})\s*de\s*([a-z\u00e1\u00e9\u00ed\u00f3\u00fa]+)', re.I)


def parse_es_date(cell, year):
    """'30 de enero' -> '2026-01-30'. Returns None rather than a guess."""
    m = ES_DATE.search(cell or '')
    if not m:
        return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    return f'{year:04d}-{mon:02d}-{int(m.group(1)):02d}'


def read_rounds(tables, year):
    """[(date, home, away, hg, ag)] from Spanish round-by-round tables.

    A row only counts when it has BOTH a parsed score and a parsed date --
    a fixture list contains future games with empty scores, and a dateless
    row is exactly the thing this reader exists to avoid producing."""
    out, undated = [], 0
    for _head, rows in tables:
        if not rows or not rows[0]:
            continue
        # THE HEADER IS NOT ALWAYS ROW 0. These tables open with a one-cell
        # TITLE row ('Fecha 1' = matchday 1) and put the real header beneath
        # it. Reading row 0 as the header found 'fecha 1', matched no columns,
        # and skipped every table on the page while reporting "no dated rows"
        # -- a parser that looked like an absent source. Find the header row.
        hrow = None
        for k in range(min(3, len(rows))):
            cells = [c.strip().lower() for c in rows[k]]
            if any(c.startswith('local') for c in cells) and \
               any(c.startswith('resultado') for c in cells):
                hrow = k
                break
        if hrow is None:
            continue
        hdr = [c.strip().lower() for c in rows[hrow]]

        def col(*names):
            for i, c in enumerate(hdr):
                if any(c.startswith(n) for n in names):
                    return i
            return None
        ih, ir, ia = col('local'), col('resultado'), col('visita')
        # 'Fecha' is both "date" and "matchday" in Spanish. The header row of a
        # round table is literally 'Fecha 1', so the DATE column is the one that
        # is not the first column and parses as a date -- checked per row below.
        if ih is None or ir is None or ia is None:
            continue
        for row in rows[hrow + 1:]:
            if max(ih, ir, ia) >= len(row):
                continue
            m = ES_SCORE.match(row[ir].strip())
            if not m:
                continue
            date = None
            for j in range(len(row) - 1, -1, -1):
                if j in (ih, ir, ia):
                    continue
                date = parse_es_date(row[j], year)
                if date:
                    break
            if not date:
                undated += 1
                continue
            out.append((date, row[ih].strip(), row[ia].strip(),
                        int(m.group(1)), int(m.group(2))))
    return out, undated


def canonicalise(rows, idx):
    """One spelling per club, before anything is keyed on the name.

    Bolivia's pages write the same club as 'Bolivar' AND 'Bolívar', which
    split it into two half-records: two form strings, two home/away splits,
    and a head-to-head that could find neither. The most frequent raw
    spelling wins; ties break alphabetically so a rebuild is deterministic.
    Returns (rows, {canonical: [variants]}) and reports what it merged.
    """
    from collections import Counter, defaultdict
    seen = defaultdict(Counter)
    for r in rows:
        for i in idx:
            seen[norm_team(r[i])][r[i]] += 1
    canon, merged = {}, {}
    for key, names in seen.items():
        best = sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for nm in names:
            canon[nm] = best
        if len(names) > 1:
            merged[best] = sorted(names)
    out = []
    for r in rows:
        r = list(r)
        for i in idx:
            r[i] = canon.get(r[i], r[i])
        out.append(tuple(r))
    return out, merged


def form_table(dated, last=5):
    """Per team: the last N results newest-first, from DATED rows only."""
    by = {}
    for d, h, a, hg, ag in sorted(dated):
        by.setdefault(h, []).append((d, 'W' if hg > ag else ('D' if hg == ag else 'L'), hg, ag, a, 'H'))
        by.setdefault(a, []).append((d, 'W' if ag > hg else ('D' if hg == ag else 'L'), ag, hg, h, 'A'))
    out = {}
    for team, rows in by.items():
        rows = rows[-last:][::-1]
        out[team] = {
            'form': ''.join(r[1] for r in rows),
            'n': len(rows),
            'gf': sum(r[2] for r in rows),
            'ga': sum(r[3] for r in rows),
            'newest': rows[0][0] if rows else None,
            'matches': [{'date': r[0], 'res': r[1], 'gf': r[2], 'ga': r[3],
                         'opp': r[4], 'side': r[5]} for r in rows]}
    return out


def cross_check(matrix, dated):
    """Two independent readers of the same season must agree.

    Compared as MULTISETS per ordered pair, not single values. Colombia and
    Peru play Apertura AND Finalizacion, so the same pair meets twice at the
    same ground with different scores -- Santa Fe beat America 4-0 in May and
    drew 0-0 in August. A single-value check called that a reader conflict on
    the first run; it is a split season, and the fix is to compare the whole
    bag of scores for a pair rather than one of them.

    Returns (agreed_pairs, disagreed_pairs, [samples]).
    """
    from collections import defaultdict
    mi, di = defaultdict(list), defaultdict(list)
    collide = {}
    for h, a, hg, ag in matrix:
        for nm in (h, a):
            collide.setdefault(join_key(nm), set()).add(norm_team(nm))
        mi[(join_key(h), join_key(a))].append((hg, ag))
    for _d, h, a, hg, ag in dated:
        di[(join_key(h), join_key(a))].append((hg, ag))
    smashed = {k: sorted(v) for k, v in collide.items() if len(v) > 1}
    agree, bad = 0, []
    for k in set(mi) & set(di):
        if sorted(mi[k]) == sorted(di[k]):
            agree += 1
        else:
            bad.append((k[0], k[1], sorted(mi[k]), sorted(di[k])))
    # Is the dated reading a SUPERSET of the grid -- every score the grid has,
    # plus possibly more? Colombia's grid is missing one of two Santa Fe v
    # America meetings that the round tables both carry. That is not a
    # conflict, it is one reader being more complete, and it decides which
    # source the rates are built from.
    # Scoped to SHARED pairs. The two readers come off different wikis and
    # spell clubs differently ("America de Cali" vs "America"), so a pair
    # missing from one side is a NAME gap, not a data gap -- judging
    # completeness on those would reject a reading that is strictly better.
    # Coverage is reported instead, because low coverage is its own signal.
    shared = set(mi) & set(di)
    superset = all(_contains(di[k], mi[k]) for k in shared)
    coverage = round(len(shared) / len(mi), 3) if mi else 0.0
    if smashed:
        # Stripping furniture merged two real clubs into one key -- the join
        # is unsafe for this league, so report rather than claim agreement.
        bad = bad + [('JOIN COLLISION', k, v, []) for k, v in list(smashed.items())[:3]]
    return agree, len(bad), bad[:5], (superset and not smashed, coverage)


def _contains(big, small):
    from collections import Counter
    b, s = Counter(big), Counter(small)
    return all(b[k] >= v for k, v in s.items())


# Club furniture, stripped ONLY for the cross-check join. The two wikis
# write the same club as "Cusco" and "Cusco FC", "Melgar" and "FBC Melgar",
# "Cajamarca" and "FC Cajamarca" -- 85 of Peru's 242 pairs failed to join on
# that alone, and the coverage number said 65% when the readings agreed.
# Stored names keep whatever the source published; this is a join key only.
FURNITURE = {'fc', 'cf', 'sc', 'afc', 'cd', 'ca', 'ac', 'as', 'club', 'fbc',
             'sd', 'ad', 'cs', 'sac', 'fbc', 'aa', 'cdsc'}


def norm_team(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return ' '.join(s.replace('.', ' ').replace('-', ' ').split())


def join_key(s):
    """norm_team minus club furniture, for matching ACROSS sources.

    Collision-guarded by the caller: if stripping ever maps two distinct
    clubs in one league onto the same key, the cross-check says so instead
    of reporting a false agreement."""
    toks = [w for w in norm_team(s).split() if w not in FURNITURE]
    return ' '.join(toks) or norm_team(s)


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
        # THE MATRIX IS OPTIONAL. Uruguay publishes no results grid at all,
        # only dated round tables across three tournament pages, so requiring
        # a grid would drop a league whose data is strictly BETTER than a
        # grid's -- it has dates. A league qualifies on either source.
        matches, refused, used = [], [], None
        for s in slugs:
            try:
                html = fetch(s)
            except Exception as e:
                report.append(f'  {league}: {s.rsplit("/", 1)[-1]} -> {type(e).__name__}')
                continue
            p = Tables()
            p.feed(html)
            for head, rows in p.out:
                if not is_matrix(rows):
                    continue
                ok, bad = diagonal_ok(rows)
                if not ok:
                    refused.append(f'{head or "?"} (diagonal: {bad[:2]})')
                    continue
                matches.extend(read_matrix(rows))
            if matches:
                used = s
                break
        all_dated, tot_und, pages = [], 0, []
        for u in ES_ROUNDS.get(league, []):
            try:
                eh = fetch(u)
            except Exception as e:
                report.append(f'    es-rounds {league}: {u.rsplit("/", 1)[-1]} -> {type(e).__name__}')
                continue
            ep = Tables()
            ep.feed(eh)
            dated, undated = read_rounds(ep.out, YEAR)
            tot_und += undated
            if dated:
                all_dated.extend(dated)
                pages.append(u.rsplit('/', 1)[-1])
            else:
                report.append(f'    es-rounds {league}: {u.rsplit("/", 1)[-1]} read, no dated rows')
        if not matches and not all_dated:
            report.append(f'  EMPTY   {league}: no usable matrix and no dated rounds'
                          + (f' ({len(refused)} matrix refused)' if refused else ''))
            continue
        if matches:
            entry = {'slug': used, 'rates': rates(matches), 'splits': splits(matches),
                     'matches': [list(m) for m in matches], 'refused_matrices': refused}
        else:
            entry = {'slug': None, 'refused_matrices': refused,
                     'rates_source': 'dated rounds only (this league publishes no grid)'}
        if all_dated:
            # A club can appear on both tournament pages; identical rows are
            # the same fixture listed twice, so dedupe on the whole tuple.
            all_dated = sorted(set(all_dated))
            all_dated, merged_names = canonicalise(all_dated, (1, 2))
            all_dated = sorted(set(all_dated))
            if merged_names:
                entry['merged_names'] = merged_names
                for c, vs in merged_names.items():
                    report.append(f'    merged spellings {league}: {vs} -> {c!r}')
            entry['dated'] = [list(d) for d in all_dated]
            entry['form'] = form_table(all_dated)
            entry['es_pages'] = pages
            if not matches:
                dm = [(h, a, hg, ag) for _d, h, a, hg, ag in all_dated]
                entry['rates'] = rates(dm)
                entry['splits'] = splits(dm)
                entry['matches'] = [list(m) for m in dm]
                newest0 = max(d[0] for d in all_dated)
                report.append(f'    es-rounds {league}: {len(all_dated)} dated results '
                              f'across {len(pages)} page(s), newest {newest0} '
                              f'[NO GRID -- dated rounds are the only source]')
                r0 = entry['rates']['result']
                report.append(f'  OK      {league}: {r0["n"]} matches  home {r0["home"]:.3f} '
                              f'draw {r0["draw"]:.3f} away {r0["away"]:.3f} goals {r0["mean_goals"]}')
                doc[league] = entry
                continue
            ag, dis, samples, (superset, coverage) = cross_check(matches, all_dated)
            delta = len(all_dated) - len(matches)
            entry['cross_check'] = {'agreed_pairs': ag, 'disagreed_pairs': dis,
                                    'samples': samples, 'count_delta': delta,
                                    'dated_is_superset': superset,
                                    'name_coverage': coverage}
            if dis:
                report.append(f'    !! {league}: {dis} scoreline(s) DISAGREE between the '
                              f'grid and the round tables (agreed {ag})')
                for s in samples:
                    report.append(f'       {s[0]} v {s[1]}: grid {s[2]} vs rounds {s[3]}')
            else:
                report.append(f'    cross-check {league}: {ag} fixture pairs agree '
                              f'across both readers, 0 disagree'
                              + (f'; rounds carry {delta:+d} result(s)' if delta
                                 else '; same count')
                              + f'; names join on {coverage:.0%} of grid pairs')
            # PREFER THE MORE COMPLETE READER. When the dated rounds contain
            # every score the grid has and at least as many, they are simply
            # the better reading -- and they are date-verified besides. The
            # grid stays as the fallback and as the cross-check's other half.
            # WHICH READER WINS. Preferring the grid whenever the two
            # disagree is backwards: it rejects the better source for
            # disagreeing with the worse one. Peru proved it -- the grid said
            # Cajamarca 2-1 Cusco, the rounds said Cajamarca 1-2 Cusco, and
            # RPP, dsn.pe and the FIFA match centre all record Cusco winning
            # 2-1 AWAY on 2026-09-19. The rounds were right and were being
            # thrown away for it.
            #
            # The rounds are per-fixture rows carrying date, venue and kickoff;
            # the grid is a hand-maintained summary cell. So the rounds win on
            # count, and every disagreement is REPORTED with both values rather
            # than silently resolved. A join collision still blocks the switch,
            # because then the comparison itself is untrustworthy.
            if delta >= 0 and not any(s[0] == 'JOIN COLLISION' for s in samples):
                dm = [(h, a, hg, ag) for _d, h, a, hg, ag in all_dated]
                # KEEP THE SUPERSEDED READER. Overwriting 'matches' destroyed
                # the evidence the cross-check had just run on, so Peru's 65%
                # coverage could not be re-examined at all afterwards.
                entry['grid_matches'] = entry.get('matches')
                entry['rates'] = rates(dm)
                entry['splits'] = splits(dm)
                entry['matches'] = [list(m) for m in dm]
                entry['rates_source'] = ('dated rounds (per-fixture rows with dates; '
                                         'the grid is kept as grid_matches)')
            else:
                entry['rates_source'] = 'results grid (dated rounds not a superset)'
            newest = max(d[0] for d in all_dated)
            report.append(f'    es-rounds {league}: {len(all_dated)} dated results '
                          f'across {len(pages)} page(s), newest {newest}'
                          + (f' ({tot_und} scored rows still undated)' if tot_und else ''))
        doc[league] = entry
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

    rt = [(None, [['Local', 'Resultado', 'Visita', 'Estadio', 'Fecha', 'Hora'],
                  ['Alpha', '2-1', 'Beta', 'Ground', '30 de enero', '20:00'],
                  ['Beta', '0 \u2013 0', 'Gamma', 'Ground', '6 de febrero', '20:00'],
                  ['Gamma', '', 'Alpha', 'Ground', '13 de marzo', '20:00'],
                  ['Alpha', '1-0', 'Gamma', 'Ground', 'TBD', '20:00']])]
    mx = [('Alpha FC', 'Beta FC', 2, 1), ('Beta FC', 'Gamma', 0, 0)]
    dtd = [('2026-01-30', 'Alpha FC', 'Beta FC', 2, 1), ('2026-02-06', 'Beta FC', 'Gamma', 0, 0)]
    a, d, _, (sup, cov) = cross_check(mx, dtd)
    chk(a == 2 and d == 0 and sup, 'identical readings agree and count as a superset')
    a2, d2, s2, (_s2, _c2) = cross_check(mx, [('2026-01-30', 'Alpha FC', 'Beta FC', 3, 1)])
    chk(d2 == 1 and s2[0][2] == [(2, 1)] and s2[0][3] == [(3, 1)],
        'a scoreline that differs between readers is REPORTED with both values')
    # SPLIT SEASON: the same pair meets twice at the same ground. Both readers
    # see both results, so this is agreement, not conflict.
    a4, d4, _, (sup4, _c4) = cross_check(
        [('Santa Fe', 'America', 4, 0), ('Santa Fe', 'America', 0, 0)],
        [('2026-05-12', 'Santa Fe', 'America', 4, 0),
         ('2026-08-22', 'Santa Fe', 'America', 0, 0)])
    chk(a4 == 1 and d4 == 0 and sup4, 'a pair that meets twice with different scores AGREES')
    a5, d5, _, (sup5, _c5) = cross_check([('Santa Fe', 'America', 4, 0)],
                            [('2026-05-12', 'Santa Fe', 'America', 4, 0),
                             ('2026-08-22', 'Santa Fe', 'America', 0, 0)])
    chk(d5 == 1 and sup5, 'a GRID missing one meeting is caught, and dated reads as the superset')
    _, _, _, (sup6, _c6) = cross_check([('A', 'B', 9, 9)], [('2026-01-01', 'A', 'B', 1, 0)])
    chk(not sup6, 'dated is NOT a superset when the grid holds a score it lacks')
    chk(join_key('Cusco FC') == join_key('Cusco') == 'cusco',
        'club furniture is stripped for the cross-source join')
    chk(join_key('FBC Melgar') == 'melgar' and join_key('FC Cajamarca') == 'cajamarca',
        'prefixes too, in either position')
    chk(norm_team('Cusco FC') == 'cusco fc',
        'but the STORED name keeps whatever the source published')
    chk(join_key('FC') == 'fc', 'a club whose whole name is furniture keeps it')
    _, dcol, scol, (supcol, _) = cross_check(
        [('Nacional', 'X', 1, 0), ('Nacional FC', 'X', 2, 0)],
        [('2026-01-01', 'Nacional', 'X', 1, 0)])
    chk(any(s[0] == 'JOIN COLLISION' for s in scol) and not supcol,
        'if stripping merges two DIFFERENT clubs, the join is reported unsafe')

    a3, d3, _, (_s3, _c3) = cross_check(mx, [('2026-01-30', 'alpha fc', 'BETA FC', 2, 1)])
    chk(a3 == 1 and d3 == 0, 'the cross-check joins on normalised names, not exact case')

    # ROWSPAN: the exact shape that lost every second date. One 'Fecha' cell
    # spans three matches; rows 2 and 3 carry no date cell of their own.
    span_html = (
        '<table class="wikitable">'
        '<tr><th>Local</th><th>Resultado</th><th>Visita</th><th>Fecha</th><th>Hora</th></tr>'
        '<tr><td>A</td><td>1-0</td><td>B</td><td rowspan="3">30 de enero</td><td>15:00</td></tr>'
        '<tr><td>C</td><td>2-2</td><td>D</td><td>18:00</td></tr>'
        '<tr><td>E</td><td>0-1</td><td>F</td><td>20:30</td></tr>'
        '<tr><td>G</td><td>3-1</td><td>H</td><td>6 de febrero</td><td>17:00</td></tr>'
        '</table>')
    sp_p = Tables(); sp_p.feed(span_html)
    rows = sp_p.out[0][1]
    chk(all(len(r) == 5 for r in rows), f'every row is rebuilt to full width: {[len(r) for r in rows]}')
    chk(rows[2][3] == '30 de enero' and rows[3][3] == '30 de enero',
        'a rowspan date is carried into the rows it spans')
    chk(rows[4][3] == '6 de febrero', 'the span stops when its count runs out')
    sd, sund = read_rounds(sp_p.out, 2026)
    chk(len(sd) == 4 and sund == 0, f'all four scored rows now carry dates ({len(sd)}, {sund} undated)')
    chk(sd[1] == ('2026-01-30', 'C', 'D', 2, 2), f'the spanned row parses fully: {sd[1]}')

    titled = [(None, [['Fecha 1'],
                      ['Local', 'Resultado', 'Visita', 'Estadio', 'Fecha', 'Hora'],
                      ['U de Chile', '0-0', 'Audax', 'Nacional', '30 de enero', '20:00']])]
    dt, _ = read_rounds(titled, 2026)
    chk(len(dt) == 1 and dt[0][1] == 'U de Chile',
        'a one-cell TITLE row above the header does not hide the table')

    d, und = read_rounds(rt, 2026)
    chk(len(d) == 2, f'only rows with BOTH a score and a date are taken, got {len(d)}')
    chk(und == 1, 'a scored row with an unparseable date is COUNTED, not silently dropped')
    chk(d[0] == ('2026-01-30', 'Alpha', 'Beta', 2, 1), f'row parses in full: {d[0]}')
    chk(parse_es_date('6 de febrero', 2026) == '2026-02-06', 'spanish date -> iso')
    chk(parse_es_date('sometime', 2026) is None, 'an unparseable date returns None, never a guess')

    rows_v = [('2026-01-01', 'Bolivar', 'X', 1, 0), ('2026-02-01', 'Bolívar', 'Y', 2, 0),
              ('2026-03-01', 'Bolivar', 'Z', 0, 1)]
    cv, mg = canonicalise(rows_v, (1, 2))
    chk(len({r[1] for r in cv}) == 1 and cv[0][1] == 'Bolivar',
        'accent variants collapse to the most frequent spelling')
    chk(mg == {'Bolivar': ['Bolivar', 'Bolívar']}, f'and the merge is reported: {mg}')
    fv = form_table(cv)
    chk(fv['Bolivar']['n'] == 3, 'the club now has ONE form record, not two half ones')
    cv2, mg2 = canonicalise([('2026-01-01', 'A', 'B', 1, 0)], (1, 2))
    chk(mg2 == {} and cv2[0][1] == 'A', 'clubs with one spelling are untouched')

    f = form_table([('2026-01-30', 'Alpha', 'Beta', 2, 1),
                    ('2026-02-06', 'Beta', 'Alpha', 3, 0),
                    ('2026-03-01', 'Alpha', 'Beta', 1, 1)])
    chk(f['Alpha']['form'] == 'DLW', f"form is NEWEST FIRST across home and away, got {f['Alpha']['form']}")
    chk(f['Beta']['form'] == 'DWL', 'the same fixtures read from the other side')
    chk(f['Alpha']['matches'][0]['date'] == '2026-03-01', 'newest match leads the list')
    chk(f['Alpha']['n'] == 3 and f['Alpha']['gf'] == 3, 'form counts goals for from the right side')

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
    chk(any('EMPTY' in line for line in rep),
        'a league with no usable source is REPORTED, not silently dropped')
    chk(any('Colombia' in line and 'HTTPError' in line for line in rep),
        'and each failed fetch is named with its error')

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

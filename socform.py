#!/usr/bin/env python3
"""socform.py — current team form for the board's soccer fixtures.

    python3 socform.py                     # form for the board's soccer teams
    python3 socform.py "Necaxa" "Racing Club"
    python3 socform.py --selftest

The last missing piece of "consider form for every single pick": history said
what a LEAGUE does, nothing said what a TEAM has done lately. football-data
.co.uk's current-season files (Europe 26/27 already filling, the new/ country
files carrying 2026 rows for MLS, Argentina, Brazil, Mexico, Japan, China)
give every team's recent results with dates.

For each team: last six matches inside a 240-day window -- results string
newest first, goals for and against, points per game. Six because five-ish is
what talk of "form" means and one more blunts a single freak scoreline.

NAME MATCHING IS THE HAZARD AND IT IS NOT ALLOWED TO BE SILENT. The board
names teams the way FanDuel does ("New York City FC"); the CSVs name them the
way football-data does ("New York City"). Matching is normalised -- accents
folded, club furniture like FC/CF/SC stripped -- and every failure is REPORTED
as unmatched rather than quietly dropped, because a form report that silently
covers only the easy half of the slate is worse than none: it reads complete.

WHAT SIX MATCHES IS ALLOWED TO SAY. Six results is a mood, not a rating. The
number exists to catch "this side has lost five straight and the board still
prices last month's team" -- the Hammarby-shaped miss -- never to out-price
the market on its own.
"""
import csv, io, json, os, sys, unicodedata, urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'socform.json')
BASE = "https://www.football-data.co.uk"
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"

MMZ_CUR = ['2627', '2526']            # current European season, plus the tail
MMZ_DIVS = ['E0', 'E1', 'SP1', 'I1', 'D1', 'F1', 'N1', 'P1', 'B1',
            'T1', 'G1', 'SC0']    # Turkey, Greece, Scotland -- all on the board
# The unmatched tail on 8/13 was 329 names and MOST were not join failures
# at all -- they were whole leagues never pulled. football-data's new/ folder
# carries sixteen countries; six were being read. Every one below has
# fixtures on the current board.
NEW = ['USA', 'MEX', 'ARG', 'BRA', 'JPN', 'CHN',
       'DNK', 'FIN', 'NOR', 'POL', 'RUS', 'SWE', 'AUT', 'ROU', 'SWZ', 'IRL']
WINDOW_DAYS = 240
LAST_N = 6

STRIP = {'fc', 'cf', 'sc', 'afc', 'cd', 'ca', 'club', 'de', 'fk', 'if',
         'bk', 'sk', 'ac', 'as', 'ii'}


# Hand-verified joins the normaliser cannot make. Each one was checked against
# the CSV by eye; an alias here is a claim that two spellings are one club,
# and a wrong claim is the Inter-Milan bug with extra steps. Keys and values
# are both post-norm().
ALIAS = {
    'sporting lisbon': 'sp lisbon',
    'braga': 'sp braga',
    'fortuna sittard': 'for sittard',
    'besiktas jk': 'besiktas',
}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', 'replace')


def norm(name):
    """Fold accents, drop punctuation and club furniture, lowercase.
    'Necaxa' == 'Club Necaxa'; 'América' == 'America'."""
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = ''.join(c if c.isalnum() or c == ' ' else ' ' for c in s)
    toks = [t for t in s.split() if t not in STRIP]
    return ' '.join(toks)


def parse_date(d):
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(d.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def add_rows(text, kind, acc):
    """Fold one CSV into acc: {norm_team: [(date, gf, ga)]}. Unplayed rows and
    unparseable dates are skipped -- a missing score is not a 0-0 here either."""
    hk, ak = ('HomeTeam', 'AwayTeam') if kind == 'mmz' else ('Home', 'Away')
    gk, qk = ('FTHG', 'FTAG') if kind == 'mmz' else ('HG', 'AG')
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        d = parse_date(row.get('Date') or '')
        h, a = (row.get(hk) or '').strip(), (row.get(ak) or '').strip()
        try:
            hg, ag = int(float(row.get(gk))), int(float(row.get(qk)))
        except (TypeError, ValueError):
            continue
        if not (d and h and a):
            continue
        acc.setdefault(norm(h), {'name': h, 'rows': []})['rows'].append((d, hg, ag))
        acc.setdefault(norm(a), {'name': a, 'rows': []})['rows'].append((d, ag, hg))
        n += 1
    return n


def form_of(rows, today=None, last=LAST_N):
    """Newest-first summary of the recent window, or None if fewer than three
    recent matches -- three is the floor under calling anything 'form'."""
    today = today or date.today()
    cut = today - timedelta(days=WINDOW_DAYS)
    recent = sorted((r for r in rows if cut <= r[0] <= today))[-last:]
    if len(recent) < 3:
        return None
    recent = recent[::-1]
    letters = ''.join('W' if gf > ga else 'D' if gf == ga else 'L'
                      for _, gf, ga in recent)
    pts = sum(3 if gf > ga else 1 if gf == ga else 0 for _, gf, ga in recent)
    return {'form': letters, 'n': len(recent),
            'ppg': round(pts / len(recent), 2),
            'gf': round(sum(gf for _, gf, _ in recent) / len(recent), 2),
            'ga': round(sum(ga for _, _, ga in recent) / len(recent), 2),
            'newest': recent[0][0].isoformat()}


def lookup(acc, name):
    """(entry, how) by normalised name. Containment counts only when the
    SHORTER of the two names is six-plus characters: the first live run
    joined 'FC Inter Turku' to Inter Milan and 'Lillestrom' to Lille because
    the length floor sat on the query while the matched key could be five
    letters. A refused join prints as unmatched, which is honest; a false
    join prints as form, which is a lie with decimals."""
    q = ALIAS.get(norm(name), norm(name))
    if q in acc:
        return acc[q], 'exact'
    hits = [k for k in acc
            if (q in k or k in q) and min(len(q), len(k)) >= 6]
    if len(hits) == 1:
        return acc[hits[0]], f'via {acc[hits[0]]["name"]}'
    return None, 'unmatched'


def board_teams():
    """Soccer team names on the current board, from the feed itself."""
    try:
        import other
    except Exception:
        return []
    out = []
    for line in other.OTHER_RAW.strip().split('\n'):
        p = line.split('|')
        if len(p) == 6 and p[0] == 'SOC' and p[2] != 'Draw':
            out.append((p[2], p[1], p[5]))
    return out


def main():
    acc = {}
    for ssn in MMZ_CUR:
        for div in MMZ_DIVS:
            try:
                add_rows(get(f"{BASE}/mmz4281/{ssn}/{div}.csv"), 'mmz', acc)
            except Exception:
                continue
    for code in NEW:
        try:
            add_rows(get(f"{BASE}/new/{code}.csv"), 'new', acc)
        except Exception as e:
            print(f"  {code}: {type(e).__name__}")
    print(f"  {len(acc)} teams accumulated\n")
    want = [(n, None, None) for n in sys.argv[1:] if not n.startswith('--')]
    if not want:
        seen = set()
        for name, grp, t in board_teams():
            if name not in seen:
                seen.add(name)
                want.append((name, grp, t))
    hit, miss, table = 0, [], {}
    for name, grp, _ in want:
        e, how = lookup(acc, name)
        f = form_of(e['rows']) if e else None
        if f:
            hit += 1
            table[name] = {**f, 'matched': how}
            print(f"  {name[:26]:<27} {f['form']:<7} ppg {f['ppg']:<5} "
                  f"gf {f['gf']:<5} ga {f['ga']:<5} (last {f['newest']})"
                  + (f"  [{how}]" if how != 'exact' else ''))
        else:
            miss.append(name)
    if miss:
        print(f"\n  UNMATCHED OR THIN ({len(miss)}): " + '; '.join(miss[:20]))
        print("  -- unmatched is a statement about the JOIN, not the team. Do "
              "not read absence as bad form.")
    with open(OUT, 'w') as fh:
        json.dump({'built': date.today().isoformat(), 'teams': table,
                   'unmatched': miss}, fh, indent=1)
    print(f"\n  {hit} matched / {len(miss)} not. wrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    chk(norm('Club Necaxa') == norm('Necaxa') and norm('América') == 'america',
        "club furniture and accents fold away, so FanDuel and the CSVs meet")
    chk(norm('New York City FC') == 'new york city',
        "suffix FC drops without touching the city name")

    acc = {}
    mmz = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
           "E0,01/08/2026,Arsenal,Chelsea,2,0\n"
           "E0,08/08/2026,Chelsea,Arsenal,1,1\n"
           "E0,bad,Chelsea,Arsenal,1,1\n"
           "E0,09/08/2026,Wolves,,2,1\n")
    n = add_rows(mmz, 'mmz', acc)
    chk(n == 2 and len(acc['arsenal']['rows']) == 2,
        "each match lands on BOTH teams; junk dates and blank names are dropped")
    chk(acc['chelsea']['rows'][0] == (date(2026, 8, 1), 0, 2),
        "goals are oriented per team -- Chelsea away 0-2 is gf 0 ga 2")

    today = date(2026, 8, 13)
    rows = [(date(2026, 8, 13) - timedelta(days=k * 7), (k % 3), 1)
            for k in range(8)]
    f = form_of(rows, today=today)
    chk(f['n'] == 6 and f['form'][0] == 'L',
        "form is the last six inside the window, newest first")
    old = [(date(2025, 1, 1), 3, 0)] * 6
    chk(form_of(old, today=today) is None,
        "six wins from eighteen months ago are NOT form -- outside the window "
        "the answer is 'unknown', never 'in form'")
    chk(form_of(rows[:2], today=today) is None,
        "two matches is below the floor for calling anything form")

    acc2 = {norm('Union Berlin'): {'name': 'Union Berlin', 'rows': rows},
            norm('Philadelphia Union'): {'name': 'Philadelphia Union', 'rows': rows}}
    e, how = lookup(acc2, 'Philadelphia Union')
    chk(e and e['name'] == 'Philadelphia Union', "exact wins before fuzzy")
    e2, how2 = lookup(acc2, 'Union')
    chk(e2 is None and how2 == 'unmatched',
        "an ambiguous or too-short name refuses to guess between two Unions")

    acc3 = {'inter': {'name': 'Inter', 'rows': rows},
            'lille': {'name': 'Lille', 'rows': rows}}
    chk(lookup(acc3, 'FC Inter Turku')[0] is None,
        "Inter Turku does NOT join to Inter Milan -- the first live run made "
        "exactly this false join and printed Serie A form as Finnish form")
    chk(lookup(acc3, 'Lillestrom')[0] is None,
        "and Lillestrom does not join to Lille: containment needs the SHORTER "
        "name at six-plus characters, whichever side it is on")
    acc4 = {'nijmegen': {'name': 'Nijmegen', 'rows': rows}}
    chk(lookup(acc4, 'NEC Nijmegen')[0] is not None,
        "while NEC Nijmegen still reaches Nijmegen, which is a real join")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

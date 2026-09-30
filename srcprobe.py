#!/usr/bin/env python3
"""srcprobe.py — which data sources can the runner actually reach?

ROUND 5 (2026-09-30): the leagues today's board cannot price. An
international break left the big-5 dark and the real slate was Colombia,
Peru, Uruguay, Chile, Bolivia, El Salvador and USL -- every one of them
UNMEASURED in socbase, because football-data.co.uk (which feeds sococalib
and socform) simply does not publish those countries. Its whole /new/
folder is ARG/AUT/BRA/CHN/DNK/FIN/IRL/JPN/MEX/NOR/POL/ROU/RUS/SWE/SWZ/USA.

So before a single line of a fetcher gets written: find out what the runner
can REACH and what SHAPE the data is in. The container cannot reach
Wikipedia or football-data at all (egress); only this runner can, which is
why the look is a committed probe and not a local experiment.

Two questions per league:
  1) does a season page exist under any of the slugs we would guess, and
  2) does it carry a table we could actually parse into results --
     a results MATRIX (home x away grid) or a dated fixture list.
Both get dumped, because the matrix has no dates (fine for league base
rates, useless for recent form) and the fixture list has both.
"""
import re, sys, urllib.request
from html.parser import HTMLParser

BUA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Tables(HTMLParser):
    """Every <table class=wikitable>: (preceding heading, rows of cell texts)."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.head = [], ''
        self.t = None          # current table rows
        self.row = self.cell = None
        self.in_h = 0

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
            self.out.append((self.head, self.t)); self.t = None
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
    r = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": BUA}), timeout=timeout)
    return r.read().decode("utf-8", "replace")


HOSTS = [
    "https://en.wikipedia.org/wiki/Main_Page",
    "https://www.football-data.co.uk/new/ARG.csv",
    "https://raw.githubusercontent.com/openfootball/world-cup/master/README.md",
    "https://fixturedownload.com/results/usl-championship-2026",
    "https://es.wikipedia.org/wiki/Wikipedia:Portada",
]

# Slug guesses per league. These leagues run Apertura/Clausura calendars and
# Wikipedia names them inconsistently, so guess several and report which live.
LEAGUES = {
    "Colombia Primera A": [
        "2026_Categor%C3%ADa_Primera_A_season",
        "2026_Categor%C3%ADa_Primera_A",
    ],
    "Peru Liga 1": [
        "2026_Liga_1_(Peru)", "2026_Peruvian_Primera_Divisi%C3%B3n",
        "2026_Liga_1_(Peruvian_football)",
    ],
    "Uruguay Primera": [
        "2026_Uruguayan_Primera_Divisi%C3%B3n",
        "2026_Uruguayan_Primera_Division",
    ],
    "Chile Primera": [
        "2026_Chilean_Primera_Divisi%C3%B3n",
        "2026_Campeonato_Nacional_(Chile)",
    ],
    "USL Championship": [
        "2026_USL_Championship_season", "2026_USL_Championship",
    ],
    "Bolivia Primera": [
        "2026_Bolivian_Primera_Divisi%C3%B3n",
    ],
}

SCORE = re.compile(r"^\d{1,2}\s*[-\u2013]\s*\d{1,2}$")


def looks_like_matrix(rows):
    """A results grid: many cells that are bare scores like '2-1'."""
    hits = sum(1 for r in rows for c in r if SCORE.match(c.strip()))
    return hits >= 20, hits


def looks_like_fixtures(rows):
    """A dated fixture list: a header naming a date and a score/result."""
    if not rows:
        return False
    h = " ".join(rows[0]).lower()
    return ("date" in h) and any(k in h for k in ("score", "result", "home", "away"))


API_EN = "https://en.wikipedia.org/w/api.php"
API_ES = "https://es.wikipedia.org/w/api.php"


def api(base, **kw):
    import json as _j, urllib.parse
    kw.setdefault("format", "json")
    url = base + "?" + urllib.parse.urlencode(kw)
    return _j.loads(get(url, timeout=25))


def fulltext(base, q, n=8):
    """action=query&list=search -- real full-text search. opensearch ranked
    2012 above 2026 for these leagues, which is how round 6 nearly graded a
    2026 slate against a fourteen-year-old season."""
    try:
        r = api(base, action="query", list="search", srsearch=q, srlimit=n)
        return [h["title"] for h in r["query"]["search"]]
    except Exception as e:
        return [f"<{type(e).__name__}>"]


def links_2026(base, title):
    """Every outgoing link on a league's parent article that names 2026."""
    try:
        r = api(base, action="parse", page=title, prop="links")
        return [l["*"] for l in r["parse"]["links"]
                if "2026" in l["*"] and l.get("exists") is not None]
    except Exception:
        return []


print("=== ROUND 7: CHILE + URUGUAY, EN AND ES ===")
QUERIES = {
    "Chile":   [(API_EN, "2026 Chilean Primera Division"),
                (API_ES, "Campeonato Nacional 2026 Chile"),
                (API_ES, "Primera Division de Chile 2026")],
    "Uruguay": [(API_EN, "2026 Uruguayan Primera Division"),
                (API_ES, "Campeonato Uruguayo 2026"),
                (API_ES, "Primera Division de Uruguay 2026")],
    "Bolivia": [(API_ES, "Division de Futbol Profesional 2026"),
                (API_EN, "2026 Bolivian Primera Division")],
}
for country, qs in QUERIES.items():
    print(f"\n-- {country}")
    for base, q in qs:
        wiki = "en" if base is API_EN else "es"
        print(f"   [{wiki}] {q!r}")
        for t in fulltext(base, q)[:6]:
            print(f"        {t}")

print("\n=== PARENT-ARTICLE 2026 LINKS ===")
for base, page in ((API_ES, "Primera Divisi\u00f3n de Chile"),
                   (API_ES, "Primera Divisi\u00f3n de Uruguay"),
                   (API_EN, "Chilean Primera Divisi\u00f3n"),
                   (API_EN, "Uruguayan Primera Divisi\u00f3n")):
    wiki = "en" if base is API_EN else "es"
    ls = links_2026(base, page)
    print(f"  [{wiki}] {page}: {ls[:10] if ls else 'none'}")

print("\n=== DATED FIXTURE TABLES? (what Recent Form needs) ===")
# A results MATRIX has no dates. Do these pages carry a per-round fixture
# list with a date column anywhere? Check the leagues we already parse.
DATE_RE = re.compile(r"(date|fecha)", re.I)
for wiki, slug in (("en", "2026_Categor%C3%ADa_Primera_A_season"),
                   ("es", "Categor%C3%ADa_Primera_A_2026"),
                   ("en", "2026_Liga_1_(Peru)"),
                   ("es", "Liga_1_2026")):
    try:
        html = get(f"https://{wiki}.wikipedia.org/wiki/{slug}")
    except Exception as e:
        print(f"  [{wiki}] {slug}: {type(e).__name__}")
        continue
    p = Tables(); p.feed(html)
    hits = 0
    for h, t in p.out:
        if not t or not t[0]:
            continue
        hdr = " | ".join(t[0])
        if DATE_RE.search(hdr) and len(t) > 6:
            hits += 1
            print(f"  [{wiki}] {slug}")
            print(f"        DATED TABLE [{h[:28]}] {len(t)} rows :: {hdr[:90]}")
            for row in t[1:3]:
                print(f"          {' | '.join(c[:20] for c in row[:7])}")
    if not hits:
        print(f"  [{wiki}] {slug}: no dated table (matrix only)")

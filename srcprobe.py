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


import urllib.parse

API_ES = "https://es.wikipedia.org/w/api.php"


def api(base, **kw):
    import json as _j
    kw.setdefault("format", "json")
    return _j.loads(get(base + "?" + urllib.parse.urlencode(kw), timeout=25))


def fulltext(base, q, n=8):
    try:
        r = api(base, action="query", list="search", srsearch=q, srlimit=n)
        return [h["title"] for h in r["query"]["search"]]
    except Exception as e:
        return [f"<{type(e).__name__}>"]


SC = re.compile(r"^(\d{1,2})\s*[-\u2013\u2014:]\s*(\d{1,2})$")
DATE = re.compile(r"(\d{1,2})\s*de\s*([a-z\u00e1\u00e9\u00ed\u00f3\u00fa]+)", re.I)

print("=== ROUND 10a: WHY do half the scored rows have no date? ===")
for tag, url in (("Chile", "https://es.wikipedia.org/wiki/Liga_de_Primera_2026"),
                 ("Colombia", "https://es.wikipedia.org/wiki/Categor%C3%ADa_Primera_A_2026")):
    try:
        html = get(url)
    except Exception as e:
        print(f"  {tag}: {type(e).__name__}"); continue
    p = Tables(); p.feed(html)
    shown = 0
    for h, rows in p.out:
        hrow = None
        for k in range(min(3, len(rows))):
            cells = [c.strip().lower() for c in rows[k]]
            if any(c.startswith("local") for c in cells) and any(c.startswith("resultado") for c in cells):
                hrow = k; break
        if hrow is None:
            continue
        for row in rows[hrow + 1:]:
            has_score = any(SC.match(c.strip()) for c in row)
            has_date = any(DATE.search(c) for c in row)
            if has_score and not has_date and shown < 8:
                shown += 1
                print(f"  {tag} [{(h or '?')[:20]}] hdr={rows[hrow]}")
                print(f"     ROW({len(row)}): {row}")
    if not shown:
        print(f"  {tag}: every scored row also carried a date")

print()
print("=== ROUND 10b: Colombia Finalizacion + Peru round pages ===")
for q in ("Torneo Finalizacion 2026 Colombia",
          "Categoria Primera A 2026 Colombia",
          "Liga1 2026 Peru Torneo Clausura",
          "Liga1 2026 Peru"):
    print(f"  {q!r}: {fulltext(API_ES, q)[:6]}")

print()
print("=== ROUND 10c: do those pages carry Local/Resultado tables? ===")
for slug in ("Torneo_Finalizaci%C3%B3n_2026_(Colombia)",
             "Torneo_Apertura_2026_(Colombia)",
             "Liga1_2026_(Per%C3%BA)",
             "Categor%C3%ADa_Primera_A_2026"):
    try:
        html = get(f"https://es.wikipedia.org/wiki/{slug}")
    except Exception as e:
        print(f"  {slug}: {type(e).__name__}"); continue
    p = Tables(); p.feed(html)
    nround = ndated = 0
    for h, rows in p.out:
        for k in range(min(3, len(rows))):
            cells = [c.strip().lower() for c in rows[k]]
            if any(c.startswith("local") for c in cells) and any(c.startswith("resultado") for c in cells):
                nround += 1
                ndated += sum(1 for r in rows[k+1:] if any(DATE.search(c) for c in r))
                break
    print(f"  {slug}: {len(p.out)} tables, {nround} round-tables, {ndated} rows with a date")

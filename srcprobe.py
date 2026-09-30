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
API_EN = "https://en.wikipedia.org/w/api.php"


def api(base, **kw):
    import json as _j, urllib.parse
    kw.setdefault("format", "json")
    return _j.loads(get(base + "?" + urllib.parse.urlencode(kw), timeout=25))


def fulltext(base, q, n=6):
    try:
        r = api(base, action="query", list="search", srsearch=q, srlimit=n)
        return [h["title"] for h in r["query"]["search"]]
    except Exception as e:
        return [f"<{type(e).__name__}>"]


SC = re.compile(r"^\d{1,2}\s*[-\u2013\u2014:]\s*\d{1,2}$")
ROUND_HDR = re.compile(r"(jornada|fecha|round|local|visitante)", re.I)

print("=== ROUND 9: a DATED or ORDERED results source ===")
print("Recent Form needs order. A matrix has none. Two routes tested:")
print("  (a) Spanish Wikipedia round-by-round pages")
print("  (b) the odds API /scores endpoint for these league keys\n")

print("--- (a) es.wikipedia season pages ---")
QS = {
  "Colombia": "Categoria Primera A 2026 Torneo Finalizacion",
  "Peru":     "Liga 1 2026 Peru temporada",
  "Chile":    "Liga de Primera 2026",
  "Bolivia":  "Division Profesional 2026 Bolivia",
}
for country, q in QS.items():
    titles = fulltext(API_ES, q)
    print(f"  {country}: {titles[:5]}")
    for t in titles[:3]:
        slug = t.replace(" ", "_")
        try:
            html = get(f"https://es.wikipedia.org/wiki/{urllib.parse.quote(slug)}")
        except Exception as e:
            continue
        p = Tables(); p.feed(html)
        dated = 0
        for h, rows in p.out:
            if not rows or not rows[0]:
                continue
            hdr = " | ".join(rows[0])
            nsc = sum(1 for r in rows for c in r if SC.match(c.strip()))
            if ROUND_HDR.search(hdr) and nsc >= 5:
                dated += 1
                if dated <= 2:
                    print(f"      [{t}] ROUND TABLE [{(h or '?')[:24]}] {len(rows)}r scores={nsc}")
                    print(f"         hdr: {hdr[:88]}")
                    for row in rows[1:3]:
                        print(f"         {' | '.join(c[:18] for c in row[:8])}")
        if dated:
            break

print("\n--- (b) odds API /scores for these leagues ---")
import os
key = os.environ.get("ODDS_API_KEY", "")
if not key:
    print("  NO ODDS_API_KEY in this job -- cannot test")
else:
    try:
        cat = api_url = None
        raw = get(f"https://api.the-odds-api.com/v4/sports/?apiKey={key}&all=true")
        import json as _j
        cat = _j.loads(raw)
        socc = [s["key"] for s in cat if s.get("group") == "Soccer"]
        for want in ("colombia", "peru", "chile", "bolivia", "uruguay", "usl"):
            hits = [k for k in socc if want in k]
            print(f"  catalog '{want}': {hits if hits else 'ABSENT'}")
        for k in [x for x in socc if any(w in x for w in ("colombia", "peru", "chile", "bolivia"))]:
            try:
                sc = _j.loads(get(f"https://api.the-odds-api.com/v4/sports/{k}/scores/?daysFrom=3&apiKey={key}"))
                done = [e for e in sc if e.get("completed")]
                print(f"    {k}: {len(sc)} events, {len(done)} completed, "
                      f"sample={[(e.get('home_team'), e.get('commence_time')[:10]) for e in done[:2]]}")
            except Exception as e:
                print(f"    {k}: scores -> {type(e).__name__}")
    except Exception as e:
        print("  catalog fetch failed:", type(e).__name__, str(e)[:80])

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

import urllib.parse

BUA2 = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def probe(url, label, post=None, referer=None, note=''):
    hdrs = {'User-Agent': BUA2, 'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9'}
    if referer:
        hdrs['Referer'] = referer
    if post is not None:
        hdrs['X-Requested-With'] = 'XMLHttpRequest'
        hdrs['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        req = urllib.request.Request(url, data=post, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        print(f"  OK    {len(body):>9,}b  {label}  {note}")
        return body
    except Exception as e:
        code = getattr(e, 'code', '')
        print(f"  FAIL  {type(e).__name__}{' ' + str(code) if code else ''}  {label}  {note}")
        return None


import gzip as _gz


def body_text(b):
    if b[:2] == b'\x1f\x8b':
        b = _gz.decompress(b)
    return b.decode('utf-8', 'replace')


print("=== ROUND 15: is understat's 200 a real page or a challenge? ===")
b = probe("https://understat.com/league/EPL/2026", "understat EPL 2026")
if b:
    t = body_text(b)
    print(f"     {len(t):,} chars")
    low = t.lower()
    for marker in ('cloudflare', 'just a moment', 'challenge', 'cf-', 'captcha',
                   'enable javascript', 'ray id'):
        if marker in low:
            print(f"     CHALLENGE MARKER: {marker!r}")
    print("     --- first 400 chars ---")
    print("     " + t[:400].replace('\n', ' ')[:400])
    print("     --- title ---")
    import re as _re
    ti = _re.search(r'<title[^>]*>(.*?)</title>', t, _re.S | _re.I)
    print("     " + (ti.group(1).strip()[:120] if ti else 'no title'))

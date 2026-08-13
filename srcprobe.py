#!/usr/bin/env python3
"""srcprobe.py — which data sources can the runner actually reach?

Round 4b: CFL table structure. Round 4 found the route (Wikipedia 200;
ESPN 403, fixturedownload absent). Before a parser exists, LOOK at the
page: dump every wikitable's nearest heading, header row, and first two
data rows for two season pages — structure drift across seasons is the
thing that silently breaks scrapers, so both get dumped before one line
of cflhist is written. The container cannot reach Wikipedia (egress);
only this runner can, which is why the peek is a committed probe and not
a local look.
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


for yr in (2025, 2024):
    url = f"https://en.wikipedia.org/wiki/{yr}_CFL_season"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": BUA}), timeout=30)
        html = r.read().decode('utf-8', 'replace')
    except Exception as e:
        print(f"== {yr}: FAIL {type(e).__name__} {getattr(e, 'code', '')}")
        continue
    p = Tables(); p.feed(html)
    print(f"== {yr}: {len(html)}B, {len(p.out)} wikitable(s)")
    for head, rows in p.out:
        if not rows:
            continue
        # only tables that smell like games: a score-like cell somewhere early
        smell = any(re.search(r'\b\d{1,2}\s*[–-]\s*\d{1,2}\b', c) or ' at ' in c
                    for row in rows[:4] for c in row)
        if not smell:
            continue
        print(f"  [{head}] {len(rows)} rows")
        for row in rows[:3]:
            print(f"    {' | '.join(c[:34] for c in row[:9])}")

#!/usr/bin/env python3
"""srcprobe.py — which data sources can the runner actually reach?

Round 4: CFL. Round 3 closed SBR (affiliate shell, zero file links; MLB
posted-line history now self-collected by linelog.py). CFL is the last OPEN
source item: fixturedownload 404'd in round 2. CFL legs appear on FanDuel's
Thursday/Friday boards, so before one is ever priced above a hunch we need
results history (base rates: totals distribution, home edge — nflhist's
shape) and, if anything free carries them, historical odds. Candidates:
ESPN's public scoreboard API (works for MLS with a browser UA), alternate
fixturedownload spellings, and Wikipedia season pages as a last resort for
results-only.
"""
import re, sys, urllib.request

BUA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
T = [
 ("espn cfl scoreboard", "https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard", {"User-Agent": BUA}),
 ("espn cfl 2025 wk1",   "https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard?dates=20250605-20250612", {"User-Agent": BUA}),
 ("fixturedl cfl list",  "https://fixturedownload.com/results/cfl-2025", {"User-Agent": BUA}),
 ("fixturedl feed 2025", "https://fixturedownload.com/feed/json/cfl-2025", {"User-Agent": BUA}),
 ("wikipedia 2025 CFL",  "https://en.wikipedia.org/wiki/2025_CFL_season", {"User-Agent": BUA}),
]

for name, url, hdr in T:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=25)
        b = r.read(300000)
        head = b[:200].decode("utf-8", "replace").replace("\n", " | ")
        # a scoreboard answer is only useful if it carries scores/dates
        marks = sum(1 for w in (b"score", b"competitions", b"winner") if w in b[:100000])
        print(f"  {name:<19} HTTP {r.status:<4} {len(b):>7}B  marks={marks}  {head[:80]}")
    except Exception as e:
        print(f"  {name:<19} FAIL {type(e).__name__} {getattr(e, 'code', '')}")

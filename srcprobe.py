#!/usr/bin/env python3
"""srcprobe.py — which historical data sources can the runner actually reach?

MLB now has an empirical grounding (f5hist, 6681 games). Soccer and WNBA have
none at all, and soccer is where today's money went. Before writing a module
against any source, find out what answers -- this is the same lesson as the
soccer catalog: an hour was spent inferring what an API had instead of asking.

Prints status, size and a content probe for every candidate.
"""
import json, sys, urllib.request
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"
T = [
 ("openfootball EPL 25/26",  "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json"),
 ("openfootball index",      "https://api.github.com/repos/openfootball/football.json/contents/2024-25"),
 ("football-data.org v4",    "https://api.football-data.org/v4/competitions"),
 ("statsapi MLB (control)",  "https://statsapi.mlb.com/api/v1/teams?sportId=1"),
 ("WNBA stats.nba.com",      "https://stats.nba.com/stats/leaguegamelog?LeagueID=10&Season=2025&SeasonType=Regular+Season&PlayerOrTeam=T"),
 ("WNBA data.nba.com",       "https://data.wnba.com/data/10s/prod/v1/2025/schedule.json"),
 ("ESPN WNBA scoreboard",    "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"),
 ("ESPN soccer scoreboard",  "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.conf/scoreboard"),
 ("TheSportsDB free",        "https://www.thesportsdb.com/api/v1/json/3/all_leagues.php"),
 ("fbref (scrape)",          "https://fbref.com/en/comps/9/Premier-League-Stats"),
]
for name, url in T:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25)
        b = r.read(300000)
        note = ""
        if b.strip()[:1] in (b"{", b"["):
            try:
                d = json.loads(b)
                note = (f"keys={list(d)[:5]}" if isinstance(d, dict)
                        else f"list of {len(d)}")
            except Exception:
                note = "json truncated"
        print(f"  {name:<26} HTTP {r.status:<4} {len(b):>7}B  {note}")
    except Exception as e:
        print(f"  {name:<26} FAIL {type(e).__name__} {getattr(e,'code','')}")

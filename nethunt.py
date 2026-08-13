#!/usr/bin/env python3
"""nethunt.py — which odds sources can the Actions runner actually reach?

Written 2026-08-13 after four dead ends in a row: The Odds API has no
Europa/Conference key, every aggregator is egress-blocked from the maintaining
session, and FanDuel's own sbapi refuses datacenter IPs. Before writing a
fifth scraper, find out what answers at all. Reachability first, parsing second.
"""
import json, sys, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TARGETS = [
    ("odds-api sports",   "https://api.the-odds-api.com/v4/sports?apiKey=x"),
    ("sofascore api",     "https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-08-13"),
    ("fd sbapi nj",       "https://sbapi.nj.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=soccer&_ak=FhMFpcPWXMeyZxOx"),
    ("fd sportsbook www", "https://sportsbook.fanduel.com/navigation/soccer"),
    ("oddsportal",        "https://www.oddsportal.com/football/europe/europa-league/"),
    ("oddspedia",         "https://oddspedia.com/football"),
    ("flashscore",        "https://www.flashscore.com/football/"),
    ("espn scoreboard",   "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa_qual/scoreboard"),
    ("espn conf qual",    "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.conf_qual/scoreboard"),
    ("bbc sport",         "https://www.bbc.com/sport/football/scores-fixtures"),
]
for name, url in TARGETS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(400000)
            print(f"  {name:<20} HTTP {r.status:<4} {len(body):>7} bytes  {r.headers.get('content-type','')[:30]}")
            if "espn" in name and body.strip().startswith(b"{"):
                d = json.loads(body)
                for e in d.get("events", [])[:40]:
                    print(f"      {e.get('date')}  {e.get('name')}")
    except Exception as e:
        print(f"  {name:<20} FAIL {type(e).__name__} {getattr(e,'code','')}")

#!/usr/bin/env python3
"""srcprobe.py — which data sources can the runner actually reach?

Round 2. Round 1 found openfootball (history, no form) and statsapi (MLB,
everything). Still missing: soccer WITH odds (to calibrate the de-vig the way
f5hist calibrated MLB), current-season soccer form, WNBA anything, UFC
history for Saturday's card, and NFL before September. Ask, don't infer.
"""
import json, sys, urllib.request
BUA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
T = [
 # soccer results WITH closing odds -- the de-vig calibration set
 ("fd.co.uk EPL 25/26",   "https://www.football-data.co.uk/mmz4281/2526/E0.csv", {}),
 ("fd.co.uk EPL 26/27",   "https://www.football-data.co.uk/mmz4281/2627/E0.csv", {}),
 ("fd.co.uk USA (MLS)",   "https://www.football-data.co.uk/new/USA.csv", {}),
 ("fd.co.uk MEX",         "https://www.football-data.co.uk/new/MEX.csv", {}),
 ("fd.co.uk ARG",         "https://www.football-data.co.uk/new/ARG.csv", {}),
 ("fd.co.uk BRA",         "https://www.football-data.co.uk/new/BRA.csv", {}),
 # current-season soccer form
 ("sportsdb MLS 2026",    "https://www.thesportsdb.com/api/v1/json/3/eventsseason.php?id=4346&s=2026", {}),
 ("espn MLS scoreboard",  "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard", {"User-Agent": BUA}),
 # WNBA, with the headers their own site sends
 ("cdn.wnba scoreboard",  "https://cdn.wnba.com/static/json/liveData/scoreboard/todaysScoreboard_10.json", {"User-Agent": BUA, "Referer": "https://www.wnba.com/"}),
 ("stats.wnba gamelog",   "https://stats.wnba.com/stats/leaguegamelog?LeagueID=10&Season=2026&SeasonType=Regular%20Season&PlayerOrTeam=T",
  {"User-Agent": BUA, "Referer": "https://www.wnba.com/", "Origin": "https://www.wnba.com",
   "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}),
 ("espn WNBA (brwsr UA)", "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard", {"User-Agent": BUA}),
 # UFC history
 ("ufc mdabbert odds",    "https://raw.githubusercontent.com/mdabbert/Ultimate-UFC-Dataset/master/ufc-master.csv", {}),
 ("ufc greco results",    "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/ufc_fight_results.csv", {}),
 # NFL, for September
 ("nflverse sched (new)",  "https://github.com/nflverse/nflverse-data/releases/download/schedules/sched_all.csv", {}),
 ("habitatring games",    "http://www.habitatring.com/games.csv", {}),
 ("nflverse games rel",   "https://github.com/nflverse/nflverse-data/releases/download/games/games.csv", {}),
 ("cfl fixturedownload",  "https://fixturedownload.com/feed/json/cfl-2026", {}),
 # historical MLB odds w/ totals lines -- would let FG totals be calibrated
 # like soccer's, and condition run distributions ON the posted line
 ("sbr mlb odds 2023",    "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlb%20odds%202023.xlsx", {}),
 ("sbr mlb odds 2024",    "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlb%20odds%202024.xlsx", {}),
]
for name, url, hdr in T:
    try:
        h = {"User-Agent": "Mozilla/5.0 (compatible; parlay-research/1.0)"}
        h.update(hdr)
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25)
        b = r.read(250000)
        head = b[:160].decode('utf-8', 'replace').replace('\n', ' | ')
        print(f"  {name:<22} HTTP {r.status:<4} {len(b):>7}B  {head[:90]}")
    except Exception as e:
        print(f"  {name:<22} FAIL {type(e).__name__} {getattr(e, 'code', '')}")

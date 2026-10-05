#!/usr/bin/env python3
"""Live F5 and full-game prices for tonight's MLB, to put against mlbform.

mlbform says the two games point opposite ways and says it from four numbers
each, so the only thing missing is what the board charges.

  NYY@TB   Schlittler 1.4 runs/start, Peralta 0.6 -- and both offences have
           scored about two F5 runs over ten games. Starter form implies a
           first-five total near 2; the blended environment figure says 4.05.
           That disagreement is the bet, in whichever direction the price sits.
  CWS@CLE  Kay 3.0 runs/start with an 0.84 HR/9, and the White Sox have scored
           4.8 F5 runs across ten games. Points the other way.

F5 lives on alternate_totals_1st_5_innings. NOT totals_h1, which is empty for
baseball and once produced a confident "F5 does not exist on FanDuel".
"""
import json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
WANT = ["totals_1st_5_innings", "alternate_totals_1st_5_innings",
        "h2h_1st_5_innings", "totals", "h2h", "spreads"]


def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())


def imp(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


evs = get(f"{BASE}/sports/baseball_mlb/events?apiKey={KEY}")
if not evs:
    print("no MLB events on the board"); sys.exit(0)
for e in evs[:4]:
    print(f"\n=== {e.get('away_team')} @ {e.get('home_team')}   "
          f"{e.get('commence_time')} ===")
    for k in WANT:
        try:
            d = get(f"{BASE}/sports/baseball_mlb/events/{e['id']}/odds/"
                    f"?apiKey={KEY}&regions=us&bookmakers={BOOK}"
                    f"&oddsFormat=american&markets={k}")
        except urllib.error.HTTPError as ex:
            print(f"  {k}: HTTP {ex.code}")
            continue
        rows = []
        for bk in d.get("bookmakers") or []:
            if bk.get("key") != BOOK:
                continue
            for m in bk.get("markets") or []:
                if m.get("key") != k:
                    continue
                rows += (m.get("outcomes") or [])
        if not rows:
            print(f"  {k}: nothing posted")
            continue
        print(f"  {k}:")
        for o in sorted(rows, key=lambda x: (float(x.get("point") or 0),
                                             str(x.get("name")))):
            pt = "" if o.get("point") is None else f"{float(o['point']):6.1f}"
            print(f"      {str(o.get('name')):8s} {pt:>6s}  {o.get('price'):+6d}"
                  f"   {imp(o.get('price'))*100:5.1f}%")

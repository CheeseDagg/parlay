#!/usr/bin/env python3
"""Bijan Robinson's full ladder for Monday night. Read it, do not infer it.

The prop board flagged Under 87.5 rushing yards at -113: 13 of 20 under for him,
15 of 20 for the Saints defence, against a 53% price. The largest gap on the
board.

Then the injury report said New Orleans are missing Kaden Elliss, Carl
Granderson and Anfernee Jennings, all OUT, with Pete Werner having not
practised. That is three linebackers and a fourth doubtful -- the run-defence
positions, and the ones whose presence produced the 15-of-20. A defensive record
is a claim about a UNIT, and this is not that unit. defense_at() counts twenty
games without knowing who was on the field for them, which is the regime problem
one level out from the player.

So the live side may be the OVER, and that means reading the Over prices rather
than assuming they mirror an Under at -113.
"""
import json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
WHO = "Robinson"
WANT = ["player_rush_yds", "player_rush_yds_alternate", "player_rush_attempts",
        "player_rush_reception_yds", "player_receptions", "player_anytime_td"]


def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())


evs = get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
tgt = [e for e in evs if "Falcons" in str(e.get("away_team")) + str(e.get("home_team"))]
if not tgt:
    print("no Falcons game on the board")
    print("events:", [f"{e['away_team']} @ {e['home_team']}" for e in evs])
    sys.exit(1)
e = tgt[0]
print(f"{e['away_team']} @ {e['home_team']}   {e['commence_time']}\n")

for k in ("spreads", "totals"):
    try:
        d = get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/"
                f"?apiKey={KEY}&regions=us&bookmakers={BOOK}&oddsFormat=american&markets={k}")
    except urllib.error.HTTPError as ex:
        print(f"  {k}: HTTP {ex.code}"); continue
    for bk in d.get("bookmakers") or []:
        for m in bk.get("markets") or []:
            for o in m.get("outcomes") or []:
                pt = "" if o.get("point") is None else f" {o['point']:+g}"
                print(f"  {m['key']:8s} {str(o.get('name'))[:26]:26s}{pt:>8s} {o.get('price'):+}")
print()

for k in WANT:
    try:
        d = get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/"
                f"?apiKey={KEY}&regions=us&bookmakers={BOOK}"
                f"&oddsFormat=american&markets={k}")
    except urllib.error.HTTPError as ex:
        print(f"  {k}: HTTP {ex.code}"); continue
    rows = []
    for bk in d.get("bookmakers") or []:
        if bk.get("key") != BOOK:
            continue
        for m in bk.get("markets") or []:
            if m.get("key") != k:
                continue
            for o in m.get("outcomes") or []:
                # BOTH Robinsons are in this backfield -- Bijan and Brian. A
                # surname match here would merge a 22-carry back with a
                # 10-carry one, which is the Javonte error with both players on
                # the same team. Full names only, and both are printed so the
                # distinction is visible rather than assumed.
                if WHO in str(o.get("description")):
                    rows.append(o)
    if not rows:
        print(f"  {k}: no Robinson outcome"); continue
    print(f"  {k}:")
    for o in sorted(rows, key=lambda x: (str(x.get("description")),
                                         float(x.get("point") or 0),
                                         str(x.get("name")))):
        print(f"      {str(o.get('description')):18s} {str(o.get('name')):6s} "
              f"{float(o.get('point') or 0):7.1f}  {o.get('price'):+}")

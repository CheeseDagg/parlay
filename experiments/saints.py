#!/usr/bin/env python3
"""Every New Orleans skill-player line for tonight, whole ladders.

Atlanta's front seven is on the report too -- Deablo limited with a hamstring,
Abdullah ill, Ebukam hamstring, Za'Darius Smith rested -- so the linebacker
story runs BOTH ways and only Atlanta's half has been looked at.

The Saints' usage is concentrated and stable in a way Atlanta's is not:
Olave 13/10/13 targets for 375 yards, Juwan Johnson 7/4/8 at tight end,
Etienne 9/8/13 carries having taken the backfield off Kamara, and Shough
throwing 56, 34 and 42 times. The prop board surfaced exactly one of them,
which means the gates removed the rest rather than the market did -- most
likely the 70% price ceiling. So read the whole ladder and judge each rung.
"""
import json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
WHO = ("Olave", "Johnson", "Etienne", "Shough", "Fant", "Vele", "Kamara", "Miller")
WANT = ["player_reception_yds", "player_reception_yds_alternate",
        "player_receptions", "player_receptions_alternate",
        "player_rush_yds", "player_rush_yds_alternate",
        "player_rush_reception_yds", "player_pass_yds",
        "player_pass_yds_alternate", "player_pass_attempts",
        "player_anytime_td"]


def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())


def imp(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


evs = get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
tgt = [e for e in evs if "Saints" in str(e.get("away_team")) + str(e.get("home_team"))]
if not tgt:
    print("no Saints game on the board"); sys.exit(1)
e = tgt[0]
print(f"{e['away_team']} @ {e['home_team']}   {e['commence_time']}\n")
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
                # Surname matching is fine HERE and only here: this prints every
                # match rather than selecting one, so a collision is visible in
                # the output instead of silently becoming the wrong player. Two
                # Johnsons would both appear and be obvious.
                if any(w in str(o.get("description")) for w in WHO):
                    rows.append(o)
    if not rows:
        print(f"  {k}: nothing for these players"); continue
    print(f"  {k}:")
    for o in sorted(rows, key=lambda x: (str(x.get("description")),
                                         float(x.get("point") or 0),
                                         str(x.get("name")))):
        print(f"      {str(o.get('description')):20s} {str(o.get('name')):6s} "
              f"{float(o.get('point') or 0):7.1f}  {o.get('price'):+6d}  "
              f"{imp(o.get('price'))*100:5.1f}%")

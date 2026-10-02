#!/usr/bin/env python3
"""One-off: dump the rush+rec ladder for a named game. The slate pull returned
no rush+reception lines at all, which is either FanDuel not posting them for
this game or the market key being wrong -- and those need different answers."""
import json, os, sys, urllib.parse, urllib.request
BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
WANT = ["player_rush_reception_yds", "player_rush_reception_yds_alternate",
        "player_rush_reception_tds", "player_anytime_td"]
def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())
evs = get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
tgt = [e for e in evs if "Rams" in str(e.get("away_team")) + str(e.get("home_team"))]
if not tgt:
    print("no Rams game in the event list"); sys.exit(1)
e = tgt[0]
print(f"{e['away_team']} @ {e['home_team']}  {e['commence_time']}")
url = (f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/?apiKey={KEY}"
       f"&regions=us&bookmakers=fanduel&oddsFormat=american&markets={','.join(WANT)}")
try:
    d = get(url)
except Exception as ex:
    body = ""
    try: body = ex.read().decode()[:300]
    except Exception: pass
    print(f"HTTP {getattr(ex,'code','?')}: {body}"); sys.exit(1)
found = False
for bk in d.get("bookmakers") or []:
    for m in bk.get("markets") or []:
        rows = [o for o in (m.get("outcomes") or [])
                if "Williams" in str(o.get("description"))]
        if rows:
            found = True
            print(f"\n  market {m['key']}:")
            for o in sorted(rows, key=lambda x: (str(x.get('description')), x.get('point') or 0)):
                print(f"     {o.get('description')}  {o.get('name')} {o.get('point')}  {o.get('price'):+}")
if not found:
    print("\n  no Kyren Williams lines in any rush+rec market")
    print("  markets returned:", sorted({m['key'] for bk in (d.get('bookmakers') or [])
                                         for m in (bk.get('markets') or [])}))

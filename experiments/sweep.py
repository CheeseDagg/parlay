#!/usr/bin/env python3
"""Every market FanDuel posts on tonight's game, and every outcome in each.

I have been evaluating the markets I thought to ask for -- yards, receptions,
anytime TD -- and then reporting that the game is thin. That is a statement
about my list, not about the game. The event carries sixty-odd market keys and
I have looked at six of them.

Specifically untried and worth it:
  * RUSH ATTEMPTS. A volume prop, independent of efficiency and of how well the
    defence tackles. If Atlanta lean on the run because New Orleans have no
    linebackers, attempts move FIRST and most reliably -- yards need the
    blocking to work too.
  * TEAM TOTALS and the alternate spread ladder, which is where an injury to a
    front seven shows up at the game level.
  * FIRST HALF and quarter markets. Three linebackers being out is a full-game
    fact, but a team's plan is at its purest early.
  * Everything else, so that "there is nothing here" can be a finding rather
    than a description of what I bothered to request.
"""
import json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
SKIP = ("_q1", "_q2", "_q3", "_q4")   # quarter markets: too thin to price off


def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())


def imp(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


evs = get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
tgt = [e for e in evs if "Falcons" in str(e.get("away_team")) + str(e.get("home_team"))]
if not tgt:
    print("no Falcons game"); sys.exit(1)
e = tgt[0]
print(f"{e['away_team']} @ {e['home_team']}   {e['commence_time']}\n")

mk = get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/markets"
         f"?apiKey={KEY}&regions=us&bookmakers={BOOK}")
keys = []
for bk in (mk.get("bookmakers") or []) if isinstance(mk, dict) else []:
    if bk.get("key") == BOOK:
        keys = sorted({m.get("key") for m in (bk.get("markets") or [])})
print(f"{len(keys)} market keys posted\n")
todo = [k for k in keys if not any(s in k for s in SKIP)]
print(f"pricing {len(todo)} of them (skipping quarter markets)\n")

# batch them: the endpoint takes several keys at once, so this is a handful of
# requests rather than sixty.
B = 5
for i in range(0, len(todo), B):
    chunk = todo[i:i + B]
    try:
        d = get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/"
                f"?apiKey={KEY}&regions=us&bookmakers={BOOK}"
                f"&oddsFormat=american&markets={','.join(chunk)}")
    except urllib.error.HTTPError as ex:
        print(f"  [{','.join(chunk)}]: HTTP {ex.code}")
        continue
    for bk in d.get("bookmakers") or []:
        if bk.get("key") != BOOK:
            continue
        for m in sorted(bk.get("markets") or [], key=lambda x: x.get("key") or ""):
            outs = m.get("outcomes") or []
            if not outs:
                continue
            print(f"  {m['key']}  ({len(outs)})")
            for o in sorted(outs, key=lambda x: (str(x.get("description") or ""),
                                                 float(x.get("point") or 0),
                                                 str(x.get("name")))):
                desc = str(o.get("description") or "")
                pt = "" if o.get("point") is None else f"{float(o['point']):7.1f}"
                pr = o.get("price")
                if pr is None:
                    continue
                print(f"      {desc[:20]:20s} {str(o.get('name'))[:22]:22s} "
                      f"{pt:>7s} {pr:+6d} {imp(pr)*100:5.1f}%")

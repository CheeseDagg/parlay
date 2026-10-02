#!/usr/bin/env python3
"""Is Purdy better on pass+rush than on rush alone? Read the board, don't guess.

Three things have to come back before that question can be answered, and I have
guessed at all three before:

  1. WHICH MARKETS EXIST for this game. "player_pass_rush_yds" is a plausible
     key, not a known one. The markets endpoint is asked rather than a key
     being assumed and a 404 being read as "FanDuel doesn't post it".
  2. EVERY Purdy outcome on each of them, whole ladder, both sides.
  3. THE SPREAD AND TOTAL, because a quarterback's yardage prop is a bet on
     how much his team has to throw, and that is the game script.
"""
import json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"


def get(u):
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.loads(r.read().decode())


def try_get(u, label):
    try:
        return get(u)
    except urllib.error.HTTPError as ex:
        body = ""
        try:
            body = ex.read().decode()[:200]
        except Exception:
            pass
        print(f"  {label}: HTTP {ex.code} {body}")
        return None


evs = get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
tgt = [e for e in evs if "49ers" in str(e.get("away_team")) + str(e.get("home_team"))]
if not tgt:
    print("no 49ers game in the event list")
    print("events:", [f"{e['away_team']} @ {e['home_team']}" for e in evs])
    sys.exit(1)
e = tgt[0]
print(f"{e['away_team']} @ {e['home_team']}   {e['commence_time']}\n")

# ---- 1. what markets does this event actually have
print("AVAILABLE MARKETS")
mk = try_get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/markets"
             f"?apiKey={KEY}&regions=us&bookmakers={BOOK}", "markets endpoint")
keys = []
if mk:
    for bk in (mk.get("bookmakers") or []) if isinstance(mk, dict) else []:
        if bk.get("key") == BOOK:
            keys = sorted({m.get("key") for m in (bk.get("markets") or [])})
    print(f"  {len(keys)} keys")
    for k in keys:
        if "pass" in k or "rush" in k:
            print(f"    {k}")
if not keys:
    # Fall back to asking for candidate keys directly. A key the API does not
    # recognise comes back as a 422 naming it, which is itself the answer.
    keys = ["player_pass_yds", "player_pass_yds_alternate",
            "player_rush_yds", "player_rush_yds_alternate",
            "player_pass_rush_yds", "player_pass_rush_yds_alternate",
            "player_pass_rush_reception_yds",
            "player_pass_rush_reception_yds_alternate",
            "player_pass_attempts", "player_pass_completions",
            "player_pass_tds", "player_anytime_td"]
    print(f"  markets endpoint unavailable; probing {len(keys)} candidate keys")

# ---- 2. the spread and total first, because it frames everything below
print("\nGAME SCRIPT")
h2h = try_get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/"
              f"?apiKey={KEY}&regions=us&bookmakers={BOOK}&oddsFormat=american"
              f"&markets=h2h,spreads,totals", "h2h/spreads/totals")
for bk in (h2h or {}).get("bookmakers") or []:
    for m in bk.get("markets") or []:
        for o in m.get("outcomes") or []:
            pt = "" if o.get("point") is None else f" {o['point']:+g}"
            print(f"  {m['key']:9s} {str(o.get('name')):28s}{pt:>8s} "
                  f"{o.get('price'):+}")

# ---- 3. every Purdy outcome, one market at a time so a bad key is isolated
print("\nPURDY OUTCOMES")
found_any = False
for k in keys:
    d = try_get(f"{BASE}/sports/americanfootball_nfl/events/{e['id']}/odds/"
                f"?apiKey={KEY}&regions=us&bookmakers={BOOK}"
                f"&oddsFormat=american&markets={k}", k)
    if not d:
        continue
    rows = []
    for bk in d.get("bookmakers") or []:
        if bk.get("key") != BOOK:
            continue
        for m in bk.get("markets") or []:
            if m.get("key") != k:
                continue
            for o in m.get("outcomes") or []:
                if "Purdy" in str(o.get("description")) or "Purdy" in str(o.get("name")):
                    rows.append(o)
    if not rows:
        print(f"  {k}: no Purdy outcome")
        continue
    found_any = True
    print(f"  {k}:")
    for o in sorted(rows, key=lambda x: (float(x.get("point") or 0), str(x.get("name")))):
        print(f"      {str(o.get('name')):6s} {float(o.get('point') or 0):7.1f}  "
              f"{o.get('price'):+}")
if not found_any:
    print("  nothing posted for Purdy in any market tried")

#!/usr/bin/env python3
"""socdiag.py — answer ONE question: which soccer competitions does this API
actually carry right now, and which of them are playing today?

Written 2026-08-13, when the board showed five Leagues Cup matches and FanDuel
was showing two dozen Europa/Conference League qualifiers on the same evening.
Three keys were added to catch them, came back with nothing, and the log could
not say whether the API lacks the fixtures or the keys were wrong.

Guessing cost an hour. This asks.

Prints, for every soccer key in /v4/sports?all=true:
  * whether the API calls it active
  * how many events it returns with NO bookmaker filter
  * how many of those start today, and the first few by name
  * which bookmakers priced the earliest one

No bookmaker filter is the point: 'FanDuel has no price' and 'the API has no
fixture' are different problems and the board's normal pull cannot tell them
apart, because it asks for FanDuel only and gets an empty list either way.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r), r.headers.get("x-requests-remaining")


def main():
    if not KEY:
        print("no ODDS_API_KEY in env"); return 1
    now = datetime.now(timezone.utc)
    day0 = now.strftime("%Y-%m-%d")
    day1 = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    sports, _ = get(f"{BASE}/sports?apiKey={KEY}&all=true")
    soc = [s for s in sports if s.get("key", "").startswith("soccer")]
    print(f"{len(soc)} soccer keys in the catalog\n")
    hits = []
    for s in sorted(soc, key=lambda x: x["key"]):
        k, title, active = s["key"], s.get("title", ""), bool(s.get("active"))
        q = urllib.parse.urlencode({"apiKey": KEY, "regions": "us",
                                    "markets": "h2h", "oddsFormat": "american",
                                    "dateFormat": "iso"})
        try:
            ev, rem = get(f"{BASE}/sports/{k}/odds?{q}")
        except urllib.error.HTTPError as e:
            print(f"  {k:<52} HTTP {e.code}")
            continue
        except Exception as e:
            print(f"  {k:<52} {type(e).__name__}")
            continue
        today = [e for e in ev if e.get("commence_time", "").startswith((day0, day1))]
        if not ev:
            continue
        flag = "ACTIVE" if active else "off-season"
        print(f"  {k:<52} {flag:<11} {len(ev):>3} events, {len(today):>3} today/tomorrow")
        if today:
            hits.append((k, title, today))
    print("\n" + "=" * 72)
    for k, title, today in hits:
        print(f"\n{k}  ({title})  — {len(today)} fixtures today/tomorrow")
        for e in sorted(today, key=lambda x: x["commence_time"])[:30]:
            bks = [b.get("key") for b in e.get("bookmakers", [])]
            fd = "FANDUEL" if "fanduel" in bks else f"no fd ({len(bks)} books)"
            print(f"    {e['commence_time']}  {e.get('away_team')} @ "
                  f"{e.get('home_team')}   {fd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

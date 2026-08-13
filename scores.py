#!/usr/bin/env python3
"""scores.py — what actually happened, fetched where the network allows it.

    python3 scores.py            # write scores.json + print a summary
    python3 scores.py --selftest

Every stats host is blocked from the dev container -- statsapi.mlb.com,
api.the-odds-api.com, espn, fox, all of it. So on 2026-08-12, with a placed
18-leg slip live and six F5 unders already settled, the honest answer to "is
it dead?" was "I cannot see." The board could tell Ryan what to bet and had
no way to tell him whether it won.

The Actions runner has open egress -- it calls the odds API on every refresh.
So the fetch belongs there, and its output belongs in the repo where anything
can read it.

MLB comes from statsapi.mlb.com, which is free, unauthenticated, and reports
a LINESCORE BY INNING. That matters: an F5 leg needs runs through five, not
the final, and every other source gives only a running total. Soccer comes
from the odds API's /scores, which is a running total -- fine, because a goal
total only ever moves one way (see f5_state).
"""
import json, os, sys, urllib.request, urllib.error

MLB_API = "https://statsapi.mlb.com/api/v1/schedule"
ODDS_BASE = "https://api.the-odds-api.com/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "scores.json")


def _get(url, timeout=25):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def f5_state(line, through5, current, inning):
    """Verdict on an F5 under, given what is known.

    'WON'     runs through five are in and at or under the line
    'LOST'    runs through five are in and over it
    'SAFE'    innings unavailable, but the CURRENT total is already at or
              under the line -- runs never come off the board, so the first
              five cannot have exceeded it
    'UNKNOWN' current total is over the line and the split is unavailable;
              the runs may all have come after the fifth
    """
    if through5 is not None:
        return 'WON' if through5 <= line else 'LOST'
    if current is not None and current <= line:
        return 'SAFE'
    return 'UNKNOWN'


def mlb_games(date):
    """[{away, home, key, through5, current, inning, final}] for a date."""
    url = (f"{MLB_API}?sportId=1&date={date}"
           "&hydrate=linescore,team")
    out = []
    for d in _get(url).get("dates", []):
        for g in d.get("games", []):
            ls = g.get("linescore") or {}
            innings = ls.get("innings") or []
            away = ((g.get("teams") or {}).get("away") or {}).get("team", {}).get("abbreviation")
            home = ((g.get("teams") or {}).get("home") or {}).get("team", {}).get("abbreviation")
            # Runs through five: sum both halves of innings 1-5, but ONLY when
            # five have actually been played. A game in the 4th must not report
            # a partial sum as if it were the F5 result.
            t5 = None
            if len([i for i in innings if i.get("num", 0) <= 5]) >= 5:
                t5 = 0
                for i in innings:
                    if i.get("num", 0) <= 5:
                        t5 += (i.get("away", {}).get("runs") or 0)
                        t5 += (i.get("home", {}).get("runs") or 0)
            cur = None
            if ls.get("teams"):
                a = (ls["teams"].get("away") or {}).get("runs")
                h = (ls["teams"].get("home") or {}).get("runs")
                if a is not None and h is not None:
                    cur = a + h
            out.append({"away": away, "home": home, "key": f"{away}@{home}",
                        "through5": t5, "current": cur,
                        "inning": ls.get("currentInning"),
                        "final": (g.get("status") or {}).get("abstractGameState") == "Final"})
    return out


def soccer_scores(key, sport="soccer_concacaf_leagues_cup"):
    """Running totals from the odds API. Goals only accumulate, so a total at
    or under a line mid-match means the under is still live, never the reverse."""
    url = f"{ODDS_BASE}/sports/{sport}/scores/?daysFrom=1&apiKey={key}"
    out = []
    for ev in _get(url):
        sc = {s["name"]: int(s["score"]) for s in (ev.get("scores") or [])
              if s.get("score") is not None}
        out.append({"home": ev.get("home_team"), "away": ev.get("away_team"),
                    "goals": sum(sc.values()) if sc else None,
                    "completed": bool(ev.get("completed")),
                    "detail": sc})
    return out


def main():
    import datetime as dt
    # MLB's schedule date is the ET calendar date, not UTC -- a 9pm CT first
    # pitch is tomorrow in UTC and would return an empty slate.
    et = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)
    date = et.strftime("%Y-%m-%d")
    doc = {"as_of": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "date": date, "mlb": [], "soccer": []}
    try:
        doc["mlb"] = mlb_games(date)
        print(f"MLB: {len(doc['mlb'])} games on {date}")
    except Exception as e:
        print(f"MLB scores unavailable ({type(e).__name__}: {e})")
    key = os.environ.get("ODDS_API_KEY", "")
    if key:
        for sp in ("soccer_concacaf_leagues_cup", "soccer_usa_mls"):
            try:
                got = soccer_scores(key, sp)
                doc["soccer"].extend(got)
                print(f"{sp}: {len(got)} matches")
            except Exception as e:
                print(f"{sp} scores unavailable ({type(e).__name__})")
    json.dump(doc, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")
    for g in doc["mlb"]:
        if g["current"] is None:
            continue
        t5 = g["through5"]
        print(f"  {g['key']:10} through5={t5 if t5 is not None else '-':>3}  "
              f"current={g['current']:>3}  inning={g['inning']}  "
              f"{'FINAL' if g['final'] else ''}")
    for s in doc["soccer"]:
        if s["goals"] is not None:
            print(f"  {str(s['away'])[:16]:16} @ {str(s['home'])[:16]:16} "
                  f"goals={s['goals']}  {'FT' if s['completed'] else 'live'}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(f5_state(10.5, 4, 9, 7) == 'WON', "4 through five clears U10.5")
    chk(f5_state(10.5, 11, 14, 8) == 'LOST', "11 through five loses U10.5")
    chk(f5_state(9.5, 10, 10, 6) == 'LOST', "BOS@TOR's line is 9.5, so 10 kills it")
    # THE CASE THAT MATTERS WHEN INNINGS ARE MISSING: runs never come off the
    # board, so a current total at or under the line proves the first five were.
    chk(f5_state(10.5, None, 7, 8) == 'SAFE',
        "no innings, but 7 total in the 8th means five innings cannot have had 11")
    chk(f5_state(10.5, None, 12, 8) == 'UNKNOWN',
        "12 total says nothing -- all twelve may have come after the fifth")
    chk(f5_state(10.5, None, None, None) == 'UNKNOWN', "no data is not good news")
    chk(f5_state(10.5, 10, 10, 5) == 'WON', "exactly the line is UNDER on a .5 line")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

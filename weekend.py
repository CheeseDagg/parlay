#!/usr/bin/env python3
"""weekend.py — what is actually on the board across sports, and what it costs.

    ODDS_API_KEY=... python3 weekend.py      # runner does this
    python3 weekend.py --selftest

Ryan wants a multi-sport ticket. Before anything can be said about legs, the
board has to be read rather than remembered: fights.py still carries the
Makhachev card from an event that has already happened, and a parlay built off
a stale card is not a parlay, it is a guess with names on it.

ONE THING WORTH KNOWING BEFORE PICKING LEGS. A same-game parlay and a
cross-sport parlay are not the same bet wearing different clothes:

  * In an SGP the legs are CORRELATED. The book prices that in with a haircut,
    but correlation also means the legs cash together -- which is the only
    reason the open 7-leg PIT/CLE ticket is live at all while five of its legs
    share one game script.
  * Across sports there is NO correlation to find. A UFC bout and an NFL game
    cannot share a script, so the fair price IS the product, and the vig on
    every leg compounds with nothing to offset it. Four -110 legs is roughly
    4.5% of vig stacked.

So a cross-sport ticket has exactly one source of edge: individual legs the
market has priced wrong. Not the structure. That is worth saying out loud
because "multi-sport" can feel like diversification, and it is the opposite --
every leg still has to win.

WHAT THIS PRINTS: every MMA bout and NFL game inside the horizon, with
FanDuel's two-way price de-vigged to a probability, so a leg can be compared
against a number instead of against a feeling.
"""
import datetime as dt, json, os, sys, urllib.error, urllib.request

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
SPORTS = [("mma_mixed_martial_arts", "UFC"), ("americanfootball_nfl", "NFL")]
BOOK = "fanduel"
HORIZON_H = 120          # five days: Thursday through Monday night


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode()), dict(r.headers)


def devig_two(a, b):
    """Two-way multiplicative de-vig. Returns (p_a, p_b) or None if unusable."""
    def imp(am):
        am = float(am)
        return 100.0 / (am + 100.0) if am > 0 else -am / (-am + 100.0)
    try:
        ia, ib = imp(a), imp(b)
    except (TypeError, ValueError):
        return None
    s = ia + ib
    if not (1.0 < s < 1.35):      # a two-way book total outside this is not a
        return None               # clean pair -- suspended, stale, or one-sided
    return ia / s, ib / s


def board(sport, fetch=None):
    """[(commence, home, away, [(name, american, p_devig)])] inside the horizon."""
    fetch = fetch or (lambda u: _get(u)[0])
    url = (f"{BASE}/sports/{sport}/odds/?apiKey={KEY}&regions=us&markets=h2h"
           f"&oddsFormat=american&bookmakers={BOOK}")
    rows = []
    now = dt.datetime.now(dt.timezone.utc)
    for ev in fetch(url) or []:
        try:
            t = dt.datetime.fromisoformat(str(ev.get("commence_time")).replace("Z", "+00:00"))
        except Exception:
            continue
        if not (now <= t <= now + dt.timedelta(hours=HORIZON_H)):
            continue
        outs = []
        for bk in ev.get("bookmakers") or []:
            for mk in bk.get("markets") or []:
                if mk.get("key") != "h2h":
                    continue
                o = mk.get("outcomes") or []
                if len(o) == 2:
                    d = devig_two(o[0].get("price"), o[1].get("price"))
                    for i, x in enumerate(o):
                        outs.append((x.get("name"), x.get("price"),
                                     d[i] if d else None))
        if outs:
            rows.append((t, ev.get("home_team"), ev.get("away_team"), outs))
    rows.sort()
    return rows


def main():
    if not KEY:
        print("no ODDS_API_KEY -- this runs on the Actions runner")
        return 1
    for sport, label in SPORTS:
        try:
            rows = board(sport)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            print(f"\n{label}: HTTP {e.code} {body}")
            continue
        except Exception as e:
            print(f"\n{label}: {type(e).__name__}")
            continue
        print(f"\n{label} — {len(rows)} events in the next {HORIZON_H}h")
        for t, home, away, outs in rows:
            print(f"  {t.strftime('%a %m-%d %H:%MZ')}  {away} @ {home}")
            for name, price, p in outs:
                pc = f"{p*100:5.1f}%" if p is not None else "  —  "
                print(f"      {str(name)[:32]:32} {str(price):>6}   {pc}")
    return 0


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    d = devig_two(-110, -110)
    chk(d and abs(d[0] - 0.5) < 1e-9, "a pick-em de-vigs to 50/50")
    d = devig_two(-300, +240)
    chk(d and abs(sum(d) - 1.0) < 1e-9, "the two sides sum to exactly 1")
    chk(d and d[0] > d[1], "and the favourite carries the larger share")
    chk(devig_two(-110, +500) is None,
        "a pair whose book total is under 1.00 is refused, not 'de-vigged' "
        "into a number above the true price")
    chk(devig_two(-10000, -10000) is None,
        "and so is a pair holding 50% vig -- that is a suspended market")
    chk(devig_two(None, -110) is None and devig_two("x", 1) is None,
        "a missing or non-numeric price yields None rather than raising")

    now = dt.datetime.now(dt.timezone.utc)
    soon = (now + dt.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    late = (now + dt.timedelta(hours=HORIZON_H + 48)).isoformat().replace("+00:00", "Z")
    past = (now - dt.timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    FEED = [
        {"commence_time": soon, "home_team": "H", "away_team": "A",
         "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
             {"name": "A", "price": -200}, {"name": "H", "price": +165}]}]}]},
        {"commence_time": late, "home_team": "TooFar", "away_team": "X",
         "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
             {"name": "X", "price": -110}, {"name": "TooFar", "price": -110}]}]}]},
        {"commence_time": past, "home_team": "Started", "away_team": "Y",
         "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
             {"name": "Y", "price": -110}, {"name": "Started", "price": -110}]}]}]},
    ]
    rows = board("x", fetch=lambda u: FEED)
    chk(len(rows) == 1 and rows[0][1] == "H",
        "events beyond the horizon and events already started are both dropped")
    chk(rows[0][3][0][2] is not None and abs(sum(o[2] for o in rows[0][3]) - 1) < 1e-9,
        "the surviving event carries de-vigged probabilities that sum to 1")
    chk(board("x", fetch=lambda u: []) == [], "an empty feed yields nothing, not a crash")
    chk(board("x", fetch=lambda u: [{"commence_time": "garbage"}]) == [],
        "an unparseable timestamp is skipped rather than crashing the pull")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())

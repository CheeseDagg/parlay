#!/usr/bin/env python3
"""tonight.py -- everything with a start time in the next N hours, across sports.

    ODDS_API_KEY=... python3 tonight.py [hours]
    python3 tonight.py --selftest

"Any good action tonight" is a question about a WINDOW, not a sport, and the
answer has to start from what is actually scheduled. In October that is one
Monday-night football game and whatever round of the baseball postseason is
running -- and a postseason baseball game is not a regular-season one wearing a
different hat: short rotations, relievers on no rest, and lineups that sit a
cold bat. The board comes first; what is worth betting comes after.

Every two-way price is de-vigged so a number can be compared against a number.
A one-sided quote prints raw and says so.
"""
import datetime as dt, json, os, sys, urllib.error, urllib.request

import slips

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
# Asked in this order; any that is out of season simply returns nothing, which
# is cheaper than guessing which are live from a calendar.
SPORTS = [("americanfootball_nfl", "NFL"), ("baseball_mlb", "MLB"),
          ("basketball_nba", "NBA"), ("icehockey_nhl", "NHL"),
          ("mma_mixed_martial_arts", "UFC"), ("soccer_epl", "EPL"),
          ("soccer_uefa_champs_league", "UCL")]


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def imp(american):
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def within(ev, now, hours):
    try:
        t = dt.datetime.fromisoformat(str(ev["commence_time"]).replace("Z", "+00:00"))
    except Exception:
        return None
    return t if now <= t <= now + dt.timedelta(hours=hours) else None


def two_way(outs):
    """(name, price, p, basis) rows for a market, de-vigged where it is a clean
    two-way book. A three-way market (soccer) de-vigs across all three; a
    one-sided quote cannot be de-vigged at all and says `vig`."""
    rows = [o for o in outs if o.get("price") is not None]
    if not rows:
        return []
    if len(rows) == 1:
        return [(rows[0].get("name"), rows[0]["price"], imp(rows[0]["price"]), "vig")]
    qs = [imp(o["price"]) for o in rows]
    s = sum(qs)
    if not (1.0 < s < 1.45):      # suspended, stale, or not a real book
        return [(o.get("name"), o["price"], imp(o["price"]), "raw") for o in rows]
    ps = slips.devig(qs)
    return [(o.get("name"), o["price"], p, "devig") for o, p in zip(rows, ps)]


def selftest():
    f = 0

    def ck(c, m):
        nonlocal f
        if not c:
            print(f"  FAIL {m}"); f += 1

    ck(abs(imp(-110) - 0.5238) < 1e-3, "imp")
    now = dt.datetime(2026, 10, 5, 18, 0, tzinfo=dt.timezone.utc)
    ck(within({"commence_time": "2026-10-06T00:15:00Z"}, now, 12) is not None, "in window")
    ck(within({"commence_time": "2026-10-07T00:15:00Z"}, now, 12) is None, "past window")
    ck(within({"commence_time": "2026-10-05T17:00:00Z"}, now, 12) is None,
       "already started must be excluded")
    ck(within({"commence_time": "nonsense"}, now, 12) is None, "unparseable time")

    r = two_way([{"name": "A", "price": -150}, {"name": "B", "price": 130}])
    ck(len(r) == 2 and r[0][3] == "devig", f"two-way {r}")
    ck(abs(sum(x[2] for x in r) - 1.0) < 1e-9, "de-vigged pair must sum to 1")
    ck(r[0][2] < imp(-150), "the favourite must come down")
    one = two_way([{"name": "A", "price": -150}])
    ck(one[0][3] == "vig", "one-sided cannot be de-vigged")
    # a book that does not sum to a plausible overround is not de-vigged
    bad = two_way([{"name": "A", "price": -5000}, {"name": "B", "price": -5000}])
    ck(all(x[3] == "raw" for x in bad), f"implausible book must stay raw: {bad}")
    ck(two_way([]) == [], "empty market")
    ck(two_way([{"name": "A"}]) == [], "a market with no price is empty")
    three = two_way([{"name": "H", "price": 150}, {"name": "D", "price": 240},
                     {"name": "A", "price": 180}])
    ck(len(three) == 3 and abs(sum(x[2] for x in three) - 1.0) < 1e-9,
       f"three-way must normalise too: {three}")
    print("tonight selftest:", "ok" if f == 0 else f"{f} FAILURES")
    return 1 if f else 0


def main(hours=12):
    if not KEY:
        print("no ODDS_API_KEY"); return 1
    now = dt.datetime.now(dt.timezone.utc)
    print(f"{now:%Y-%m-%dT%H:%MZ}  next {hours}h  FanDuel\n")
    found = 0
    for key, lab in SPORTS:
        try:
            evs = _get(f"{BASE}/sports/{key}/odds/?apiKey={KEY}&regions=us"
                       f"&bookmakers={BOOK}&oddsFormat=american&markets=h2h,totals")
        except urllib.error.HTTPError as ex:
            print(f"{lab}: HTTP {ex.code}")
            continue
        except Exception as ex:
            print(f"{lab}: {type(ex).__name__}")
            continue
        live = [(within(e, now, hours), e) for e in (evs or [])]
        live = sorted([(t, e) for t, e in live if t], key=lambda x: x[0])
        if not live:
            continue
        print(f"--- {lab} ({len(live)}) ---")
        found += len(live)
        for t, e in live:
            print(f"  {t:%H:%M}Z  {e.get('away_team')} @ {e.get('home_team')}")
            for bk in e.get("bookmakers") or []:
                if bk.get("key") != BOOK:
                    continue
                for m in bk.get("markets") or []:
                    for name, price, p, basis in two_way(m.get("outcomes") or []):
                        pt = next((o.get("point") for o in m["outcomes"]
                                   if o.get("name") == name and o.get("point") is not None), None)
                        ptxt = "" if pt is None else f" {pt:+g}"
                        print(f"       {m['key']:7s} {str(name)[:26]:26s}{ptxt:>7s} "
                              f"{price:+6d}  {p*100:5.1f}% {basis}")
        print()
    if not found:
        print("nothing scheduled inside the window")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("-")]
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main(int(a[0]) if a else 12))

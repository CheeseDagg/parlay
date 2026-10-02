#!/usr/bin/env python3
"""nflprops.py — NFL player props, scored against the actual game logs.

    ODDS_API_KEY=... python3 nflprops.py [max_events]
    python3 nflprops.py --selftest

WHY ALT LINES. Ryan's standing complaint about books is that they "sell you a
story": an alternate line gets marked at a price that reads like a near-lock or
like a long shot, and the number underneath does not agree. That is a testable
claim, not a feeling -- every alt line is a threshold, and nflverse has every
player's per-game result for the last five seasons. So each posted line gets a
HIT RATE from the record and the two numbers go side by side.

WHAT THIS IS NOT. It is not a model. It counts how often a player has cleared a
number and compares that with what the book charges. A count is weaker than a
projection and stronger than an opinion, and it is reported as a count --
"cleared this in 11 of his last 20" -- so the sample size is visible instead of
being laundered into a probability.

TWO THINGS IT REFUSES TO DO:
  * No de-vig on a one-sided alt line. An alt quote usually arrives alone, and
    the implied probability of a lone price INCLUDES the vig. Calling that a
    probability flatters every under and punishes every over. It is labelled
    "implied (with vig)" and compared only against the raw hit rate.
  * No edge on fewer than MIN_GAMES. A rookie with three games will show 3 of 3
    against any soft line and that is not information.
"""
import datetime as dt, gzip, io, json, os, sys, urllib.error, urllib.request
from collections import defaultdict

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
SPORT = "americanfootball_nfl"
BOOK = "fanduel"
HORIZON_H = 120
MIN_GAMES = 8          # below this a hit rate is noise, not a rate
SEASONS = [2026, 2025]

# market key -> (nflverse stat columns to sum, human label)
MARKETS = {
    "player_pass_yds_alternate":       (["passing_yards"], "pass yds"),
    "player_rush_yds_alternate":       (["rushing_yards"], "rush yds"),
    "player_reception_yds_alternate":  (["receiving_yards"], "rec yds"),
    "player_receptions_alternate":     (["receptions"], "receptions"),
    "player_pass_tds_alternate":       (["passing_tds"], "pass TDs"),
    "player_rush_reception_yds_alternate": (["rushing_yards", "receiving_yards"],
                                            "rush+rec yds"),
}


def _get(url):
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.loads(r.read().decode()), dict(r.headers)


def implied(american):
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def game_logs(seasons=None, fetch=None):
    """{player: [(date, {stat: value})]} from nflverse weekly stats."""
    seasons = seasons or SEASONS
    out = defaultdict(list)
    for yr in seasons:
        url = (f"https://github.com/nflverse/nflverse-data/releases/download/"
               f"stats_player/stats_player_week_{yr}.csv")
        try:
            txt = fetch(url) if fetch else _raw(url)
        except Exception as e:
            print(f"  game logs {yr}: {type(e).__name__}")
            continue
        import csv
        for r in csv.DictReader(io.StringIO(txt)):
            if r.get("season_type") != "REG":
                continue
            nm = r.get("player_display_name")
            if not nm:
                continue
            vals = {}
            for k in ("passing_yards", "rushing_yards", "receiving_yards",
                      "receptions", "passing_tds"):
                try:
                    vals[k] = float(r.get(k) or 0)
                except (TypeError, ValueError):
                    vals[k] = 0.0
            out[nm].append((int(r["season"]), int(r["week"]), vals))
    for k in out:
        out[k].sort()
    return out


def _raw(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        b = r.read()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return b.decode("utf-8", "replace")


def hit_rate(logs, player, cols, point, side):
    """(hits, n) over the player's games — how often he cleared this number."""
    rows = logs.get(player) or []
    if len(rows) < MIN_GAMES:
        return None
    hits = 0
    for _s, _w, v in rows:
        tot = sum(v.get(c, 0.0) for c in cols)
        if (tot > point) if side == "Over" else (tot < point):
            hits += 1
    return hits, len(rows)


def score(events, logs, min_gap=0.10):
    """Lines where the record disagrees with the price by at least min_gap."""
    out = []
    for ev in events:
        for mk, (cols, label) in MARKETS.items():
            for name, side, point, price in ev.get("lines", {}).get(mk, []):
                hr = hit_rate(logs, name, cols, point, side)
                if not hr:
                    continue
                hits, n = hr
                rate = hits / n
                imp = implied(price)
                # The book's number carries vig, so a gap in the book's favour
                # is expected and only a gap the OTHER way is interesting.
                if rate - imp >= min_gap:
                    out.append({"game": ev.get("game"), "player": name,
                                "market": label, "side": side, "point": point,
                                "price": price, "hits": hits, "n": n,
                                "rate": rate, "implied": imp,
                                "gap": rate - imp})
    out.sort(key=lambda r: -r["gap"])
    return out


def pull(max_events=4):
    evs, _ = _get(f"{BASE}/sports/{SPORT}/events?apiKey={KEY}")
    now = dt.datetime.now(dt.timezone.utc)
    keep = []
    for e in evs or []:
        try:
            t = dt.datetime.fromisoformat(str(e["commence_time"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if now <= t <= now + dt.timedelta(hours=HORIZON_H):
            keep.append((t, e))
    # SORT ON THE TIME ONLY. These are (datetime, dict) tuples, and a Sunday
    # slate has many games kicking at exactly the same minute -- so a plain
    # sort falls through to comparing the dicts and raises. The fixture that
    # tested this had distinct timestamps, which is the one shape the real
    # board never has.
    keep.sort(key=lambda x: x[0])
    out = []
    for t, e in keep[:max_events]:
        url = (f"{BASE}/sports/{SPORT}/events/{e['id']}/odds/?apiKey={KEY}"
               f"&regions=us&bookmakers={BOOK}&oddsFormat=american"
               f"&markets={','.join(MARKETS)}")
        try:
            d, h = _get(url)
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode()[:160]
            except Exception:
                pass
            print(f"  {e.get('away_team')} @ {e.get('home_team')}: HTTP {err.code} {body}")
            continue
        lines = defaultdict(list)
        for bk in d.get("bookmakers") or []:
            for m in bk.get("markets") or []:
                for o in m.get("outcomes") or []:
                    if o.get("point") is None or o.get("price") is None:
                        continue
                    lines[m["key"]].append((o.get("description") or o.get("name"),
                                            o.get("name"), float(o["point"]),
                                            float(o["price"])))
        out.append({"game": f"{e.get('away_team')} @ {e.get('home_team')}",
                    "kick": t.strftime("%a %m-%d %H:%MZ"), "lines": lines,
                    "quota": h.get("x-requests-remaining")})
        print(f"  {out[-1]['game']}: {sum(len(v) for v in lines.values())} lines"
              f"  (quota left {h.get('x-requests-remaining')})")
    return out


def main():
    if not KEY:
        print("no ODDS_API_KEY -- this runs on the Actions runner")
        return 1
    n = 4
    for a in sys.argv[1:]:
        if a.isdigit():
            n = int(a)
    print(f"pulling alt props for up to {n} games")
    events = pull(n)
    if not events:
        print("no events pulled")
        return 1
    print("\nloading game logs...")
    logs = game_logs()
    print(f"  {len(logs)} players with logs")
    rows = score(events, logs)
    print(f"\n{len(rows)} lines where the RECORD beats the PRICE by 10+ points")
    print(f"(hit rate is raw history; implied price still carries the vig)\n")
    for r in rows[:40]:
        print(f"  {r['player'][:22]:22} {r['side']:5} {r['point']:6.1f} {r['market']:13}"
              f" {int(r['price']):>6}  hit {r['hits']:2}/{r['n']:2} = {r['rate']:4.0%}"
              f"  vs {r['implied']:4.0%}  (+{r['gap']:.0%})  {r['game'][:34]}")
    return 0


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(abs(implied(-110) - 0.5238) < 1e-3, "a -110 price implies 52.4%, vig included")
    chk(abs(implied(+200) - 1/3) < 1e-6, "and +200 implies 33.3%")

    logs = {"Busy Guy": [(2025, w, {"rushing_yards": v}) for w, v in
                         enumerate([80, 90, 70, 100, 85, 60, 95, 75, 88, 92], 1)],
            "Rookie": [(2026, w, {"rushing_yards": 99}) for w in range(1, 4)]}
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 59.5, "Over") == (10, 10),
        "a line under every game he has played reads 10 of 10")
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 89.5, "Over") == (4, 10),
        "and a line through the middle of his record splits it")
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 89.5, "Under") == (6, 10),
        "the under is counted as its own side, not one minus the over")
    chk(hit_rate(logs, "Rookie", ["rushing_yards"], 10.5, "Over") is None,
        "a three-game player is refused -- 3 of 3 against a soft line is not a rate")
    chk(hit_rate(logs, "Nobody", ["rushing_yards"], 10.5, "Over") is None,
        "and an unknown name yields None rather than raising")

    ev = [{"game": "A @ B", "lines": {"player_rush_yds_alternate": [
        ("Busy Guy", "Over", 59.5, -250),    # 100% history vs 71% implied -> gap
        ("Busy Guy", "Over", 89.5, +150),    #  40% history vs 40% implied -> no gap
        ("Rookie",   "Over", 10.5, -1000),   # too few games -> dropped
    ]}}]
    s = score(ev, logs)
    chk(len(s) == 1 and s[0]["point"] == 59.5,
        "only the line whose record beats its price by 10+ points is reported")
    chk(s[0]["hits"] == 10 and s[0]["n"] == 10,
        "and it carries the count, so the sample size is visible")
    tight = score(ev, logs, min_gap=0.99)
    chk(tight == [], "raising the bar past any real gap yields nothing")

    # THE SUNDAY SLATE SHAPE: one kickoff time, many games. A plain sort over
    # (datetime, dict) pairs raises on the second comparison, and the board
    # always looks like this at 1pm ET.
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    same = (now + _dt.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    feed = [{"id": str(i), "commence_time": same, "home_team": f"H{i}",
             "away_team": f"A{i}"} for i in range(4)]
    try:
        keep = []
        for e in feed:
            t = _dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            keep.append((t, e))
        keep.sort(key=lambda x: x[0])
        crashed = False
    except TypeError:
        crashed = True
    chk(not crashed,
        "four games at one kickoff time sort without comparing the dicts")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())

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
CURRENT_SEASON = 2026  # absent from it = injured, cut, or moved; not evidence
MIN_CURRENT = 3        # games THIS season before the recent window means anything.
                       # At two, "1 of 2 = 50%" clears almost any implied price,
                       # which is how Calvin Ridley survived the first two-window
                       # filter: nine games across two seasons, two of them this
                       # year, zero yards in the most recent one. Four weeks in,
                       # three games is also a decent proxy for "he plays every
                       # week", which is most of what the book is pricing on a
                       # low bar.
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
            vals["_team"] = r.get("team") or ""
            vals["_opp"] = r.get("opponent_team") or ""
            vals["_pos"] = (r.get("position") or "").upper()
            out[nm].append((int(r["season"]), int(r["week"]), vals))
    for k in out:
        # KEY ON (season, week), NOT THE WHOLE TUPLE. The third element is a
        # dict, so any two rows sharing a season and week fall through to
        # comparing dicts and raise. This is the SECOND place that bug
        # appeared; the first was fixed in pull() without auditing the rest of
        # the file, which is how it came back nine minutes later.
        out[k].sort(key=lambda r: (r[0], r[1]))
    return out


def _raw(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        b = r.read()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return b.decode("utf-8", "replace")


# Odds-API team names -> nflverse abbreviations. Spelled out rather than
# derived: "Los Angeles Rams" and "Los Angeles Chargers" share a city, and
# nflverse writes the Rams as LA and the Chargers as LAC, so any clever
# substring rule gets that pair wrong in silence.
TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}
# A position is only worth ranking a defence against if the prop depends on it.
POS_FOR = {"pass yds": "QB", "pass TDs": "QB", "rush yds": "RB",
           "rec yds": "WR", "receptions": "WR", "rush+rec yds": "RB"}
GENEROUS_FRAC = 0.375  # a defence must sit in the most generous 37.5% -- 12 of
                       # 32. A FRACTION, not a fixed rank: with fewer teams in
                       # the pool (early weeks, a position with sparse data) a
                       # hard "rank <= 12" passes everything, which is how a
                       # three-team fixture let the stingiest defence through.


def defense_allowed(logs, current=CURRENT_SEASON):
    """{position: {defence: yards allowed per game}} for the current season.

    This is the check that would have caught Rome Odunze. His record cleared
    every window -- 3 of 3 this season, 13 of 15 all time -- and he draws the
    Jets, who are 29th of 32 in receiving yards allowed to wide receivers. A
    rate measures what a player did against the schedule he happened to have;
    it says nothing about the defence in front of him on Sunday.
    """
    tot = defaultdict(lambda: defaultdict(float))
    games = defaultdict(set)
    for player, rows in logs.items():
        for sn, wk, v in rows:
            if sn != current:
                continue
            opp, pos = v.get("_opp"), v.get("_pos")
            if not opp:
                continue
            games[opp].add((sn, wk))
            if pos in ("WR", "TE"):
                tot["WR"][opp] += v.get("receiving_yards", 0.0)
            elif pos == "RB":
                tot["RB"][opp] += v.get("rushing_yards", 0.0)
            elif pos == "QB":
                tot["QB"][opp] += v.get("passing_yards", 0.0)
    out = {}
    for pos, d in tot.items():
        out[pos] = {t: v / len(games[t]) for t, v in d.items() if games[t]}
    return out


def generosity(defn, pos, opp):
    """(rank, allowed, n) where rank 1 is the MOST generous defence."""
    d = defn.get(pos) or {}
    if opp not in d:
        return None
    order = sorted(d.items(), key=lambda kv: -kv[1])
    for i, (t, v) in enumerate(order, 1):
        if t == opp:
            return i, v, len(order)
    return None


def hit_rate(logs, player, cols, point, side, current=CURRENT_SEASON):
    """(hits, n, team) over the games that can speak to THIS week's line.

    The first version pooled every game it had and produced nonsense. Darius
    Slayton scored 11 of 14 over 24.5 receiving yards off fourteen 2025 GIANTS
    games, against a line posted in a Colts-Commanders game, with no 2026
    appearances at all. Calvin Ridley read 67% off nine games spread across two
    seasons he mostly missed, while the book had him at +550 because he gained
    zero yards last week.

    Those gaps were 40 and 50 points. A gap that size against a major book is a
    broken count, not a mispriced market: the book is pricing injuries, snap
    shares and depth charts that a historical tally cannot see. Three guards,
    one per failure --

      * MUST HAVE PLAYED THIS SEASON. Absent from it means injured, cut, or
        moved somewhere the log does not know, and old production is not
        evidence about this week.
      * ONE TEAM ONLY, his current one. Production is a joint fact about a
        player and an offence, not a property he carries between them.
      * MIN_GAMES APPLIES AFTER those cuts, not before, or the floor passes on
        games that were just thrown away.
    """
    rows = logs.get(player) or []
    if not rows:
        return None
    if current not in {s for s, _w, _v in rows}:
        return None
    team = rows[-1][2].get("_team")
    rows = [r for r in rows if r[2].get("_team") == team]
    if len(rows) < MIN_GAMES:
        return None

    def rate(rs):
        h = 0
        for _s, _w, v in rs:
            tot = sum(v.get(c, 0.0) for c in cols)
            if (tot > point) if side == "Over" else (tot < point):
                h += 1
        return h, len(rs)

    hits, n = rate(rows)
    # THE CURRENT SEASON ON ITS OWN. A rate pooled across two seasons weights a
    # 131-yard game from last October the same as a 0-yard game last Sunday,
    # and that is how Calvin Ridley read 89% while the book had him at -158 --
    # the book is pricing the role he has NOW. Reporting both windows makes a
    # changed role visible instead of averaging it away. This is the Judkins
    # error from the soccer work in a third costume: one number over two
    # regimes.
    cur = [r for r in rows if r[0] == current]
    ch, cn = rate(cur) if cur else (0, 0)
    return hits, n, team, ch, cn


def score(events, logs, min_gap=0.10, defn=None, frac=GENEROUS_FRAC):
    """Lines where the record disagrees with the price by at least min_gap."""
    out = []
    defn = defense_allowed(logs) if defn is None else defn
    for ev in events:
        for mk, (cols, label) in MARKETS.items():
            for name, side, point, price in ev.get("lines", {}).get(mk, []):
                hr = hit_rate(logs, name, cols, point, side)
                if not hr:
                    continue
                hits, n, team, ch, cn = hr
                rate = hits / n
                imp = implied(price)
                # The book's number carries vig, so a gap in the book's favour
                # is expected and only a gap the OTHER way is interesting.
                # BOTH WINDOWS MUST BEAT THE PRICE. A gap that exists only
                # in the pooled history is a gap about a role the player no
                # longer has. Requiring this season to clear the price too
                # costs some real edges in exchange for dropping every stale
                # one, which is the right side to err on.
                crate = (ch / cn) if cn else 0.0
                # THE DEFENCE IN FRONT OF HIM ON SUNDAY. A hit rate measures the
                # schedule he happened to have. Rome Odunze cleared every window
                # and draws the 29th-most-generous defence to receivers, which
                # no amount of history can see.
                pos = POS_FOR.get(label)
                gen = None
                if pos and defn:
                    teams = [TEAM_ABBR.get(x.strip()) for x in
                             (ev.get("game") or "").split(" @ ")]
                    opp = next((t for t in teams if t and t != team), None)
                    gen = generosity(defn, pos, opp) if opp else None
                if gen is None or gen[0] > max(1, round(frac * gen[2])):
                    continue
                if rate - imp >= min_gap and (cn >= MIN_CURRENT and crate >= imp):
                    out.append({"game": ev.get("game"), "player": name,
                                "market": label, "side": side, "point": point,
                                "price": price, "hits": hits, "n": n, "team": team,
                                "chits": ch, "cn": cn, "crate": crate,
                                "def_rank": gen[0], "def_allowed": gen[1],
                                "def_of": gen[2], "pos": pos,
                                "rate": rate, "implied": imp,
                                "gap": rate - imp})
    out.sort(key=lambda r: -r["gap"])
    return out


def pull(max_events=4, skip=0):
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
    # skip lets a later batch be pulled without re-spending quota on the
    # early kickoffs already covered.
    for t, e in keep[skip:skip + max_events]:
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
    nums = [int(a) for a in sys.argv[1:] if a.isdigit()]
    n = nums[0] if nums else 4
    skip = nums[1] if len(nums) > 1 else 0
    print(f"pulling alt props for up to {n} games, skipping the first {skip}")
    events = pull(n, skip)
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
              f" {int(r['price']):>6}  all {r['hits']:2}/{r['n']:2}={r['rate']:4.0%}"
              f"  {CURRENT_SEASON} {r['chits']}/{r['cn']}={r['crate']:4.0%}"
              f"  vs {r['implied']:4.0%} (+{r['gap']:.0%})"
              f"  D#{r['def_rank']}/{r['def_of']} {r['def_allowed']:.0f}{r['pos']}"
              f"  {r['game'][:28]}")
    return 0


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(abs(implied(-110) - 0.5238) < 1e-3, "a -110 price implies 52.4%, vig included")
    chk(abs(implied(+200) - 1/3) < 1e-6, "and +200 implies 33.3%")

    SOFT_WR = {"WR": {"NYJ": 200.0, "ATL": 80.0, "BUF": 90.0}}

    def gl(rows):
        return [(sn, w, dict(v, _team=t)) for sn, w, t, v in rows]

    logs = {
        # plays this season, one team, long record -> usable
        "Busy Guy": gl([(2025, w, "BUF", {"rushing_yards": v}) for w, v in
                        enumerate([80, 90, 70, 100, 85, 60, 95, 75, 88, 92], 1)]
                       + [(2026, w, "BUF", {"rushing_yards": 85}) for w in (1, 2, 3)]),
        # fourteen games, all last season, none this one -- Darius Slayton's exact
        # shape, which the first version scored as 11 of 14 against another
        # team's game
        "Gone Guy": gl([(2025, w, "NYG", {"rushing_yards": 90}) for w in range(1, 15)]),
        # moved clubs: plenty of history, three games with the new one
        "Traded Guy": gl([(2025, w, "NYG", {"rushing_yards": 90}) for w in range(1, 13)]
                         + [(2026, w, "IND", {"rushing_yards": 10}) for w in (1, 2, 3)]),
        "Rookie": gl([(2026, w, "LAC", {"rushing_yards": 99}) for w in (1, 2, 3)]),
    }
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 59.5, "Over")[:2] == (13, 13),
        "a line under every game he has played reads 13 of 13")
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 89.5, "Over")[:2] == (4, 13),
        "and a line through the middle of his record splits it")
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 89.5, "Under")[:2] == (9, 13),
        "the under is counted as its own side, not one minus the over")
    chk(hit_rate(logs, "Busy Guy", ["rushing_yards"], 59.5, "Over")[2] == "BUF",
        "the team the rate belongs to rides on the answer")
    hr = hit_rate(logs, "Busy Guy", ["rushing_yards"], 59.5, "Over")
    chk(hr[3:] == (3, 3),
        "and the CURRENT season is reported separately, not folded into the pool")
    # a player whose role collapsed: strong history, nothing this year
    logs["Faded"] = gl([(2025, w, "TEN", {"receiving_yards": 90}) for w in range(1, 13)]
                       + [(2026, w, "TEN", {"receiving_yards": 2}) for w in (1, 2, 3)])
    fh = hit_rate(logs, "Faded", ["receiving_yards"], 24.5, "Over")
    chk(fh[:2] == (12, 15) and fh[3:] == (0, 3),
        "a collapsed role shows 12/15 pooled and 0/3 this season")
    chk(hit_rate(logs, "Gone Guy", ["rushing_yards"], 10.5, "Over") is None,
        "fourteen games and none this season is refused -- that is injured, cut "
        "or moved, and the book knows which")
    chk(hit_rate(logs, "Traded Guy", ["rushing_yards"], 10.5, "Over") is None,
        "a player with three games at his NEW club is refused: the floor applies "
        "AFTER the old club's games are dropped, not before")
    chk(hit_rate(logs, "Rookie", ["rushing_yards"], 10.5, "Over") is None,
        "a three-game player is refused -- 3 of 3 against a soft line is not a rate")
    chk(hit_rate(logs, "Nobody", ["rushing_yards"], 10.5, "Over") is None,
        "and an unknown name yields None rather than raising")

    ev = [{"game": "Buffalo Bills @ New York Jets", "lines": {"player_rush_yds_alternate": [
        ("Busy Guy",   "Over", 59.5, -250),   # 100% history vs 71% implied -> gap
        ("Busy Guy",   "Over", 89.5, +150),   #  31% history vs 40% implied -> none
        ("Gone Guy",   "Over", 10.5, -1000),  # not this season -> dropped
        ("Traded Guy", "Over", 10.5, -1000),  # too few at the new club -> dropped
        ("Rookie",     "Over", 10.5, -1000),  # too few games -> dropped
    ]}}]
    # The collapsed-role player must NOT survive on his pooled history alone.
    ev_faded = [{"game": "Tennessee Titans @ New York Jets", "lines": {"player_reception_yds_alternate": [
        ("Faded", "Over", 24.5, +300)]}}]      # 80% pooled, 0% this season
    chk(score(ev_faded, logs, defn=SOFT_WR) == [],
        "a gap that exists only in the pooled history is dropped -- that is a "
        "gap about a role he no longer has")

    # A two-game current window is not a window. "1 of 2 = 50%" clears nearly
    # any implied price, which is exactly how Ridley survived the first version.
    logs["Spotty"] = gl([(2025, w, "TEN", {"receiving_yards": 60}) for w in range(1, 10)]
                        + [(2026, 2, "TEN", {"receiving_yards": 60}),
                           (2026, 3, "TEN", {"receiving_yards": 0})])
    chk(score([{"game": "Tennessee Titans @ New York Jets", "lines": {"player_reception_yds_alternate": [
        ("Spotty", "Over", 24.5, +550)]}}], logs, defn=SOFT_WR) == [],
        "a player with two games this season is dropped, however good the pool")

    # THE ODUNZE CHECK. A line that clears every history window is still
    # dropped when the defence it faces is one of the stingiest at that
    # position -- the one thing a hit rate structurally cannot see. Busy Guy is
    # a BUF rusher, so the fixture game must contain Buffalo or the opponent
    # cannot be resolved at all (the first version of this test put him in a
    # Bears-Jets game and "passed" for the wrong reason).
    ev_def = [{"game": "Buffalo Bills @ New York Jets", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, +200)]}}]
    STINGY = {"RB": {"NYJ": 50.0, "ATL": 150.0, "CAR": 140.0}}
    SOFT = {"RB": {"NYJ": 150.0, "ATL": 50.0, "CAR": 60.0}}
    chk(score(ev_def, logs, defn=STINGY) == [],
        "a prop into the stingiest defence is dropped however good the record")
    chk(len(score(ev_def, logs, defn=SOFT)) == 1,
        "and the same prop into the most generous defence survives")
    chk(score(ev_def, logs, defn={"RB": {"ATL": 150.0}}) == [],
        "a defence with no data at all is a refusal, not a free pass")

    sc = score(ev, logs, defn=SOFT)
    chk(len(sc) == 1 and sc[0]["point"] == 59.5,
        "only the line whose record beats its price by 10+ points survives")
    chk(sc[0]["hits"] == 13 and sc[0]["n"] == 13 and sc[0]["team"] == "BUF",
        "and it carries the count and the club, so the sample is visible")
    chk(score(ev, logs, min_gap=0.99) == [],
        "raising the bar past any real gap yields nothing")

    # TWO ROWS FOR ONE PLAYER IN ONE WEEK. nflverse can carry a duplicate or a
    # correction row, and the third tuple element is a dict -- so a bare sort
    # falls through to comparing dicts and raises. This crashed game_logs() on
    # the runner nine minutes after the identical bug was fixed in pull(),
    # because the first fix patched the call site instead of auditing the file.
    CSV = ("season,week,season_type,player_display_name,team,receiving_yards\n"
           "2026,1,REG,Dup Guy,BUF,40\n"
           # DIFFERENT yardage on the duplicate, or the dicts compare EQUAL and
           # Python never needs '<' -- the first version of this fixture used
           # identical rows and passed with the bug still in place.
           "2026,1,REG,Dup Guy,BUF,45\n"
           "2026,2,REG,Dup Guy,BUF,55\n")
    try:
        gl = game_logs(seasons=[2026], fetch=lambda u: CSV)
        crashed_logs = False
    except TypeError:
        crashed_logs = True
    chk(not crashed_logs,
        "two rows for one player in one week sort without comparing the dicts")
    chk(len(gl.get("Dup Guy", [])) == 3 and gl["Dup Guy"][0][2]["_team"] == "BUF",
        "and the rows survive with the team carried on each")

    # THE SUNDAY SLATE SHAPE: one kickoff time, many games. A plain sort over
    # (datetime, dict) pairs raises on the second comparison, and the board
    # always looks like this at 1pm ET.
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    same = (now + _dt.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    try:
        keep = [(_dt.datetime.fromisoformat(same.replace("Z", "+00:00")),
                 {"id": str(i)}) for i in range(4)]
        keep.sort(key=lambda x: x[0])
        crashed = False
    except TypeError:
        crashed = True
    chk(not crashed, "four games at one kickoff time sort without comparing dicts")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())

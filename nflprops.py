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
    # ANYTIME TD is the market most parlays are actually built from and the
    # first pull had none of it. It is a 0.5 threshold on rushing+receiving
    # touchdowns, which the same "did he clear it" machinery already handles.
    "player_anytime_td":        (["rushing_tds", "receiving_tds"], "anytime TD"),
    "player_rush_attempts":     (["carries"], "rush att"),
    "player_receptions":        (["receptions"], "receptions"),
    "player_reception_yds":     (["receiving_yards"], "rec yds"),
    "player_rush_yds":          (["rushing_yards"], "rush yds"),
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
                      "receptions", "passing_tds", "rushing_tds",
                      "receiving_tds", "carries", "attempts"):
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
           "rec yds": "WR", "receptions": "WR", "rush+rec yds": "RB",
           "rush att": "RB"}


# GAME SCRIPT. A rushing prop wants his team AHEAD -- a leading team runs clock,
# a trailing one throws it away. Omarion Hampton was recommended as a rushing
# prop for a team priced at +295, which is the shape of a side that spends the
# fourth quarter passing. I had flagged that risk for this exact game hours
# earlier and then did not apply it, because the check lived in my head instead
# of in the file.
SCRIPT_DOG = -0.32     # implied win prob below this and a rushing prop is fading
SCRIPT_FAV = 0.68      # above this and a receiving prop risks garbage-time clock


def script_ok(label, win_prob):
    """Does the likely game script help this prop, or fight it?"""
    if win_prob is None:
        return True                      # no price -> no opinion, not a veto
    if label in ("rush yds", "rush att"):
        return win_prob >= abs(SCRIPT_DOG)
    if label in ("pass yds", "pass TDs", "rec yds", "receptions"):
        return win_prob <= SCRIPT_FAV
    return True


def pos_for(label, player_pos):
    """The pool a prop is measured against: the player's OWN position.

    A receiving line for a tight end is a question about tight ends. The first
    version mapped every receiving market to WR whoever the player was, which
    is how a TE came back carrying a receiver's matchup read.
    """
    if label in ("rec yds", "receptions", "anytime TD"):
        return player_pos if player_pos in ("TE", "WR", "RB") else "WR"
    return POS_FOR.get(label)


INJ = ("https://github.com/nflverse/nflverse-data/releases/download/"
       "injuries/injuries_{yr}.csv")
BAD_STATUS = ("Out", "Doubtful")
BAD_PRACTICE = ("Did Not Participate In Practice",)


def injuries(season=CURRENT_SEASON, fetch=None):
    """{(team, name): status} for the latest week on the report.

    THE GAP THAT MADE EVERY PROP ABOVE SUSPECT. I kept noting that I had no
    injury data and then recommending props anyway -- and recommended Bucky
    Irving in a week where Baker Mayfield did not practice at all with a thumb
    injury, and Irving himself was limited with a glute. A running back's
    receiving prop without his quarterback is a different bet; a receiver with
    a thumb injury is a different bet. nflverse publishes this and I never
    looked.

    'Did not participate' on the Friday report is the signal that matters most
    here, not just the Out/Doubtful tag, because the official game status is
    often still blank two days out.
    """
    try:
        txt = fetch(INJ.format(yr=season)) if fetch else _raw(INJ.format(yr=season))
    except Exception:
        return None                       # unavailable -> refuse, never assume fit
    import csv as _csv
    rows = [r for r in _csv.DictReader(io.StringIO(txt))
            if (r.get("week") or "").isdigit()]
    if not rows:
        return None
    wk = max(int(r["week"]) for r in rows)
    out = {}
    for r in rows:
        if int(r["week"]) != wk:
            continue
        st, pr = (r.get("report_status") or ""), (r.get("practice_status") or "")
        flag = st if st in BAD_STATUS else (pr if pr in BAD_PRACTICE else "")
        if flag:
            out[(r.get("team"), r.get("full_name"))] = (
                flag, r.get("report_primary_injury")
                or r.get("practice_primary_injury") or "", r.get("position"))
    return out


SNAPS = ("https://github.com/nflverse/nflverse-data/releases/download/"
         "snap_counts/snap_counts_{yr}.csv")
MIN_SNAP_PCT = 0.45    # below this he is a rotational piece, not a volume bet


def snap_share(season=CURRENT_SEASON, fetch=None):
    """{(team, player): (latest_pct, trend)} -- is he actually on the field?

    THE VOLUME SIGNAL I NEVER PULLED. Every prop here is a bet on opportunity,
    and snap share is the most direct measure of it there is -- more direct
    than targets, which are themselves downstream of being on the field. It
    has been published all along next to the injury file.

    trend is latest minus the mean of the earlier weeks: a player whose share
    is collapsing is being phased out, and his season-long rate is describing
    a role he no longer has. That is the same regime problem that has bitten
    every other part of this file, measured at its source.
    """
    try:
        txt = fetch(SNAPS.format(yr=season)) if fetch else _raw(SNAPS.format(yr=season))
    except Exception:
        return None
    import csv as _csv
    by = defaultdict(list)
    for r in _csv.DictReader(io.StringIO(txt)):
        if not (r.get("week") or "").isdigit():
            continue
        try:
            pct = float(r.get("offense_pct") or 0)
        except (TypeError, ValueError):
            continue
        by[(r.get("team"), r.get("player"))].append((int(r["week"]), pct))
    out = {}
    for k, v in by.items():
        v.sort()
        latest = v[-1][1]
        prior = [p for _w, p in v[:-1]]
        out[k] = (latest, latest - (sum(prior) / len(prior) if prior else latest))
    return out or None


def qb_of(logs, team, season=CURRENT_SEASON):
    """The team's most-used quarterback this season."""
    best, most = None, -1
    for name, rows in logs.items():
        n = sum(v.get("attempts", 0.0) for sn, _w, v in rows
                if sn == season and v.get("_team") == team and v.get("_pos") == "QB")
        if n > most:
            best, most = name, n
    return best if most > 0 else None


def defense_at(logs, opp, pos, col_sum, thresh, side):
    """How often does this defence let a player at THIS position clear THIS
    number? Two seasons, position-pure, measured at the actual line.

    Three upgrades on the first version, each from a hole the audit found:

      * TWENTY GAMES, not three. Ranking a defence on three weeks is the same
        small-sample error that has bitten this file at every stage.
      * POSITION-PURE. Lumping tight ends into the receiver pool made Houston
        look like the 7th-easiest defence to get 100 receiving yards against.
        Receivers only, it is 5 of 20 -- exactly league average.
      * AT THE ACTUAL NUMBER. A defence that bleeds short catches is not the
        same as one that gives up chunk yardage, and "yards allowed per game"
        cannot tell them apart. The Chargers allow 90+ yards to a receiver 40%
        of the time and 8+ catches 15% of the time. Same defence, opposite
        answer depending on the prop.

    Returns (hits, games) over the best line that position put up each week.
    """
    wk = {}
    for player, rows in logs.items():
        for sn, w, v in rows:
            if v.get("_opp") != opp or v.get("_pos") not in pos:
                continue
            tot = sum(v.get(c, 0.0) for c in col_sum)
            k = (sn, w)
            wk[k] = max(wk.get(k, 0.0), tot)
    if not wk:
        return None
    vals = list(wk.values())
    hits = sum(1 for z in vals if ((z > thresh) if side == "Over" else (z < thresh)))
    return hits, len(vals)





# A TIGHT END IS NOT A WIDE RECEIVER, in either direction. Lumping TEs into the
# WR pool made Houston look soft to receivers; stripping them out without giving
# tight ends a pool of their own then scored Juwan Johnson -- a TE -- against
# receiver data and reported Atlanta at 18/20 (90%) when the tight end number is
# 6/20 (30%). Each position is measured against its own.
POS_POOL = {"QB": ("QB",), "RB": ("RB",), "WR": ("WR",), "TE": ("TE",)}


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


def score(events, logs, min_gap=0.10, inj=None, snaps=None):
    """Lines where the record disagrees with the price by at least min_gap."""
    out = []
    if inj is None:
        inj = injuries() or {}
    if snaps is None:
        snaps = snap_share()
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
                ppos = (logs.get(name) or [(0, 0, {})])[-1][2].get("_pos")
                pos = pos_for(label, ppos)
                teams = [TEAM_ABBR.get(x.strip()) for x in
                         (ev.get("game") or "").split(" @ ")]
                opp = next((t for t in teams if t and t != team), None)
                dres = (defense_at(logs, opp, POS_POOL.get(pos, (pos,)), cols,
                                   point, side) if (pos and opp) else None)
                if not dres or dres[1] < 8:
                    continue
                drate = dres[0] / dres[1]
                # THE DEFENCE HAS TO ALLOW IT TOO. Not "is this defence
                # generous in general" -- does it give up THIS number to THIS
                # position. A 50% floor means better than a coin flip from the
                # defence's side before the player's own form counts at all.
                if drate < 0.50:
                    continue
                # A DEFENCE TEST THAT PASSES EVERYTHING IS NOT A TEST. This
                # measures the BEST player at the position each week, so any
                # low bar -- over 0.5 receptions, over 4.5 receiving yards --
                # comes back 20 of 20 and tells you nothing. Treating that as
                # support put a wall of -300 to -850 near-locks at the top of
                # the list. A line only earns the matchup read when the defence
                # has actually stopped it sometimes.
                if drate >= 0.95:
                    continue
                # THE PLAYER, AND THE MAN THROWING HIM THE BALL. A resting-day
                # DNP is a flag too: it still means he was not on the field,
                # and the reason is the team's word rather than a diagnosis.
                if not script_ok(label, (ev.get("wp") or {}).get(team)):
                    continue
                # ON THE FIELD ENOUGH TO MATTER, and not on the way out.
                # ON THE FIELD ENOUGH TO MATTER, and not on the way out. When
                # the feed is unavailable this cannot veto -- an absent source
                # is not evidence a player is benched.
                sh = (snaps or {}).get((team, name))
                if snaps and ((not sh) or sh[0] < MIN_SNAP_PCT or sh[1] < -0.20):
                    continue
                hurt = inj.get((team, name))
                qb = qb_of(logs, team)
                qhurt = inj.get((team, qb)) if qb else None
                if hurt or (qhurt and label not in ("rush yds", "rush att")):
                    continue
                # And a price this short is not a bet, it is a toll. Ryan has
                # said so every time the list drifted this way.
                if imp > 0.70:
                    continue
                if rate - imp >= min_gap and (cn >= MIN_CURRENT and crate >= imp):
                    out.append({"game": ev.get("game"), "player": name,
                                "market": label, "side": side, "point": point,
                                "price": price, "hits": hits, "n": n, "team": team,
                                "chits": ch, "cn": cn, "crate": crate,
                                "snap": sh[0] if sh else None,
                                "snap_trend": sh[1] if sh else None,
                                "dhits": dres[0], "dn": dres[1],
                                "drate": drate, "pos": pos,
                                "rate": rate, "implied": imp,
                                "gap": rate - imp})
    # Rank by the WEAKER of the two sides -- a prop is only as good as
    # whichever of player form and matchup is softer.
    # The feed repeats a line when more than one book or market key carries it,
    # and the list showed the same prop twice more than once.
    seen, uniq = set(), []
    for r in out:
        k = (r["game"], r["player"], r["market"], r["side"], r["point"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    out = uniq
    out.sort(key=lambda r: -min(r['crate'], r['drate']))
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
               f"&markets={','.join(list(MARKETS) + ['h2h'])}")
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
        # The moneyline rides along so the game script can be judged. One extra
        # market on a request already being made, not an extra request.
        wp = {}
        lines = defaultdict(list)
        for bk in d.get("bookmakers") or []:
            for m in bk.get("markets") or []:
                if m.get("key") == "h2h":
                    outs = m.get("outcomes") or []
                    if len(outs) == 2:
                        ps = [implied(o.get("price")) for o in outs
                              if o.get("price") is not None]
                        if len(ps) == 2 and 1.0 < sum(ps) < 1.35:
                            for o, pv in zip(outs, ps):
                                wp[TEAM_ABBR.get(o.get("name"))] = pv / sum(ps)
                    continue
                for o in m.get("outcomes") or []:
                    if o.get("point") is None or o.get("price") is None:
                        continue
                    lines[m["key"]].append((o.get("description") or o.get("name"),
                                            o.get("name"), float(o["point"]),
                                            float(o["price"])))
        out.append({"game": f"{e.get('away_team')} @ {e.get('home_team')}", "wp": wp,
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
              f"  D {r['dhits']:2}/{r['dn']:2}={r['drate']:4.0%}"
              f"  snap {('%3.0f%%' % (r['snap']*100)) if r['snap'] else ' -- '}"
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

    # Carolina, the soft run defence built above -- the Jets fixture is the
    # stingy one and would correctly reject every line in here.
    ev = [{"game": "Buffalo Bills @ Carolina Panthers", "lines": {"player_rush_yds_alternate": [
        ("Busy Guy",   "Over", 59.5, +120),   # 100% history vs 45% implied -> gap
        ("Busy Guy",   "Over", 89.5, +150),   #  31% history vs 40% implied -> none
        ("Gone Guy",   "Over", 10.5, -1000),  # not this season -> dropped
        ("Traded Guy", "Over", 10.5, -1000),  # too few at the new club -> dropped
        ("Rookie",     "Over", 10.5, -1000),  # too few games -> dropped
    ]}}]
    # The collapsed-role player must NOT survive on his pooled history alone.
    ev_faded = [{"game": "Tennessee Titans @ New York Jets", "lines": {"player_reception_yds_alternate": [
        ("Faded", "Over", 24.5, +300)]}}]      # 80% pooled, 0% this season
    chk(score(ev_faded, logs, snaps={}) == [],
        "a gap that exists only in the pooled history is dropped -- that is a "
        "gap about a role he no longer has")

    # A two-game current window is not a window. "1 of 2 = 50%" clears nearly
    # any implied price, which is exactly how Ridley survived the first version.
    logs["Spotty"] = gl([(2025, w, "TEN", {"receiving_yards": 60}) for w in range(1, 10)]
                        + [(2026, 2, "TEN", {"receiving_yards": 60}),
                           (2026, 3, "TEN", {"receiving_yards": 0})])
    chk(score([{"game": "Tennessee Titans @ New York Jets", "lines": {"player_reception_yds_alternate": [
        ("Spotty", "Over", 24.5, +550)]}}], logs, snaps={}) == [],
        "a player with two games this season is dropped, however good the pool")

    # THE ODUNZE CHECK, rebuilt on the audited test. The defence rate now comes
    # from what OTHER players actually did against that opponent, measured at
    # this exact number, so the fixture has to contain those games.
    def opp_games(opp, pos, col, vals, team="OTH"):
        # Key on the COLUMN too, or two calls for the same opponent overwrite
        # each other and the second silently wipes the first.
        return {f"{opp}-{col}-foe{i}": [(2026, i + 1,
                {col: v, "_team": team, "_opp": opp, "_pos": pos})]
                for i, v in enumerate(vals)}

    base = dict(logs)
    # NYJ have let a back clear 59.5 once in ten -> a stingy run defence
    base.update(opp_games("NYJ", "RB", "rushing_yards",
                          [20, 30, 25, 40, 35, 22, 28, 31, 90, 18]))
    # CAR have let a back clear it in nine of ten -> a soft one
    base.update(opp_games("CAR", "RB", "rushing_yards",
                          [80, 90, 70, 65, 95, 72, 88, 61, 30, 77]))
    ev_stingy = [{"game": "Buffalo Bills @ New York Jets", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, +200)]}}]
    ev_soft = [{"game": "Buffalo Bills @ Carolina Panthers", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, +200)]}}]
    chk(score(ev_stingy, base, snaps={}) == [],
        "a prop the defence allows once in ten is dropped however good his record")
    got_soft = score(ev_soft, base, snaps={})
    chk(len(got_soft) == 1 and got_soft[0]["dhits"] == 9,
        "and the same prop into a defence that allows it 9 of 10 survives, "
        "carrying the defence's own count")
    # A defence with a handful of games is not a sample. Three weeks of
    # defensive data is the error that has bitten this file at every stage, so
    # the floor has to actually bite: MIA below gets four soft games, which a
    # missing floor would happily report as 4 of 4.
    base.update(opp_games("MIA", "RB", "rushing_yards", [80, 90, 85, 95]))
    chk(score([{"game": "Buffalo Bills @ Miami Dolphins", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, +200)]}}], base, snaps={}) == [],
        "a defence with four games is refused -- three weeks of defensive data "
        "is the error that has bitten this file at every stage")

    # THE SAME DEFENCE, TWO DIFFERENT ANSWERS. This is the Chargers finding:
    # they allow chunk yardage and limit catch volume, so the matchup supports
    # the yards line and not the receptions line.
    split = dict(logs)
    split.update(opp_games("LAC", "WR", "receiving_yards",
                           [99, 100, 130, 118, 96, 95, 98, 119, 35, 22]))
    split.update(opp_games("LAC", "WR", "receptions",
                           [5, 6, 4, 5, 6, 3, 9, 5, 6, 4]))
    logs_wr = dict(split)
    logs_wr["WR Guy"] = [(2025, w, {"receiving_yards": 120, "receptions": 9,
                                    "_team": "SEA", "_opp": "X", "_pos": "WR"})
                         for w in range(1, 13)] + \
                        [(2026, w, {"receiving_yards": 120, "receptions": 9,
                                    "_team": "SEA", "_opp": "X", "_pos": "WR"})
                         for w in (1, 2, 3)]
    ev_y = [{"game": "Seattle Seahawks @ Los Angeles Chargers", "lines": {
        "player_reception_yds_alternate": [("WR Guy", "Over", 91.5, -114)]}}]
    ev_r = [{"game": "Seattle Seahawks @ Los Angeles Chargers", "lines": {
        "player_receptions_alternate": [("WR Guy", "Over", 7.5, +132)]}}]
    chk(len(score(ev_y, logs_wr, snaps={})) == 1,
        "the yards line survives a defence that gives up chunk yardage")
    chk(score(ev_r, logs_wr, snaps={}) == [],
        "and the receptions line on the SAME player against the SAME defence "
        "does not -- which is the Chargers in one check")

    sc = score(ev, base, snaps={})
    chk(len(sc) == 1 and sc[0]["point"] == 59.5,
        "only the line whose record beats its price by 10+ points survives")
    chk(sc[0]["hits"] == 13 and sc[0]["n"] == 13 and sc[0]["team"] == "BUF",
        "and it carries the count and the club, so the sample is visible")
    chk(score(ev, logs, min_gap=0.99, snaps={}) == [],
        "raising the bar past any real gap yields nothing")

    # THE INJURY GATE. Bucky Irving was recommended in a week where Baker
    # Mayfield did not practice at all and Irving himself was limited. A
    # receiving prop without the quarterback is a different bet, and the data
    # to know that was published the whole time.
    inj_logs = dict(base)
    inj_logs["QB1"] = [(2026, w, {"attempts": 30.0, "_team": "BUF",
                                  "_opp": "X", "_pos": "QB"}) for w in (1, 2, 3)]
    ev_i = [{"game": "Buffalo Bills @ Carolina Panthers", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, +120)]}}]
    chk(len(score(ev_i, inj_logs, inj={}, snaps={})) == 1, "a clean player is reported")

    # SNAP SHARE. Every prop is a bet on opportunity and this is the most
    # direct measure of it; it was published next to the injury file all along.
    SN_OK = {("BUF", "Busy Guy"): (0.72, +0.05)}
    SN_LOW = {("BUF", "Busy Guy"): (0.30, +0.05)}
    SN_FALL = {("BUF", "Busy Guy"): (0.60, -0.28)}
    SN_MISS = {("BUF", "Someone Else"): (0.80, 0.0)}
    chk(len(score(ev_i, inj_logs, inj={}, snaps=SN_OK)) == 1,
        "a player on 72% of snaps is reported")
    chk(score(ev_i, inj_logs, inj={}, snaps=SN_LOW) == [],
        "a player on 30% of snaps is a rotational piece, not a volume bet")
    chk(score(ev_i, inj_logs, inj={}, snaps=SN_FALL) == [],
        "and a share collapsing 28 points is a role being phased out -- his "
        "season rate describes a job he no longer has")
    chk(score(ev_i, inj_logs, inj={}, snaps=SN_MISS) == [],
        "a player absent from a LIVE snap feed is dropped, not assumed to play")
    chk(len(score(ev_i, inj_logs, inj={}, snaps=None if False else {})) == 1,
        "but an unavailable feed cannot veto -- absence of a source is not "
        "evidence he is benched")

    # DEDUP. The feed repeats a line across books and market keys, and the
    # same prop showed up twice in the output more than once.
    dup = [{"game": "Buffalo Bills @ Carolina Panthers", "wp": {"BUF": 0.63},
            "lines": {"player_rush_yds_alternate": [
                ("Busy Guy", "Over", 59.5, +120),
                ("Busy Guy", "Over", 59.5, +120)]}}]
    chk(len(score(dup, inj_logs, inj={}, snaps=SN_OK)) == 1,
        "a line repeated by the feed is reported once")
    # GAME SCRIPT. Hampton was recommended as a rushing prop for a side priced
    # at +295; a team that far behind spends the fourth quarter throwing.
    dog = [dict(ev_i[0], wp={"BUF": 0.24})]
    chk(score(dog, inj_logs, inj={}, snaps={}) == [],
        "a rushing prop for a heavy underdog is dropped -- he will be throwing")
    fav = [dict(ev_i[0], wp={"BUF": 0.63})]
    chk(len(score(fav, inj_logs, inj={}, snaps={})) == 1,
        "and the same prop for a favourite stands, because a lead means carries")
    chk(len(score([dict(ev_i[0], wp={})], inj_logs, inj={}, snaps={})) == 1,
        "no moneyline means no opinion, not a veto")
    chk(score(ev_i, inj_logs,
              inj={("BUF", "Busy Guy"): ("Out", "Knee", "RB")}, snaps={}) == [],
        "a player who is Out is dropped")
    chk(score(ev_i, inj_logs,
              inj={("BUF", "Busy Guy"): ("Did Not Participate In Practice",
                                         "Glute", "RB")}, snaps={}) == [],
        "and so is one who did not practice, even without a game status")
    # The receiving fixture needs CAR to have a WR defensive record, or the
    # line is dropped for a missing matchup and the QB check never runs --
    # which is why the "ignore the quarterback" mutation slipped through.
    inj_logs.update({f"CAR-rec-foe{i}": [(2026, i + 1, {"receiving_yards": v,
                     "_team": "OTH", "_opp": "CAR", "_pos": "WR"})]
                     for i, v in enumerate([40, 50, 35, 60, 45, 38, 55, 42, 5, 48])})
    inj_logs["Busy Guy"] = [(sn, w, dict(v, receiving_yards=40.0))
                            for sn, w, v in logs["Busy Guy"]]
    ev_rec = [{"game": "Buffalo Bills @ Carolina Panthers", "lines": {
        "player_reception_yds_alternate": [("Busy Guy", "Over", 5.5, +120)]}}]
    chk(len(score(ev_rec, inj_logs, inj={}, snaps={})) == 1,
        "the receiving fixture itself is live when nobody is hurt")

    # A TIGHT END IS MEASURED AGAINST TIGHT ENDS. Atlanta allowed a receiver
    # 50+ yards in 18 of 20 games and a tight end in 6 of 20; scoring Juwan
    # Johnson -- a TE -- against the receiver pool reported 90% for a 30%
    # matchup, and he was on the ticket because of it.
    te = dict(base)
    # 8 of 10 over 49.5, not 10 of 10: at 100% the line is dropped by the
    # uninformative-defence gate and the test passes for the wrong reason,
    # which is exactly what happened on the first attempt.
    te.update({f"ATL-wr{i}": [(2026, i + 1, {"receiving_yards": v,
               "_team": "OTH", "_opp": "ATL", "_pos": "WR"})]
               for i, v in enumerate([90, 90, 90, 90, 90, 90, 90, 90, 10, 10])})
    te.update({f"ATL-te{i}": [(2026, i + 1, {"receiving_yards": v,
               "_team": "OTH", "_opp": "ATL", "_pos": "TE"})]
               for i, v in enumerate([70, 60, 55, 20, 20, 20, 20, 20, 20, 20])})
    te["TE Guy"] = [(2025, w, {"receiving_yards": 70.0, "_team": "NO",
                               "_opp": "X", "_pos": "TE"}) for w in range(1, 13)] + \
                   [(2026, w, {"receiving_yards": 70.0, "_team": "NO",
                               "_opp": "X", "_pos": "TE"}) for w in (1, 2, 3)]
    chk(score([{"game": "New Orleans Saints @ Atlanta Falcons", "lines": {
        "player_reception_yds_alternate": [("TE Guy", "Over", 49.5, +142)]}}],
        te, inj={}, snaps={}) == [],
        "a tight end is scored against TIGHT ENDS, not the receiver pool that "
        "happens to look generous")
    chk(score(ev_rec, inj_logs,
              inj={("BUF", "QB1"): ("Did Not Participate In Practice",
                                    "Thumb", "QB")}, snaps={}) == [],
        "a RECEIVING prop dies with the quarterback -- the Bucky Irving case")
    chk(len(score(ev_i, inj_logs,
                  inj={("BUF", "QB1"): ("Did Not Participate In Practice",
                                        "Thumb", "QB")}, snaps={})) == 1,
        "but a RUSHING prop survives him, because the handoff does not need him")
    # A defence that allowed it in all ten is not evidence -- it is a bar so
    # low the question does not discriminate, which is what buried the list
    # under -300 to -850 locks.
    base2 = dict(base)
    base2.update(opp_games("DEN", "RB", "rushing_yards", [80]*10))
    chk(score([{"game": "Buffalo Bills @ Denver Broncos", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 5.5, +120)]}}], base2, snaps={}) == [],
        "a defence that allows it 10 of 10 gives no read, and the line is dropped")
    chk(score([{"game": "Buffalo Bills @ Carolina Panthers", "lines": {
        "player_rush_yds_alternate": [("Busy Guy", "Over", 59.5, -400)]}}], base, snaps={}) == [],
        "and a price shorter than -233 is a toll, not a bet")

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

    # injuries() ITSELF -- the parsing and the failure mode. Injecting a dict
    # skips both, which is how three mutations in this area passed.
    CSV_INJ = ("season,season_type,team,week,position,full_name,report_status,"
               "practice_status,report_primary_injury,practice_primary_injury\n"
               "2026,REG,TB,4,QB,Baker Mayfield,,Did Not Participate In Practice,,Thumb\n"
               "2026,REG,LA,4,RB,Kyren Williams,,Full Participation in Practice,,\n"
               "2026,REG,NE,3,RB,Old Week,Out,,Knee,\n")
    got = injuries(2026, fetch=lambda u: CSV_INJ)
    chk(got is not None and ("TB", "Baker Mayfield") in got,
        "a did-not-practice quarterback is flagged even with a blank game status")
    chk(("LA", "Kyren Williams") not in got,
        "a full participant is not flagged")
    chk(("NE", "Old Week") not in got,
        "and only the LATEST week counts -- last week's report is not this week's")
    def boom(u):
        raise OSError("feed down")
    chk(injuries(2026, fetch=boom) is None,
        "a feed that cannot be read returns None, so the caller refuses rather "
        "than calling everyone fit")
    chk(injuries(2026, fetch=lambda u: "season,week\n") is None,
        "and an empty report is a refusal too")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())

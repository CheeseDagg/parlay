#!/usr/bin/env python3
"""pull_feeds.py — regenerate the parlay board's feed files from The Odds API.

    python3 pull_feeds.py             # live pull (needs ODDS_API_KEY in env)
    python3 pull_feeds.py --selftest  # offline: fixtures through every generator

WHY THIS EXISTS. The feed files were hand-transcribed twice: first from pasted
screenshots, then from WebFetch — a channel that pipes the page through a small
summarizer model which was caught INVENTING whole slates and flipping minus
signs. The 2026-08-03 board survived that only because three structural checks
(vig-sum coherence, ladder monotonicity, two-draw agreement) were run on every
row. On GitHub Actions this script talks to the API directly over HTTPS and
parses the JSON itself; the fabrication channel is gone. The structural checks
stay anyway — they now guard against feed bugs instead of hallucinations.

WHAT IT WRITES (atomically, tmp+rename):
    times.py    START (today's MLB slate, ET-dated) + FIGHT_START + et()
    mlbml.py    MLBML_RAW  — every game both sides, FanDuel
    totals.py   TOTALS_RAW — full-game alternate-total ladders, FanDuel,
                monotonicity re-asserted at import time in the generated file
    mma.py      MMA_RAW    — ONE LINE PER BOUT (favorite named), FanDuel
    other.py    OTHER_RAW  — boxing / WNBA / CFL / soccer three-ways, FanDuel
    f5.py       F5_RAW    — first-five alternate-total ladders, FanDuel.
                (This was wrongly declared impossible on 2026-08-03: the probe
                used the totals_h1 market names, which return empty for MLB.
                The real key is alternate_totals_1st_5_innings.)
It does NOT touch fd_k_ladder.txt (deliberately empty — pitcher props are
excluded by standing instruction).

REFUSAL RULES, learned from SoccerTool's pull_props:
  * every family can come back empty (off-days exist) but if the WHOLE pull
    yields fewer than MIN_LEGS legs, nothing is overwritten and the exit code
    is non-zero — a dead pull must not dress itself as a quiet day;
  * any 401/402 (bad key / out of credits) aborts before a single write.

STRUCTURAL VALIDATION (same instruments as the manual pull, now automated):
  * two-way vig sum in [1.005, 1.12], three-way in [1.02, 1.18] — a pair that
    de-vigs outside those bands is not a real market and the whole market is
    dropped, loudly;
  * totals ladders must be monotone (higher point => longer Over, shorter
    Under) or the GAME's ladder is dropped, loudly;
  * one MLB game key per day — a doubleheader's second game shares AWAY@HOME
    with the first, board.py keys markets by game, and merged ladders let a
    solver take both halves of what it thinks is one market. The earlier game
    wins, the later one is dropped, loudly.
"""
import json, os, sys, datetime as dt, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"
BOOK_LABEL = "FanDuel"
MIN_LEGS = 12          # below this the pull is dead, not quiet — refuse to write
FIGHT_DAYS = 14        # how far ahead fights / boxing / soccer are pulled
QUOTA = {"remaining": None, "used": None}

# Same 30 clubs as board.TEAM3, duplicated ON PURPOSE: if a broken generated
# feed file ever makes board.py unimportable, this script must still run to
# write the fix. A shared import would weld the repair tool to the wreck.
TEAM3 = {'Arizona Diamondbacks': 'ARI', 'Atlanta Braves': 'ATL',
         'Baltimore Orioles': 'BAL', 'Boston Red Sox': 'BOS',
         'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS',
         'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE',
         'Colorado Rockies': 'COL', 'Detroit Tigers': 'DET',
         'Houston Astros': 'HOU', 'Kansas City Royals': 'KC',
         'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD',
         'Miami Marlins': 'MIA', 'Milwaukee Brewers': 'MIL',
         'Minnesota Twins': 'MIN', 'New York Mets': 'NYM',
         'New York Yankees': 'NYY', 'Athletics': 'ATH',
         'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT',
         'San Diego Padres': 'SD', 'San Francisco Giants': 'SF',
         'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL',
         'Tampa Bay Rays': 'TB', 'Texas Rangers': 'TEX',
         'Toronto Blue Jays': 'TOR', 'Washington Nationals': 'WSH'}
assert len(set(TEAM3.values())) == len(TEAM3) == 30

# Curated, not discovered: /v4/sports lists ~40 active soccer leagues and every
# /odds call costs credits whether or not FanDuel prices the league. These are
# the leagues where FanDuel actually posts heavy favourites in August.
SOCCER_KEYS = [
    "soccer_uefa_champs_league_qualification",
    "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga",
    "soccer_turkey_super_league", "soccer_greece_super_league",
    "soccer_sweden_allsvenskan", "soccer_finland_veikkausliiga",
    "soccer_norway_eliteserien", "soccer_china_superleague",
    "soccer_usa_mls", "soccer_brazil_campeonato", "soccer_mexico_ligamx",
]
TWO_WAY = [("basketball_wnba", "WNBA"), ("americanfootball_cfl", "CFL"),
           ("boxing_boxing", "BOX")]
MMA_KEY = "mma_mixed_martial_arts"


# ---------------------------------------------------------------- plumbing
def _get(url, _retry=True):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            h = r.headers
            if h.get("x-requests-remaining") is not None:
                QUOTA["remaining"] = h.get("x-requests-remaining")
                QUOTA["used"] = h.get("x-requests-used")
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # The provider's error BODY names the actual reason (invalid key vs
        # quota vs throttle) and two runner-side 401s were undiagnosable
        # without it. Log it, and retry auth-ish errors once after a pause --
        # the same key kept working from elsewhere during both failures.
        try:
            body = e.read().decode()[:300]
        except Exception:
            body = "(unreadable)"
        print(f"  API HTTP {e.code}: {body}")
        if _retry and e.code in (401, 429):
            import time
            time.sleep(20)
            return _get(url, _retry=False)
        raise


def _utc_min(iso):
    """API ISO stamp -> the board's 'YYYY-MM-DDTHH:MMZ' minute format."""
    t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _et_zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception:
        return dt.timezone(dt.timedelta(hours=-4))


def _today_et():
    return dt.datetime.now(_et_zone()).date()


def _et_day_window_utc(day):
    lo = dt.datetime.combine(day, dt.time.min).replace(tzinfo=_et_zone())
    hi = dt.datetime.combine(day, dt.time.max).replace(tzinfo=_et_zone())
    f = "%Y-%m-%dT%H:%M:%SZ"
    return (lo.astimezone(dt.timezone.utc).strftime(f),
            hi.astimezone(dt.timezone.utc).strftime(f))


def _dec(am):
    am = int(am)
    return 1 + (am / 100 if am > 0 else 100 / -am)


def _imp(am):
    return 1.0 / _dec(am)


def vig_ok(prices, three_way=False):
    s = sum(_imp(p) for p in prices)
    lo, hi = ((1.02, 1.18) if three_way else (1.005, 1.12))
    return lo <= s <= hi, round(s, 4)


def _short(name, surname=False):
    """A one-word handle for group labels. Labels only — never a market key."""
    drop = {"fc", "cf", "sc", "nk", "ik", "if", "sk", "ac", "cd", "de", "afc",
            "bk", "aif", "the"}
    words = [w for w in str(name).replace("-", " ").split() if w.lower() not in drop]
    if not words:
        return str(name)[:8]
    if surname:
        return words[-1]
    if len(words) == 1:
        return words[0][:10]
    return "".join(w[0].upper() for w in words)[:4]


# ---------------------------------------------------------------- fetchers
def fd_markets(event_odds):
    """the FanDuel bookmaker block from an event-odds response, or None."""
    for bk in event_odds.get("bookmakers", []):
        if bk.get("key") == BOOK:
            return bk.get("markets", [])
    return None


def pull_mlb(log):
    """-> (start {g: utc}, ml_lines [], totals_lines []) for TODAY's ET slate."""
    lo, hi = _et_day_window_utc(_today_et())
    q = urllib.parse.urlencode({"apiKey": KEY, "dateFormat": "iso",
                                "commenceTimeFrom": lo, "commenceTimeTo": hi})
    events = _get(f"{BASE}/sports/baseball_mlb/events?{q}")
    start, ml, tot, f5 = {}, [], [], []
    seen = {}
    for ev in sorted(events, key=lambda e: e.get("commence_time", "")):
        away, home = TEAM3.get(ev.get("away_team")), TEAM3.get(ev.get("home_team"))
        if not away or not home:
            log.append(f"MLB: unknown club in {ev.get('away_team')}@{ev.get('home_team')} — skipped")
            continue
        g = f"{away}@{home}"
        if g in seen:
            log.append(f"MLB: {g} appears twice today (doubleheader) — keeping the "
                       f"{seen[g]} game, dropping {_utc_min(ev['commence_time'])}. "
                       f"One game key per day or ladders merge.")
            continue
        t = _utc_min(ev["commence_time"])
        seen[g] = t
        # THE F5 MARKET KEY IS NOT WHAT THE DOCS PATTERN SUGGESTS. This feed's
        # first-five market is alternate_totals_1st_5_innings — NOT totals_h1 /
        # alternate_totals_h1, which return an empty bookmakers array for MLB.
        # Probing the h1 names on 2026-08-03 produced a confident, thrice-
        # "verified", WRONG conclusion that FanDuel posts no F5 markets at all;
        # the 07-31 hand pull had used the right key all along. An empty
        # response proves the KEY is wrong before it proves the MARKET is gone.
        q2 = urllib.parse.urlencode({"apiKey": KEY, "regions": "us",
                                     "markets": "h2h,alternate_totals,alternate_totals_1st_5_innings",
                                     "oddsFormat": "american", "bookmakers": BOOK})
        try:
            data = _get(f"{BASE}/sports/baseball_mlb/events/{ev['id']}/odds?{q2}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 402):
                raise
            log.append(f"MLB: {g} odds fetch HTTP {e.code} — skipped")
            continue
        mkts = fd_markets(data)
        if mkts is None:
            log.append(f"MLB: {g} has no FanDuel book — skipped")
            continue
        wrote_any = False
        for mk in mkts:
            if mk.get("key") == "h2h":
                oc = {o["name"]: int(o["price"]) for o in mk.get("outcomes", [])
                      if o.get("price") is not None}
                if len(oc) == 2:
                    (n1, p1), (n2, p2) = oc.items()
                    ok, s = vig_ok([p1, p2])
                    if not ok:
                        log.append(f"MLB: {g} moneyline vig-sum {s} out of band — dropped")
                    else:
                        ml.append(f"{t}|{g}|{n1} ML|{p1}|{p2}")
                        ml.append(f"{t}|{g}|{n2} ML|{p2}|{p1}")
                        wrote_any = True
            elif mk.get("key") in ("alternate_totals", "alternate_totals_1st_5_innings"):
                rungs = {}
                for o in mk.get("outcomes", []):
                    if o.get("point") is None or o.get("price") is None:
                        continue
                    rungs.setdefault(float(o["point"]), {})[o.get("name")] = int(o["price"])
                lad = []
                for pt in sorted(rungs):
                    two = rungs[pt]
                    if "Over" not in two or "Under" not in two:
                        continue
                    ok, s = vig_ok([two["Over"], two["Under"]])
                    if not ok:
                        log.append(f"MLB: {g} {mk['key']} {pt} vig-sum {s} out of band — rung dropped")
                        continue
                    lad.append((pt, two["Over"], two["Under"]))
                mono = all(_dec(b[1]) > _dec(a[1]) and _dec(b[2]) < _dec(a[2])
                           for a, b in zip(lad, lad[1:]))
                if lad and not mono:
                    log.append(f"MLB: {g} {mk['key']} ladder NOT monotone — dropped. "
                               f"These prices cannot all be real.")
                elif lad:
                    if mk["key"] == "alternate_totals":
                        for pt, ov, un in lad:
                            tot.append(f"{g}|{BOOK_LABEL}|{pt}|{ov}|{un}")
                    else:
                        for pt, ov, un in lad:
                            f5.append(f"{g}|{pt}|{ov}|{un}")
                    wrote_any = True
        if wrote_any:
            start[g] = t
        else:
            seen.pop(g, None)
    log.append(f"MLB: {len(start)} games, {len(ml)//2} moneylines, "
               f"{len(tot)} total rungs, {len(f5)} F5 rungs")
    return start, ml, tot, f5


def pull_mma(log):
    """-> (fight_start {name: utc}, mma_lines []). ONE line per bout: board.py
    builds BOTH sides off one line, keyed ('F', card, who); a second line for
    the opponent mints a second market for the same fight and a solver could
    put both men on one ticket."""
    q = urllib.parse.urlencode({
        "apiKey": KEY, "regions": "us", "markets": "h2h",
        "oddsFormat": "american", "bookmakers": BOOK, "dateFormat": "iso",
        "commenceTimeTo": (dt.datetime.now(dt.timezone.utc)
                           + dt.timedelta(days=FIGHT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    data = _get(f"{BASE}/sports/{MMA_KEY}/odds?{q}")
    fight_start, lines = {}, []
    for ev in sorted(data, key=lambda e: e.get("commence_time", "")):
        mkts = fd_markets(ev)
        if not mkts:
            continue
        for mk in mkts:
            if mk.get("key") != "h2h":
                continue
            oc = [(o["name"], int(o["price"])) for o in mk.get("outcomes", [])
                  if o.get("price") is not None]
            if len(oc) != 2:
                continue
            ok, s = vig_ok([p for _, p in oc])
            if not ok:
                log.append(f"MMA: {oc[0][0]} vs {oc[1][0]} vig-sum {s} out of band — dropped")
                continue
            oc.sort(key=lambda x: _dec(x[1]))          # shortest price first
            fav, dog = oc
            if fav[0] in fight_start:
                log.append(f"MMA: {fav[0]} already on the board — second bout dropped "
                           f"(FIGHT_START is keyed by name)")
                continue
            t = _utc_min(ev["commence_time"])
            day = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            card = f"MMA {day.astimezone(_et_zone()).strftime('%m-%d')}"
            fight_start[fav[0]] = t
            lines.append(f"{BOOK_LABEL}|{card}|{fav[0]}|{fav[1]}|{dog[1]}")
    log.append(f"MMA: {len(lines)} bouts")
    return fight_start, lines


def pull_other(log):
    """-> other_lines [] for boxing / WNBA / CFL (2-way) and soccer (3-way)."""
    lines = []
    to = (dt.datetime.now(dt.timezone.utc)
          + dt.timedelta(days=FIGHT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def q_for():
        return urllib.parse.urlencode({
            "apiKey": KEY, "regions": "us", "markets": "h2h",
            "oddsFormat": "american", "bookmakers": BOOK, "dateFormat": "iso",
            "commenceTimeTo": to})

    for skey, tag in TWO_WAY:
        try:
            data = _get(f"{BASE}/sports/{skey}/odds?{q_for()}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 402):
                raise
            log.append(f"{tag}: fetch HTTP {e.code} — family skipped")
            continue
        n0 = len(lines)
        for ev in sorted(data, key=lambda e: e.get("commence_time", "")):
            mkts = fd_markets(ev)
            if not mkts:
                continue
            for mk in mkts:
                if mk.get("key") != "h2h":
                    continue
                oc = [(o["name"], int(o["price"])) for o in mk.get("outcomes", [])
                      if o.get("price") is not None]
                if len(oc) != 2:
                    continue
                ok, s = vig_ok([p for _, p in oc])
                if not ok:
                    log.append(f"{tag}: {oc[0][0]} vs {oc[1][0]} vig-sum {s} — dropped")
                    continue
                t = _utc_min(ev["commence_time"])
                sur = (tag == "BOX")
                grp = f"{tag} {_short(oc[0][0], sur)}-{_short(oc[1][0], sur)}"
                for i, (nm, pr) in enumerate(oc):
                    other = oc[1 - i][1]
                    lines.append(f"{tag}|{grp}|{nm}|{pr}|{other}|{t}")
        log.append(f"{tag}: {(len(lines)-n0)//2} markets")

    for skey in SOCCER_KEYS:
        try:
            data = _get(f"{BASE}/sports/{skey}/odds?{q_for()}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 402):
                raise
            log.append(f"SOC {skey}: HTTP {e.code} — league skipped")
            continue
        n0 = len(lines)
        for ev in sorted(data, key=lambda e: e.get("commence_time", "")):
            mkts = fd_markets(ev)
            if not mkts:
                continue
            for mk in mkts:
                if mk.get("key") != "h2h":
                    continue
                oc = [(o["name"], int(o["price"])) for o in mk.get("outcomes", [])
                      if o.get("price") is not None]
                if len(oc) != 3:
                    continue                     # one-sided books can't be de-vigged
                ok, s = vig_ok([p for _, p in oc], three_way=True)
                if not ok:
                    log.append(f"SOC: {ev.get('home_team')} vs {ev.get('away_team')} "
                               f"vig-sum {s} — dropped")
                    continue
                t = _utc_min(ev["commence_time"])
                names = [nm for nm, _ in oc if nm != "Draw"]
                grp = f"SOC {_short(names[0])}-{_short(names[1])}" if len(names) == 2 \
                    else f"SOC {_short(ev.get('home_team', '?'))}"
                for i, (nm, pr) in enumerate(oc):
                    others = ",".join(str(p) for j, (_, p) in enumerate(oc) if j != i)
                    lines.append(f"SOC|{grp}|{nm}|{pr}|{others}|{t}")
        if len(lines) > n0:
            log.append(f"SOC {skey}: {(len(lines)-n0)//3} fixtures")
    return lines


# ---------------------------------------------------------------- generators
ET_FUNC = '''def et(utc):
    """UTC string -> Eastern wall clock, WITH THE DATE. Fixed -4 offset; fine
    inside the EDT window this board lives in. The date is not decoration:
    three 'Sat's on one ticket can be three different Saturdays."""
    from datetime import datetime, timedelta
    d = datetime.strptime(utc, "%Y-%m-%dT%H:%MZ") - timedelta(hours=4)
    return d.strftime("%a %-m/%-d %-I:%M%p").replace("AM", "am").replace("PM", "pm")
'''

GEN_HEADER = ('"""GENERATED by pull_feeds.py — do not hand-edit; the next pull '
              'overwrites this file.\nGenerated {ts} from The Odds API, '
              '{book} prices only.\n{extra}"""\n')


def _write(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(content)
    os.replace(tmp, path)


def gen_times(start, fight_start, ts):
    body = GEN_HEADER.format(ts=ts, book=BOOK_LABEL, extra=(
        "START holds TODAY'S MLB slate only (one game key per day -- a "
        "doubleheader's second game is dropped upstream). FIGHT_START is keyed "
        "by the favourite named in mma.py, ONE entry per bout."))
    body += "\nSTART = {\n"
    for g, t in sorted(start.items(), key=lambda kv: kv[1]):
        body += f'    "{g}": "{t}",\n'
    body += "}\n\nFIGHT_START = {\n"
    for who, t in sorted(fight_start.items(), key=lambda kv: (kv[1], kv[0])):
        body += f'    "{who}": "{t}",\n'
    body += "}\n\n" + ET_FUNC
    return body


def gen_raw_module(varname, lines, ts, extra):
    body = GEN_HEADER.format(ts=ts, book=BOOK_LABEL, extra=extra)
    body += f'\n{varname} = """\n' + "\n".join(lines) + '\n"""\n'
    return body


MONO_CHECK = '''

def _dec(a):
    a = int(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)

def _check_monotone(raw=None):
    from collections import defaultdict
    lad = defaultdict(list)
    for _l in (raw or TOTALS_RAW).strip().splitlines():
        if not _l.strip():
            continue
        _g, _bk, _pt, _ov, _un = _l.split('|')
        lad[(_g, _bk)].append((float(_pt), _dec(_ov), _dec(_un)))
    bad = []
    for _k, rungs in lad.items():
        rungs.sort()
        for (p0, o0, u0), (p1, o1, u1) in zip(rungs, rungs[1:]):
            if o1 <= o0:
                bad.append(f"{_k[0]} {_k[1]}: Over {p1} is not longer than Over {p0}")
            if u1 >= u0:
                bad.append(f"{_k[0]} {_k[1]}: Under {p1} is not shorter than Under {p0}")
    return bad

_bad = _check_monotone()
assert not _bad, ("totals.py ladder is not monotone -- these prices cannot all be "
                  "real:\\n  " + "\\n  ".join(_bad))
'''


def generate_all(start, ml, tot, fight_start, mma_lines, other_lines, f5_lines=(), outdir=None):
    """Write the five feed files. Returns list of paths written."""
    outdir = outdir or HERE
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    paths = []
    p = os.path.join(outdir, "times.py")
    _write(p, gen_times(start, fight_start, ts)); paths.append(p)
    p = os.path.join(outdir, "mlbml.py")
    _write(p, gen_raw_module("MLBML_RAW", ml, ts, (
        "UTC|AWAY@HOME|Team ML|price|opp_price. Both sides of every game: the "
        "de-vig needs the pair. 'No moneylining baseball teams' is enforced at "
        "solve time with --nofam=ML, not by hiding the market.")))
    paths.append(p)
    p = os.path.join(outdir, "totals.py")
    body = gen_raw_module("TOTALS_RAW", tot, ts, (
        "AWAY@HOME|Book|point|over|under. Monotonicity is asserted below at "
        "import time -- a broken ladder must crash, not price."))
    body += "\nGAME_OF = {}\n" + MONO_CHECK
    _write(p, body); paths.append(p)
    p = os.path.join(outdir, "f5.py")
    body = gen_raw_module("F5_RAW", list(f5_lines), ts, (
        "GAME|POINT|OVER|UNDER — FanDuel first-five-inning alternate totals, "
        "market key alternate_totals_1st_5_innings (NOT totals_h1, which is "
        "empty for MLB and once produced a false 'F5 does not exist' verdict). "
        "Shares the ('GT', game) market key with the full-game ladder in "
        "board.py, so a solver takes at most one total per game."))
    _write(p, body); paths.append(p)
    p = os.path.join(outdir, "mma.py")
    _write(p, gen_raw_module("MMA_RAW", mma_lines, ts, (
        "Book|card|favourite|fav_price|dog_price. ONE LINE PER BOUT -- board.py "
        "builds both sides from it; a second line would mint a second market "
        "for the same fight. No model involved: the UFC forward test went "
        "0-for-5 against the market on disagreements.")))
    paths.append(p)
    p = os.path.join(outdir, "other.py")
    _write(p, gen_raw_module("OTHER_RAW", other_lines, ts, (
        "SPORT|GROUP|SELECTION|PRICE|OTHER_PRICES|UTC. Two-way: boxing, WNBA, "
        "CFL. Three-way (with Draw): soccer. Every outcome of a market is "
        "listed under one group so the solver can take at most one side.")))
    paths.append(p)
    return paths


# ---------------------------------------------------------------- selftest
def selftest():
    import tempfile, subprocess
    tmp = tempfile.mkdtemp()
    start = {"WSH@PHI": "2026-08-03T22:41Z", "SD@ARI": "2026-08-04T01:41Z"}
    ml = ["2026-08-03T22:41Z|WSH@PHI|Philadelphia Phillies ML|-146|136",
          "2026-08-03T22:41Z|WSH@PHI|Washington Nationals ML|136|-146"]
    tot = ["WSH@PHI|FanDuel|7.5|205|-260", "WSH@PHI|FanDuel|8.5|310|-410",
           "WSH@PHI|FanDuel|9.5|450|-650"]
    fs = {"Ty Miller": "2026-08-09T00:00Z"}
    mm = ["FanDuel|MMA 08-08|Ty Miller|-350|255"]
    ot = ["WNBA|WNBA NYL-SEA|New York Liberty|-310|240|2026-08-03T23:00Z",
          "WNBA|WNBA NYL-SEA|Seattle Storm|240|-310|2026-08-03T23:00Z",
          "SOC|SOC PSV-Ajax|PSV Eindhoven|-550|1200,650|2026-08-08T18:00Z",
          "SOC|SOC PSV-Ajax|Ajax|1200|-550,650|2026-08-08T18:00Z",
          "SOC|SOC PSV-Ajax|Draw|650|-550,1200|2026-08-08T18:00Z"]
    f5x = ["WSH@PHI|7.5|300|-450", "WSH@PHI|8.5|430|-750", "WSH@PHI|9.5|640|-1450"]
    paths = generate_all(start, ml, tot, fs, mm, ot, f5x, outdir=tmp)
    ok = 0

    def chk(cond, msg):
        nonlocal ok
        assert cond, msg
        ok += 1

    # every generated module must parse AND expose its contract
    ns = {}
    exec(open(os.path.join(tmp, "times.py")).read(), ns)
    chk(ns["START"] == start, "times.py round-trips START")
    chk(ns["FIGHT_START"] == fs, "times.py round-trips FIGHT_START")
    chk(ns["et"]("2026-08-09T00:00Z") == "Sat 8/8 8:00pm",
        "generated et() carries the date")
    ns = {}
    exec(open(os.path.join(tmp, "totals.py")).read(), ns)   # monotone assert runs here
    chk([l for l in ns["TOTALS_RAW"].strip().splitlines()] == tot,
        "totals.py round-trips and its import-time monotone check passes")
    bad_tot = tot + ["WSH@PHI|FanDuel|10.5|150|-150"]       # Over shorter than 9.5's: broken
    try:
        exec(gen_raw_module("TOTALS_RAW", bad_tot, "t", "x") + "\nGAME_OF={}\n" + MONO_CHECK, {})
        raise SystemExit("selftest: broken ladder was accepted")
    except AssertionError:
        chk(True, "a non-monotone ladder refuses to import")
    for mod, var, want in (("mlbml", "MLBML_RAW", ml), ("mma", "MMA_RAW", mm),
                           ("other", "OTHER_RAW", ot), ("f5", "F5_RAW", f5x)):
        ns = {}
        exec(open(os.path.join(tmp, f"{mod}.py")).read(), ns)
        chk(ns[var].strip().splitlines() == want, f"{mod}.py round-trips")
    # parser-shape checks: every line splits into the arity board.py expects
    for l in ml:
        chk(len(l.split("|")) == 5, "ml arity")
    for l in tot:
        chk(len(l.split("|")) == 5, "totals arity")
    for l in f5x:
        chk(len(l.split("|")) == 4, "f5 arity (board.py splits it four ways)")
    for l in mm:
        chk(len(l.split("|")) == 5, "mma arity")
    for l in ot:
        chk(len(l.split("|")) == 6, "other arity")
    # vig instrument
    chk(vig_ok([-650, 450])[0], "sane pair passes vig band")
    chk(not vig_ok([-650, 650])[0], "vig-free pair fails the band (too good to be real)")
    chk(not vig_ok([-650, 200])[0], "over-vigged pair fails the band")
    chk(vig_ok([-550, 1200, 650], three_way=True)[0], "sane three-way passes")
    # _short never returns empty and BOX uses surnames
    chk(_short("David Nyika", surname=True) == "Nyika", "BOX groups use surnames")
    chk(_short("New York Liberty") == "NYL", "team groups use initials")
    print(f"PULL_FEEDS SELFTEST PASS — {ok} checks (generators, round-trips, "
          f"monotone refusal, vig bands, arity)")


# ---------------------------------------------------------------- main
def main():
    if "--selftest" in sys.argv:
        selftest(); return
    if not KEY:
        sys.exit("ODDS_API_KEY is not set. On GitHub this is a repo secret; "
                 "locally: ODDS_API_KEY=... python3 pull_feeds.py")
    log = []
    try:
        start, ml, tot, f5_lines = pull_mlb(log)
        fight_start, mma_lines = pull_mma(log)
        other_lines = pull_other(log)
    except urllib.error.HTTPError as e:
        for l in log:
            print(" ", l)
        sys.exit(f"ABORT, nothing written: HTTP {e.code} from the API. NOTE: this "
                 f"provider returns 401 for an EXHAUSTED QUOTA as well as a bad "
                 f"key -- read the error body logged above before blaming the key.")
    for l in log:
        print(" ", l)
    n_legs = len(ml) + (len(tot) + len(f5_lines)) * 2 + len(mma_lines) * 2 + len(other_lines)
    print(f"  legs representable: ~{n_legs} · API credits remaining {QUOTA['remaining']}")
    if n_legs < MIN_LEGS:
        sys.exit(f"ABORT, nothing written: only {n_legs} legs came back "
                 f"(floor {MIN_LEGS}). A dead pull must not dress itself as a "
                 f"quiet day — yesterday's board stays, and board.py will age it "
                 f"honestly.")
    paths = generate_all(start, ml, tot, fight_start, mma_lines, other_lines, f5_lines)
    for p in paths:
        print(f"  wrote {os.path.basename(p)}")
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(HERE, "board.py"), "--selftest"],
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    print("  board selftest:", tail[-1] if tail else "(no output)")
    if r.returncode != 0:
        sys.exit("board.py --selftest FAILED against the freshly written feeds — "
                 "the files are on disk for inspection; do not trust this board "
                 "until it passes.")


if __name__ == "__main__":
    main()

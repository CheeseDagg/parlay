#!/usr/bin/env python3
"""ticket.py -- price the open ticket off LIVE prices, not remembered ones.

    ODDS_API_KEY=... python3 ticket.py        # runner does this
    python3 ticket.py --selftest

WHY THIS FILE EXISTS.

Every price I have quoted on this ticket so far was quoted from the scroll-back
of an earlier run. That is the same failure as naming a starting quarterback
from memory: by the time it is said out loud, nobody has checked it. A price
that moved two hours ago makes the parlay quote wrong, and the quote is the
whole deliverable -- Ryan is deciding whether to put money down on the number
this prints.

So: every leg here is looked up by NAME in the live FanDuel board. The stored
`want` price is not used for the maths. It is used for exactly one thing --
comparing against what came back, so a line that has moved gets flagged as
MOVED instead of silently repricing the ticket under the old headline.

A leg that cannot be found is not dropped and it is not guessed. The ticket
prints as incomplete, because an 8-leg quote built from 7 readable legs is a
lie about a number Ryan is about to bet.

DE-VIG, AND WHERE IT IS REFUSED.

Where both sides of a market are posted, the pair is de-vigged (power, via
slips.py -- books load margin on the longshot side and these legs are mostly
heavy favourites, which multiplicative de-vig systematically understates).
Where only one side is posted -- the usual case for an alternate prop ladder --
there is nothing to de-vig against, so the implied probability is printed RAW
and marked `vig`. It is too high by the book's margin and saying otherwise
would be inventing the other half of a market that is not there.

The parlay price is the product of the decimal prices actually read. The
probability is the product of the leg probabilities. Independence is assumed
ACROSS sports and that is close to true -- a UFC bout and an NFL game share no
script. Two legs inside one NFL game would not be independent; this ticket has
none, and the script says so if that ever stops being the case.
"""
import datetime as dt, json, os, sys, urllib.error, urllib.parse, urllib.request

import slips

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("ODDS_API_KEY", "")
BOOK = "fanduel"

# The ticket as Ryan has built it. `want` is the last price seen, for drift
# detection only -- never for the maths.
LEGS = [
    {"kind": "mma", "who": "Jacobe Smith",   "want": -950},
    {"kind": "mma", "who": "Anthony Wint",   "want": -550},
    {"kind": "mma", "who": "Marcus McGhee",  "want": -520},
    {"kind": "mma", "who": "Ateba Gautier",  "want": -245},
    {"kind": "mma", "who": "Payton Talbott", "want": -750},
    {"kind": "prop", "who": "Jakobi Meyers",  "stat": "reception_yds",
     "side": "Over", "point": 39.5, "want": -114},
    {"kind": "prop", "who": "Brock Purdy",    "stat": "rush_yds",
     "side": "Over", "point": 24.5, "want": 198},
    # Back on the rushing line per Ryan. 59.5 is a rung on the alt ladder, not
    # a main line, so the number is pinned exactly -- there is no "main" to
    # track and a ladder rung can be pulled outright, which must read as a
    # refusal rather than quietly becoming the next rung up.
    {"kind": "prop", "who": "Kyren Williams", "stat": "rush_yds",
     "side": "Over", "point": 59.5, "want": 104},
]

# Priced alongside but NOT in the ticket: the line this one replaced. Ryan
# asked for rush+rec; the rushing line is printed next to it so the swap is
# documented with two live numbers instead of my say-so.
COMPARE = [
    # The rush+rec line he swapped off, kept on the board so the decision stays
    # two live numbers. "main" rather than a pinned number because this one
    # moved 74.5 -> 77.5 -> 74.5 inside ten minutes; any change from
    # `want_point` prints as LINE MOVED instead of passing quietly.
    {"kind": "prop", "who": "Kyren Williams", "stat": "rush_reception_yds",
     "side": "Over", "point": "main", "want_point": 74.5, "want": -113},
    # The pass+rush question. Two rungs, because the ladder prices 224.5, 249.5
    # and 274.5 at 67.7%, 52.8% and 38.8% while BOTH historical samples -- the
    # 12 Purdy starts and the 17 quality starters Denver has faced -- have a
    # hole between roughly 235 and 280 and therefore read identically at all
    # three. Where a gap exists only because of that hole it is a sampling
    # artifact, so the two rungs either side of it are priced together and the
    # difference between them is the thing to look at.
    {"kind": "prop", "who": "Brock Purdy", "stat": "pass_rush_yds",
     "side": "Over", "point": 249.5, "want": -112},
    {"kind": "prop", "who": "Brock Purdy", "stat": "pass_rush_yds",
     "side": "Over", "point": 274.5, "want": 158},
    # The two rungs BELOW the hole, which is where the yards-per-attempt
    # arithmetic actually lands. Denver has held its three 2026 starters to
    # 6.5, 6.8 and 7.1 yards an attempt; at 7.0 on Purdy's 2026 attempt counts
    # that is around 203 passing plus about 25 rushing, so what the defence
    # permits sits near 225 -- not near 275.
    {"kind": "prop", "who": "Brock Purdy", "stat": "pass_rush_yds",
     "side": "Over", "point": 224.5, "want": -210},
    {"kind": "prop", "who": "Brock Purdy", "stat": "pass_rush_yds",
     "side": "Over", "point": 199.5, "want": -380},
]

MARKETS = {  # a prop may be posted on the standard market, the alt ladder, or both
    "reception_yds": ("player_reception_yds", "player_reception_yds_alternate"),
    "rush_yds": ("player_rush_yds", "player_rush_yds_alternate"),
    "rush_reception_yds": ("player_rush_reception_yds",
                           "player_rush_reception_yds_alternate"),
    "pass_rush_yds": ("player_pass_rush_yds", "player_pass_rush_yds_alternate"),
    "pass_yds": ("player_pass_yds", "player_pass_yds_alternate"),
}


# ------------------------------------------------------------------ transport
def _get(url, fetch=None):
    if fetch is not None:
        return fetch(url)
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.loads(r.read().decode())


def surname(name):
    """Last token, lowercased. Fighter and player names come back from the API
    in a different shape than a book prints them ('Jacobe Smith' vs
    'J. Smith'), and a surname match is the part that survives that. It is also
    why `who` is checked against the FULL string first -- two Smiths on one
    card would otherwise collide, and the caller is told rather than guessing."""
    return str(name).strip().split()[-1].lower() if str(name).strip() else ""


def first(name):
    """First token, lowercased, trailing period stripped."""
    t = str(name).strip().split()
    return t[0].rstrip(".").lower() if t and t[0] else ""


def first_ok(a, b):
    """Are these two first names the same name, one of them possibly
    abbreviated? True for ('J', 'Jacobe') -- which is the whole reason the
    surname fallback exists -- and False for ('Kyren', 'Javonte') or
    ('Jon', 'Jacobe'). Prefix-compatibility, not initial-equality: matching on
    the initial alone still lets Jon Smith become Jacobe Smith."""
    fa, fb = first(a), first(b)
    if not fa or not fb:
        return False
    return fa.startswith(fb) or fb.startswith(fa)


def find_name(cands, who, allow_surname=True):
    """Match `who` against candidate strings. Exact first; then surname, but
    ONLY when the first initial agrees too.

    THE INITIAL IS NOT A NICETY. A bare surname fallback put Javonte Williams
    on this ticket in place of Kyren Williams: the event list is ordered by
    kickoff, the Cowboys game came first, "Williams" matched inside it, and the
    leg filled with a Dallas running back's price while the Rams game was never
    even read. Nothing flagged it, because within that one event there was no
    second Williams to look ambiguous against.

    So surname alone is never enough. 'J. Smith' still resolves to 'Jacobe
    Smith' -- the abbreviation the fallback exists for -- while 'Kyren
    Williams' can no longer reach 'Javonte Williams', and nor can 'Jon Smith'
    reach 'Jacobe Smith': matching on the shared initial alone would allow
    that second one straight through.

    allow_surname=False turns the fallback off entirely, which is what the prop
    path uses: the Odds API writes player props with full names, so there is
    nothing to recover and an unreadable leg should fail loudly instead."""
    low = who.lower()
    hits = [c for c in cands if low in str(c).lower()]
    if len(hits) == 1:
        return hits[0], "exact"
    if len(hits) > 1:
        return None, f"ambiguous: {sorted(set(map(str, hits)))}"
    if not allow_surname:
        return None, "not on the board under that exact name"
    sn = surname(who)
    hits = [c for c in cands if surname(c) == sn and first_ok(c, who)]
    if len(hits) == 1:
        return hits[0], "surname"
    if len(hits) > 1:
        return None, f"ambiguous on surname: {sorted(set(map(str, hits)))}"
    return None, "not on the board"


# ------------------------------------------------------------------- mma legs
def price_mma(board, who):
    """board: the /odds h2h payload. Returns a priced leg dict or {'err':...}."""
    for ev in board:
        names = []
        for bk in ev.get("bookmakers") or []:
            if bk.get("key") != BOOK:
                continue
            for m in bk.get("markets") or []:
                if m.get("key") == "h2h":
                    names = [o.get("name") for o in (m.get("outcomes") or [])]
        if not names:
            continue
        hit, how = find_name(names, who)
        if hit is None:
            if how.startswith("ambiguous"):
                return {"err": how}
            continue
        outs = {}
        for bk in ev.get("bookmakers") or []:
            if bk.get("key") != BOOK:
                continue
            for m in bk.get("markets") or []:
                if m.get("key") == "h2h":
                    for o in m.get("outcomes") or []:
                        outs[o.get("name")] = o.get("price")
        mine = outs.get(hit)
        other = [p for n, p in outs.items() if n != hit]
        if mine is None:
            return {"err": "no price posted"}
        leg = {"lab": f"{hit} ML", "price": mine, "sport": "MMA",
               "event": f"{ev.get('away_team')} / {ev.get('home_team')}",
               "start": ev.get("commence_time"), "how": how}
        if len(other) == 1 and other[0] is not None:
            pair = slips.devig([_imp(mine), _imp(other[0])])
            leg["p"], leg["basis"] = pair[0], "devig"
            leg["opp"] = other[0]
        else:
            leg["p"], leg["basis"] = _imp(mine), "vig"
        return leg
    return {"err": "not on the board"}


def _imp(american):
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


# ------------------------------------------------------------------ prop legs
def price_prop(ev_payload, spec):
    """ev_payload: one event's /odds response. Finds the exact point on either
    the standard market or the alt ladder."""
    keys = MARKETS[spec["stat"]]
    std_key = keys[0]                      # the standard market, not the ladder
    rows, main_rows = [], []
    for bk in ev_payload.get("bookmakers") or []:
        if bk.get("key") != BOOK:
            continue
        for m in bk.get("markets") or []:
            if m.get("key") not in keys:
                continue
            for o in m.get("outcomes") or []:
                rows.append(o)
                if m.get("key") == std_key:
                    main_rows.append(o)
    if not rows:
        return None
    # Dedupe before matching: one player has a row per side and per ladder
    # point, so the raw list is full of legitimate repeats and every match
    # would read as ambiguous.
    descs = sorted({str(o.get("description")) for o in rows if o.get("description")})
    hit, how = find_name(descs, spec["who"], allow_surname=False)
    if hit is None:
        return {"err": how} if how.startswith("ambiguous") else None
    if spec["point"] == "main":
        # The MAIN line lives on the standard market key; the alt ladder is a
        # fan of numbers around it. Reading the ladder here would make "main"
        # mean "whichever rung sorted first", so only the standard key counts.
        std = [o for o in main_rows if o.get("description") == hit
               and o.get("point") is not None]
        pts = sorted({float(o["point"]) for o in std})
        if not pts:
            return {"err": "no main line posted (alt ladder only)"}
        if len(pts) > 1:
            return {"err": f"more than one main line posted: {pts}"}
        point = pts[0]
    else:
        point = float(spec["point"])
    mine = [o for o in rows if o.get("description") == hit
            and float(o.get("point") or -1) == point]
    side = [o for o in mine if str(o.get("name")) == spec["side"]]
    if not side:
        posted = sorted({float(o.get("point")) for o in rows
                         if o.get("description") == hit and o.get("point") is not None})
        return {"err": f"{point} not posted; board has {posted}"}
    price = side[0].get("price")
    other = [o for o in mine if str(o.get("name")) != spec["side"]]
    leg = {"lab": f"{hit} {spec['side']} {point:g} {spec['stat'].replace('_',' ')}",
           "price": price, "sport": "PROP", "how": how, "who": spec["who"],
           "point": point, "side": spec["side"], "stat": spec["stat"],
           "event": f"{ev_payload.get('away_team')} @ {ev_payload.get('home_team')}",
           "start": ev_payload.get("commence_time")}
    if len(other) == 1 and other[0].get("price") is not None:
        pair = slips.devig([_imp(price), _imp(other[0]["price"])])
        leg["p"], leg["basis"] = pair[0], "devig"
        leg["opp"] = other[0]["price"]
    else:
        leg["p"], leg["basis"] = _imp(price), "vig"
    return leg


# ---------------------------------------------------------------------- maths
def parlay(legs):
    """(decimal, american, probability). Raises if a leg has no price."""
    d, p = 1.0, 1.0
    for lg in legs:
        d *= slips.dec(lg["price"])
        p *= lg["p"]
    return d, slips.american(d), p


def opponent(event, team, abbr):
    """The other team in 'Away @ Home', as an nflverse abbreviation.

    Returns None rather than a guess when the event names cannot both be
    resolved or neither of them is the player's team -- a defence measured
    against the wrong opponent is worse than no defence column, because it
    looks like an answer."""
    if not event or not team:
        return None
    parts = [x.strip() for x in str(event).split("@")]
    if len(parts) != 2:
        return None
    abbrs = [abbr.get(x) for x in parts]
    if None in abbrs:
        return None
    if team not in abbrs:
        return None
    a, b = abbrs
    return b if a == team else a


def model_p(legs, hist):
    """The ticket's probability using the HISTORICAL rate wherever there is
    one, and the de-vigged market everywhere else.

    WHY BOTH NUMBERS GET PRINTED. Multiplying de-vigged market probabilities
    gives the book's own view of the ticket, and comparing that against the
    book's payout is a tautology -- it returns the vig as a negative "edge"
    every time, for every ticket, which is information about parlays in general
    and none about this one.

    The historical rate is a different claim and it can be wrong in a way the
    market is not: it describes the role a player HAD. So the two numbers are
    printed side by side and the gap between them is the actual content. Where
    they disagree, the role table above says which one to distrust."""
    p = 1.0
    for lg in legs:
        h = hist.get(lg.get("lab"))
        p *= h[0] if h else lg["p"]
    return p


def marginal(legs, hist, stake=33.0):
    """What each leg ADDS to the ticket, and what it risks to add it.

    WHAT THIS SHOWS, AND WHAT I WRONGLY EXPECTED IT TO SHOW. I built this
    column believing it would prove that a near-lock is a bad buy: Purdy over
    199.5 pass+rush is a 75% leg that lifts the payout from $308 to $389, which
    LOOKS like $81 in exchange for a one-in-four chance of losing everything.
    The selftest refused the claim, and it was right to.

    The arithmetic: added = stake * without * (dec - 1), and for a leg priced
    at its own probability dec - 1 = (1 - p)/p, so added / (1 - p) collapses to
    stake * without / p -- the same number for every rung of a consistently
    priced ladder. Moving up or down it changes HOW OFTEN you collect and HOW
    MUCH, in exact proportion. It does not change the bet's value.

    So the column is still worth printing, for the opposite reason to the one I
    built it for: where $/risk is flat across the ticket, the book is pricing
    consistently and there is no free lunch in picking a safer or longer rung.
    Where one leg's figure stands out, that is a leg whose HISTORICAL rate
    disagrees with its price -- which is the only thing that can make one rung
    genuinely better than another.

    Returns per leg: (added payout, probability used, dollars added per point
    of failure risk)."""
    full = 1.0
    for lg in legs:
        full *= slips.dec(lg["price"])
    out = []
    for lg in legs:
        without = full / slips.dec(lg["price"])
        h = hist.get(lg.get("lab"))
        pr = h[0] if h else lg["p"]
        added = stake * (full - without)
        risk = 1.0 - pr
        out.append((lg, added, pr, (added / risk) if risk > 1e-9 else float("inf")))
    return out


def same_event(legs):
    """Legs sharing one event are NOT independent -- the product would be wrong.
    Returns the offending event names."""
    seen, dup = {}, []
    for lg in legs:
        ev = lg.get("event")
        if not ev:
            continue
        seen.setdefault(ev, 0)
        seen[ev] += 1
    return [ev for ev, n in seen.items() if n > 1]


# ------------------------------------------------------------------- selftest
def selftest():
    f = 0

    def ck(cond, msg):
        nonlocal f
        if not cond:
            print(f"  FAIL {msg}"); f += 1

    ck(abs(_imp(-110) - 0.5238) < 1e-3, "imp(-110)")
    ck(abs(_imp(+200) - 1 / 3) < 1e-6, "imp(+200)")
    d, am, p = parlay([{"price": 100, "p": 0.5}, {"price": 100, "p": 0.5}])
    ck(abs(d - 4.0) < 1e-9 and am == 300 and abs(p - 0.25) < 1e-9, f"parlay {d} {am} {p}")

    # name matching
    ck(find_name(["Jacobe Smith", "Kevin Jones"], "Jacobe Smith")[0] == "Jacobe Smith", "exact")
    ck(find_name(["J. Smith", "Kevin Jones"], "Jacobe Smith")[1] == "surname", "surname fallback")
    ck(find_name(["Jacobe Smith", "Ian Smith"], "Jon Smith")[0] is None,
       "a different first name must not ride the surname in")
    # THE JAVONTE CASE. A bare surname fallback filled this ticket's rush+rec
    # leg with Javonte Williams' price because the Cowboys game kicks off
    # first and "Williams" matched inside it. Nothing looked ambiguous -- there
    # was only one Williams in that event.
    ck(find_name(["Javonte Williams", "Jake Ferguson"], "Kyren Williams")[0] is None,
       "Kyren must not resolve to Javonte")
    ck(find_name(["J. Smith", "Kevin Jones"], "Jacobe Smith")[0] == "J. Smith",
       "an abbreviated first name must still resolve")
    # genuinely ambiguous: two candidates both compatible with an abbreviation
    amb = find_name(["Jacobe Smith", "Jon Smith"], "J Smith")
    ck(amb[0] is None and "ambiguous" in amb[1], f"two compatible Smiths {amb}")
    ck("Jacobe Smith" in amb[1] and "Jon Smith" in amb[1], "refusal names both")
    # the prop path takes exact names only
    ck(find_name(["J. Smith"], "Jacobe Smith", allow_surname=False)[0] is None,
       "prop path must not fall back to surname")
    ck(find_name(["Kevin Jones"], "Jacobe Smith")[1] == "not on the board", "absent")

    # mma: two-way de-vig, and the favourite must come back BELOW its raw implied
    board = [{"away_team": "A Guy", "home_team": "Jacobe Smith",
              "commence_time": "2026-10-04T02:00:00Z",
              "bookmakers": [{"key": "fanduel", "markets": [{"key": "h2h", "outcomes": [
                  {"name": "Jacobe Smith", "price": -950},
                  {"name": "A Guy", "price": 620}]}]}]}]
    lg = price_mma(board, "Jacobe Smith")
    ck(lg.get("price") == -950 and lg.get("basis") == "devig", f"mma leg {lg}")
    ck(lg["p"] < _imp(-950), f"devig must reduce the favourite: {lg['p']} vs {_imp(-950)}")
    # Power vs multiplicative is not a stylistic choice on this ticket. On
    # -950/+620 multiplicative returns 0.867 and power 0.893 -- it shaves the
    # favourite 2.6 points harder, and five favourite legs compound that into
    # a materially wrong parlay number. Both answers are pinned so a silent
    # switch of method cannot pass.
    ck(abs(lg["p"] - 0.8929) < 2e-3, f"power de-vig expected ~0.893, got {lg['p']}")
    ck(abs(slips.devig([_imp(-950), _imp(620)], "mult")[0] - 0.8669) < 2e-3,
       "multiplicative reference moved")

    # the prop path must ignore every book that is not FanDuel, same as h2h
    dk = {"away_team": "LAR", "home_team": "PHI",
          "bookmakers": [{"key": "draftkings", "markets": [
              {"key": "player_rush_yds", "outcomes": [
                  {"description": "Kyren Williams", "name": "Over",
                   "point": 59.5, "price": 104}]}]}]}
    ck(price_prop(dk, {"who": "Kyren Williams", "stat": "rush_yds",
                       "side": "Over", "point": 59.5}) is None,
       "prop path must ignore non-FanDuel books")

    # The prop path takes the full name or nothing. An abbreviated description
    # must fail loudly rather than be recovered by surname -- that recovery is
    # what crossed Kyren with Javonte.
    abbr = {"away_team": "a", "home_team": "b", "bookmakers": [{"key": "fanduel",
            "markets": [{"key": "player_rush_yds", "outcomes": [
                {"description": "K. Williams", "name": "Over",
                 "point": 59.5, "price": 104}]}]}]}
    ck(price_prop(abbr, {"who": "Kyren Williams", "stat": "rush_yds",
                         "side": "Over", "point": 59.5}) is None,
       "prop path must not surname-match an abbreviated description")
    ck(price_mma(board, "Payton Talbott").get("err") == "not on the board", "absent fighter")
    # one-sided h2h cannot be de-vigged
    solo = [{"away_team": "x", "home_team": "y", "bookmakers": [{"key": "fanduel",
            "markets": [{"key": "h2h", "outcomes": [{"name": "Lone Guy", "price": -300}]}]}]}]
    ck(price_mma(solo, "Lone Guy")["basis"] == "vig", "one-sided h2h is raw")
    # a book other than FanDuel must not be read
    other = [{"away_team": "x", "home_team": "y", "bookmakers": [{"key": "draftkings",
             "markets": [{"key": "h2h", "outcomes": [{"name": "Lone Guy", "price": -300}]}]}]}]
    ck(price_mma(other, "Lone Guy").get("err") == "not on the board", "non-FanDuel ignored")

    # prop: exact point on the alt ladder, one-sided -> vig
    ev = {"away_team": "LAR", "home_team": "PHI",
          "bookmakers": [{"key": "fanduel", "markets": [
              {"key": "player_rush_reception_yds", "outcomes": [
                  {"description": "Kyren Williams", "name": "Over", "point": 74.5, "price": -113},
                  {"description": "Kyren Williams", "name": "Under", "point": 74.5, "price": -115}]},
              {"key": "player_rush_yds_alternate", "outcomes": [
                  {"description": "Kyren Williams", "name": "Over", "point": 59.5, "price": 104}]}]}]}
    lg = price_prop(ev, {"who": "Kyren Williams", "stat": "rush_reception_yds",
                         "side": "Over", "point": 74.5})
    ck(lg["price"] == -113 and lg["basis"] == "devig", f"rush+rec {lg}")
    lg2 = price_prop(ev, {"who": "Kyren Williams", "stat": "rush_yds",
                          "side": "Over", "point": 59.5})
    ck(lg2["price"] == 104 and lg2["basis"] == "vig", f"one-sided alt must stay raw: {lg2}")
    # wrong number must report what IS posted, not snap to the nearest
    bad = price_prop(ev, {"who": "Kyren Williams", "stat": "rush_reception_yds",
                          "side": "Over", "point": 69.5})
    ck(bad and "not posted" in bad.get("err", ""), f"absent point {bad}")
    ck(bad and "74.5" in bad.get("err", ""), "refusal must name the posted line")
    # wrong side must not fall through to the other side's price
    uns = price_prop(ev, {"who": "Kyren Williams", "stat": "rush_yds",
                          "side": "Under", "point": 59.5})
    ck(uns and "err" in uns, f"missing side must refuse, got {uns}")
    ck(price_prop(ev, {"who": "Nobody Here", "stat": "rush_yds",
                       "side": "Over", "point": 59.5}) is None, "absent player")

    # "main" must read the STANDARD market, never a ladder rung. The fixture
    # puts 77.5 on the standard key and 59.5/90.5 on the ladder; resolving to
    # anything but 77.5 means the ladder leaked in.
    mix = {"away_team": "LAR", "home_team": "PHI", "bookmakers": [{"key": "fanduel",
           "markets": [
             {"key": "player_rush_reception_yds", "outcomes": [
                 {"description": "Kyren Williams", "name": "Over", "point": 77.5, "price": -110},
                 {"description": "Kyren Williams", "name": "Under", "point": 77.5, "price": -110}]},
             {"key": "player_rush_reception_yds_alternate", "outcomes": [
                 {"description": "Kyren Williams", "name": "Over", "point": 59.5, "price": -250},
                 {"description": "Kyren Williams", "name": "Over", "point": 90.5, "price": 180}]}]}]}
    m = price_prop(mix, {"who": "Kyren Williams", "stat": "rush_reception_yds",
                         "side": "Over", "point": "main"})
    ck(m.get("point") == 77.5 and m.get("price") == -110, f"main line {m}")
    ck("77.5" in m["lab"] and "59.5" not in m["lab"], f"label carries the live line: {m['lab']}")
    # ladder only -> there is no main line, and that must be said, not invented
    ladder = {"away_team": "a", "home_team": "b", "bookmakers": [{"key": "fanduel",
              "markets": [{"key": "player_rush_yds_alternate", "outcomes": [
                  {"description": "Kyren Williams", "name": "Over", "point": 59.5, "price": 104}]}]}]}
    lo = price_prop(ladder, {"who": "Kyren Williams", "stat": "rush_yds",
                             "side": "Over", "point": "main"})
    ck(lo and "no main line" in lo.get("err", ""), f"ladder-only main {lo}")
    # two numbers on the standard key is not a main line either
    two = {"away_team": "a", "home_team": "b", "bookmakers": [{"key": "fanduel",
           "markets": [{"key": "player_rush_yds", "outcomes": [
               {"description": "Kyren Williams", "name": "Over", "point": 59.5, "price": 104},
               {"description": "Kyren Williams", "name": "Over", "point": 64.5, "price": 130}]}]}]}
    tw = price_prop(two, {"who": "Kyren Williams", "stat": "rush_yds",
                          "side": "Over", "point": "main"})
    ck(tw and "more than one main line" in tw.get("err", ""), f"two main lines {tw}")

    AB = {"Denver Broncos": "DEN", "San Francisco 49ers": "SF",
          "Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC"}
    ck(opponent("Denver Broncos @ San Francisco 49ers", "SF", AB) == "DEN",
       "home player's opponent")
    ck(opponent("Denver Broncos @ San Francisco 49ers", "DEN", AB) == "SF",
       "away player's opponent")
    # LA/LAC share a city; a substring rule would cross them, so the map is
    # exact and an unmapped name must refuse rather than resolve loosely.
    ck(opponent("Los Angeles Rams @ Los Angeles Chargers", "LA", AB) == "LAC",
       "the two Los Angeles teams must not cross")
    ck(opponent("Denver Broncos @ San Francisco 49ers", "JAX", AB) is None,
       "a player on neither side must refuse")
    ck(opponent("Some Team @ San Francisco 49ers", "SF", AB) is None,
       "an unmapped team name must refuse")
    ck(opponent("Denver Broncos vs San Francisco 49ers", "SF", AB) is None,
       "an unparseable event must refuse")
    ck(opponent(None, "SF", AB) is None, "no event must refuse")
    # The length check is what stops a three-part string from reaching the
    # two-way unpack and raising instead of refusing.
    try:
        r3 = opponent("A @ B @ C", "AA", {"A": "AA", "B": "BB", "C": "CC"})
    except Exception as ex:
        r3 = f"raised {type(ex).__name__}"
    ck(r3 is None, f"a three-part event must refuse, not raise: {r3}")

    # model_p: historical rate where there is one, market price elsewhere
    legs = [{"lab": "A", "p": 0.90}, {"lab": "B", "p": 0.50}]
    ck(abs(model_p(legs, {}) - 0.45) < 1e-9, "no history -> market")
    ck(abs(model_p(legs, {"B": (0.75, 9, 12, 2, 3)}) - 0.675) < 1e-9,
       "history replaces the market price for that leg only")
    ck(abs(model_p(legs, {"Z": (0.1, 1, 10, 0, 0)}) - 0.45) < 1e-9,
       "history for an absent leg must not be applied")

    # marginal: a leg that doubles the payout adds the stake back; a near-lock
    # that barely moves the price must show a tiny $/risk even at a high hit
    # rate. Both directions are pinned because the whole point of the column
    # is that it disagrees with the hit rate.
    mlegs = [{"lab": "big", "price": 198, "p": 0.336},
             {"lab": "lock", "price": -380, "p": 0.792}]
    mg = {r[0]["lab"]: r for r in marginal(mlegs, {}, stake=100.0)}
    # full = 2.98 * 1.26316 = 3.7642; without big = 1.26316
    ck(abs(mg["big"][1] - 100 * (3.76421 - 1.26316)) < 0.5, f"big adds {mg['big'][1]}")
    ck(abs(mg["lock"][1] - 100 * (3.76421 - 2.98)) < 0.5, f"lock adds {mg['lock'][1]}")
    ck(mg["big"][1] > mg["lock"][1], "the longshot must add more payout")
    # THE DEGENERACY, PINNED. When each leg's probability IS its implied
    # price, $/risk is the same for every rung -- the ladder trades frequency
    # for size at a fixed rate. This is the assertion I originally got
    # backwards, so it is pinned tightly enough that a change in either
    # direction fails.
    ck(abs(mg["big"][3] - mg["lock"][3]) < 2.0,
       f"a consistently priced ladder must give a flat $/risk: "
       f"{mg['big'][3]:.0f} vs {mg['lock'][3]:.0f}")
    ck(abs(mg["lock"][3] - mg["lock"][1] / 0.208) < 1.0, "$/risk divides by failure odds")
    # history overrides the market price in the probability, same as model_p
    mg2 = {r[0]["lab"]: r for r in marginal(mlegs, {"lock": (0.50, 6, 12, 1, 3)},
                                            stake=100.0)}
    ck(abs(mg2["lock"][2] - 0.50) < 1e-9, "marginal must use the historical rate")
    ck(mg2["lock"][3] < mg["lock"][3], "a worse hit rate must worsen $/risk")
    # ...and the column must then stop being flat, which is the ONE case where
    # it tells you something.
    ck(abs(mg2["big"][3] - mg2["lock"][3]) > 50,
       "history disagreeing with the price must break the flat line")

    # same-event detection
    ck(same_event([{"event": "A @ B"}, {"event": "A @ B"}]) == ["A @ B"], "same event caught")
    ck(same_event([{"event": "A @ B"}, {"event": "C @ D"}]) == [], "distinct events fine")

    print("ticket selftest:", "ok" if f == 0 else f"{f} FAILURES")
    return 1 if f else 0


# ------------------------------------------------------------------------ run
def main():
    if not KEY:
        print("no ODDS_API_KEY"); return 1
    out, missing = [], []

    mma = _get(f"{BASE}/sports/mma_mixed_martial_arts/odds/?apiKey={KEY}"
               f"&regions=us&bookmakers={BOOK}&oddsFormat=american&markets=h2h")
    for spec in [l for l in LEGS if l["kind"] == "mma"]:
        lg = price_mma(mma, spec["who"])
        if "err" in lg:
            missing.append((spec["who"], lg["err"])); continue
        lg["want"] = spec["want"]
        lg["want_point"] = None
        out.append(lg)

    props = [l for l in LEGS + COMPARE if l["kind"] == "prop"]
    if props:
        evs = _get(f"{BASE}/sports/americanfootball_nfl/events?apiKey={KEY}")
        want_keys = sorted({k for p in props for k in MARKETS[p["stat"]]})
        todo = list(props)
        for ev in evs:
            if not todo:
                break
            try:
                d = _get(f"{BASE}/sports/americanfootball_nfl/events/{ev['id']}/odds/"
                         f"?apiKey={KEY}&regions=us&bookmakers={BOOK}"
                         f"&oddsFormat=american&markets={','.join(want_keys)}")
            except urllib.error.HTTPError:
                continue
            still = []
            for spec in todo:
                lg = price_prop(d, spec)
                if lg is None:
                    still.append(spec); continue
                if "err" in lg:
                    missing.append((spec["who"], lg["err"])); continue
                lg["want"] = spec["want"]
                lg["want_point"] = spec.get("want_point")
                lg["compare"] = spec in COMPARE
                out.append(lg)
            todo = still
        for spec in todo:
            missing.append((spec["who"], "no FanDuel line found on the slate"))

    tick = [l for l in out if not l.get("compare")]
    cmps = [l for l in out if l.get("compare")]

    print(f"read {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%MZ}  FanDuel live\n")
    hdr = f"{'leg':52s} {'price':>7s} {'was':>7s} {'p':>7s}  basis"
    print(hdr); print("-" * len(hdr))
    for lg in tick:
        flags = ""
        if lg["price"] != lg["want"]:
            flags += "  PRICE MOVED"
        if lg.get("want_point") is not None and lg.get("point") != lg["want_point"]:
            flags += f"  LINE MOVED from {lg['want_point']:g}"
        print(f"{lg['lab'][:52]:52s} {lg['price']:+7d} {lg['want']:+7d} "
              f"{lg['p']*100:6.1f}% {lg['basis']}{flags}")

    # HISTORY AT THE LINE THAT IS ACTUALLY POSTED, AND THE ROLE BEHIND IT.
    #
    # A hit rate counted at 74.5 says nothing about a bet graded at 77.5, and
    # the two got three yards apart inside seven minutes. Counting here, off
    # the same payload that produced the price, is the only way the record and
    # the number cannot drift apart inside one quote.
    #
    # Snap share and the practice report sit in the same table on purpose. A
    # historical rate is a claim about a role, so the role has to be visible
    # next to it or the rate is unreadable: 9-of-12 means one thing at 81% of
    # snaps and something else entirely for a man who did not practice.
    props = [l for l in tick + cmps if l.get("stat")]
    hist = {}
    if props:
        try:
            import nflprops
            logs = nflprops.game_logs(nflprops.SEASONS)
            snaps = nflprops.snap_share()
            inj = nflprops.injuries()
        except Exception as ex:
            print(f"\nno history: {type(ex).__name__}: {ex}")
            logs = snaps = inj = None
        if logs:
            print(f"\n{'history at the posted line':46s} {'all':>9s} {'2026':>7s}"
                  f" {'vs opp':>8s} {'snap':>6s} {'trend':>6s}  practice")
            print("-" * 104)
            for lg in props:
                # nflverse column lookup. Some stats appear in MARKETS only
                # under the _alternate key (rush+rec is one), so both spellings
                # are tried rather than one being assumed to exist.
                mk = nflprops.MARKETS.get(f"player_{lg['stat']}") or \
                     nflprops.MARKETS.get(f"player_{lg['stat']}_alternate")
                if not mk:
                    print(f"{lg['lab'][:46]:46s} {'no stat mapping':>18s}")
                    continue
                r = nflprops.hit_rate(logs, lg["who"], mk[0], lg["point"], lg["side"])
                tag = "  (comparison)" if lg.get("compare") else ""
                if not r:
                    print(f"{lg['lab'][:46]:46s} {'no usable log':>18s}{tag}")
                    continue
                h, n, team, ch, cn = r
                hist[lg["lab"]] = (h / n, h, n, ch, cn)
                # THE DEFENCE, AT THIS NUMBER, AGAINST THIS POSITION. The
                # column that answers "should we be doing this at all": Purdy's
                # own 3-for-3 on rushing yards means little against a defence
                # that has allowed 4 of 17 quality starters over the same bar.
                ppos = (logs.get(lg["who"]) or [(0, 0, {})])[-1][2].get("_pos")
                opp = opponent(lg.get("event"), team, nflprops.TEAM_ABBR)
                dtxt = f"{'   --':>8s}"
                if opp and ppos in nflprops.POS_POOL:
                    dr = nflprops.defense_at(logs, opp, nflprops.POS_POOL[ppos],
                                             mk[0], lg["point"], lg["side"])
                    if dr:
                        dtxt = f"{dr[0]:3d}/{dr[1]:<2d} {opp:>3s}"
                sp = (snaps or {}).get((team, lg["who"]))
                sptxt = f"{sp[0]*100:5.0f}% {sp[1]*100:+5.0f}" if sp else f"{'  --':>6s} {'--':>6s}"
                flag = (inj or {}).get((team, lg["who"]))
                # inj is None when the file could not be read -- which is not
                # the same as a clean report, and must not print as one.
                if inj is None:
                    prac = "UNKNOWN (report unread)"
                elif flag:
                    prac = f"{flag[0]} ({flag[1]})"
                else:
                    prac = "clear"
                print(f"{lg['lab'][:46]:46s} {h:>4d}/{n:<4d} {ch:>3d}/{cn:<3d}"
                      f" {dtxt} {sptxt}  {prac}{tag}")

    # The comparison prints BEFORE any bail-out. The first live run bailed on
    # the rush+rec leg and swallowed the alternative with it, which left the
    # one decision Ryan actually asked about with nothing under it.
    for lg in cmps:
        swap = [x for x in tick if x.get("who") == lg.get("who")]
        print("\nnot on the ticket, for comparison:")
        moved = "" if lg["price"] == lg["want"] else f"  (was {lg['want']:+d})"
        lmoved = ("" if lg.get("want_point") in (None, lg.get("point"))
                  else f"  LINE MOVED from {lg['want_point']:g}")
        print(f"  {lg['lab']}  {lg['price']:+d}{moved} "
              f"p={lg['p']*100:.1f}% {lg['basis']}{lmoved}")
        if not swap:
            # A comparison leg exists to replace something. If it matches no
            # player on the ticket the reprice would silently print the ticket
            # unchanged, which reads as "the swap costs nothing".
            print("  replaces no leg on this ticket -- nothing to reprice "
                  "against")
        elif not missing:
            rest = [x for x in tick if x not in swap]
            d2, am2, p2 = parlay(rest + [lg])
            m2 = model_p(rest + [lg], hist)
            print(f"  that ticket instead: {am2:+d}  market {p2*100:.1f}%  "
                  f"history {m2*100:.1f}%  $33 -> ${33*d2:,.0f}")

    if missing:
        print("\nCOULD NOT READ -- ticket is incomplete, do not bet this quote:")
        for who, why in missing:
            print(f"  {who}: {why}")
        print("\nno parlay price printed")
        return 1

    dupes = same_event(tick)
    if dupes:
        print("\nWARNING -- legs share an event, the product below is NOT the "
              "honest number:", dupes)

    d, am, p = parlay(tick)
    mp = model_p(tick, hist)
    print(f"\n{len(tick)} legs   {am:+d}   $33 -> ${33*d:,.0f}")
    print(f"  market  p={p*100:5.1f}%  fair {slips.american(1/p):+6d}   "
          f"(the book's own view, de-vigged)")
    print(f"  history p={mp*100:5.1f}%  fair {slips.american(1/mp):+6d}   "
          f"(props at their rate at this line, fights at market)")
    # WHAT EACH LEG IS ACTUALLY BUYING
    print(f"\n{'what each leg adds':46s} {'adds':>8s} {'hits':>7s} "
          f"{'risk':>6s} {'$/risk':>8s}")
    print("-" * 80)
    rows = marginal(tick, hist)
    for lg, added, pr, per in sorted(rows, key=lambda r: -r[3]):
        print(f"{lg['lab'][:46]:46s} {added:+8.0f} {pr*100:6.1f}% "
              f"{(1-pr)*100:5.1f}% {per:8.0f}")
    spread = max(r[3] for r in rows) - min(r[3] for r in rows)
    mid = sorted(r[3] for r in rows)[len(rows) // 2]
    if mid > 0 and spread / mid < 0.25:
        print("  $/risk is flat across the ticket: the book is pricing these "
              "consistently, so\n  moving a leg up or down its ladder buys "
              "frequency with payout at a fixed rate\n  and changes variance, "
              "not value.")
    # And what the ticket looks like with each prop leg taken off, since a leg
    # worth less than the risk it adds should simply not be there.
    for lg in [x for x in tick if x.get("stat")]:
        wo = [x for x in tick if x is not lg]
        dw, aw, _ = parlay(wo)
        print(f"  without {lg['lab'][:38]:38s} {len(wo)} legs {aw:+6d}  "
              f"$33 -> ${33*dw:,.0f}")

    ev = mp * (d - 1) - (1 - mp)
    print(f"\nOn the historical rates this pays {ev*100:+.0f}% of stake. That "
          f"rests entirely on\nthose rates still describing the role each "
          f"player has now -- the table above\nis how you check that, not the "
          f"number.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())

#!/usr/bin/env python3
"""score2.py -- price a posted board with calib.py instead of the old rules.

    python3 score2.py <sweep-file> [--min-edge 0.03]
    python3 score2.py --selftest

The old scorer in nflprops.py ranked on the WEAKER of the player's own hit rate
and the opposing defence's rate at the same number. calib.py's testing says both
halves of that are wrong: the own-rate runs 6-12 points hot at the volumes we
bet, and weighting the defence at face value is worse than ignoring it. So this
reprices a board the way the five-season test says to, and prints what changed.
"""
import bisect, csv, os, re, sys
from collections import defaultdict

import calib

SEASONS = [2022, 2023, 2024, 2025, 2026]
# Tonight's posted numbers, per team: the game total and that team's spread
# (positive = favoured). Set from the board rather than inferred.
# Posted numbers per team for every game on the board. Spread positive =
# favoured. Read off the board, never inferred.
TONIGHT = {("ATL", "total"): 47.5, ("ATL", "spread"): -1.5,
           ("NO", "total"): 47.5, ("NO", "spread"): 1.5,
           ("TB", "total"): 47.5, ("TB", "spread"): -1.5,
           ("DAL", "total"): 47.5, ("DAL", "spread"): 1.5,
           ("PHI", "total"): 44.5, ("PHI", "spread"): 3.5,
           ("JAX", "total"): 44.5, ("JAX", "spread"): -3.5,
           ("SF", "total"): 47.5, ("SF", "spread"): -3.0,
           ("SEA", "total"): 47.5, ("SEA", "spread"): 3.0}
CURRENT = 2026
SPW = os.environ.get("SPW_DIR", ".")
STATS = {
    "receptions": ("targets", ("TE", "WR", "RB")),
    "receiving_yards": ("targets", ("TE", "WR", "RB")),
    "rushing_yards": ("carries", ("RB", "QB")),
    "passing_yards": ("attempts", ("QB",)),
    # COMBINED MARKETS. The weekly file has no column for either, so they are
    # derived onto every row before anything reads them. They were ungraded
    # purely because nothing summed two columns -- 28 lines on a one-game board.
    "rush_reception_yards": ("rush_reception_vol", ("RB", "WR", "TE")),
    "pass_rush_yards": ("pass_rush_vol", ("QB",)),
}
VOL_COLS = ("targets", "carries", "attempts",
            "rush_reception_vol", "pass_rush_vol")
# (derived outcome column, the two columns it adds, the volume column it needs)
DERIVED = {
    "rush_reception_yards": (("rushing_yards", "receiving_yards"),
                             "rush_reception_vol", ("carries", "targets")),
    "pass_rush_yards": (("passing_yards", "rushing_yards"),
                        "pass_rush_vol", ("attempts", "carries")),
}
MK = {
    "player_receptions": "receptions", "player_receptions_alternate": "receptions",
    "player_reception_yds": "receiving_yards",
    "player_reception_yds_alternate": "receiving_yards",
    "player_rush_yds": "rushing_yards", "player_rush_yds_alternate": "rushing_yards",
    "player_pass_yds": "passing_yards", "player_pass_yds_alternate": "passing_yards",
    "player_rush_reception_yds": "rush_reception_yards",
    "player_rush_reception_yds_alternate": "rush_reception_yards",
    "player_pass_rush_yds": "pass_rush_yards",
    "player_pass_rush_yds_alternate": "pass_rush_yards",
}


# A PLAYER WHOSE SHARE OF HIS TEAM'S VOLUME IS MOVING CANNOT BE PROJECTED.
# Measured as |share over his last 3 games - share over the earlier ones|, split
# into terciles over five seasons, the model's Brier score is far worse for the
# shifting third than the stable third:
#
#   receptions 3.5   stable .1057   shifting .1733   (64% worse)
#   receptions 4.5   stable .0750   shifting .1429   (91% worse)
#   rushing 87.5     stable .0626   shifting .0943   (51% worse)
#
# This is the Kamara case made measurable. His six games with Shough are four
# sharing a backfield with Devin Neal and two sharing one with Travis Etienne;
# the projection averages two different roles and the calibration faithfully
# converts the average into a confident number. Ryan spotted it by asking
# whether a different running back had been playing. The gate catches it without
# needing to know who the other back was.
DRIFT_MAX = 0.103     # the shifting tercile starts here

# DID THE PEOPLE AROUND HIM CHANGE? Ryan asked whether Kamara's unders were
# hitting because a different running back had been playing, and the drift gate
# missed it: a back's share of his TEAM's targets is tiny and noisy, so his went
# 4.0 -> 12.5 -> 11.5 -> 4.7 -> 18.8 -> 2.5% and the recent-vs-earlier means
# cancelled to 0.007, comfortably inside the gate.
#
# Measured directly instead: 1 - Jaccard overlap between the top three OTHERS
# taking his position group's volume in his last three games and in the earlier
# ones. Brier by tercile, five seasons:
#
#   receptions 3.5   stable .1247   CHANGED .1585   (+27%)
#   rushing   87.5   stable .0767   CHANGED .0975   (+27%)
#
# It is a weaker signal than drift on its own but it is independent, and the two
# together beat either alone:
#
#   receptions 3.5  ungated .1366  drift .1334  cast .1315  BOTH .1289
#   rushing   87.5  ungated .0809  drift .0745  cast .0769  BOTH .0689
#
# Kamara scores 0.67 on receptions and 0.75 on rushing: his earlier cast is
# Devin Neal alone, his recent one is Neal plus Kendre Miller plus Travis
# Etienne. Both refused.
CAST_MAX = 0.50
CAST_TOP = 3

# ...BUT ONLY FOR A ROTATIONAL PLAYER. Who else is in the room matters when the
# player is one of several and not at all when he is the focal point. Brier for
# a changed cast against a stable one, by his share of the team's volume:
#
#   share of team targets   receptions 3.5   receptions 4.5
#     under 8%                   +17%             +8%
#     8-15%                      +16%            +33%
#     15-22%                      -3%             -2%
#     over 22%                    +3%             +1%
#
# The first version gated everyone and removed Drake London, who takes 31% of
# Atlanta's targets and is the most clearly-defined role on the board. Kamara
# takes about 9% and is exactly who the gate is for.
CAST_SHARE_MAX = 0.15

# RECENT GAMES COUNT FOR MORE. A flat average weighted a 2025 game the same as
# last Sunday's, which is how Tyler Shough projected at 253.9 passing yards while
# throwing 56, 34 and 42 times in 2026 against a 35-per-game career rate, and how
# Chris Olave projected at 91.5 receiving yards off 182, 86 and 107. Both made an
# under look good by averaging away the role each player has now.
#
# Tested as an exponential decay over the prior games, five seasons, by Brier:
#
#   half-life       flat      8      5      3      2
#   receptions 3.5  .1373  .1367  .1366  .1370  .1380
#   rush yds  87.5  .0819  .0813  .0809  .0808  .0808
#   pass yds 249.5  .2266  .2266  .2267  .2259  .2266
#
# Five games is best or near-best everywhere, and the gain is real but small --
# third decimal. It is in because it is free, not because it is large.
HALF_LIFE = 5.0

# THE MODEL HAS NO SKILL ON A MAIN LINE, and this is the measurement that says
# so. Skill = how much of a base-rate guess's error the projection bucket
# removes, by how far the bar sits from the projection:
#
#   distance from projection   receptions 3.5   receptions 4.5   rec yds 84.5
#   within 10%                     +0.8%            -0.1%          -0.3%
#   10-30%                         +5.9%            +7.5%          +2.9%
#   30-60%                        +26.9%           +21.4%          +0.4%
#   >60% away                      +6.6%            +4.4%          +4.8%
#
# Zero inside 10%. A book sets the main line AT the projection on purpose, so
# that is exactly where it posts -110 both ways and exactly where the model
# knows nothing. Every main-line edge I quoted tonight -- Shough under 257.5 at
# 5% away, Olave under 84.5, Bijan under 87.5 -- came out of that dead zone and
# was noise dressed as a number.
#
# Measured systematically across every stat and band rather than hand-set from
# four spot checks -- the hand-set version had receiving yards at 30-60% as a
# dead zone when it is +21%, and receptions beyond 60% at 5% when it is 46%, so
# it was refusing lines the model prices well:
#
#   stat              0-10%   10-30%   30-60%    60%+
#   receptions        +0.9%    +7.5%   +28.8%   +46.1%
#   receiving yards   +0.6%    +4.5%   +21.3%   +32.1%
#   rushing yards     +1.4%    +7.9%   +28.3%   +23.2%
#   passing yards     +4.5%   +19.5%   +42.2%    +8.4%
#   carries           +0.4%   +14.6%   +41.5%    +4.2%
#
# The dead zone is the 0-10% band and only that band -- which is precisely where
# a book posts its main line.
SKILL = {
    # stat, lower and upper bound on |projection - bar| / projection
    ("receptions", 0.10, 0.30): 0.07,
    ("receptions", 0.30, 0.60): 0.29,
    ("receptions", 0.60, 9.99): 0.46,
    ("receiving_yards", 0.10, 0.30): 0.05,
    ("receiving_yards", 0.30, 0.60): 0.21,
    ("receiving_yards", 0.60, 9.99): 0.32,
    ("rushing_yards", 0.10, 0.30): 0.08,
    ("rushing_yards", 0.30, 0.60): 0.28,
    ("rushing_yards", 0.60, 9.99): 0.23,
    ("passing_yards", 0.10, 0.30): 0.20,
    ("passing_yards", 0.30, 0.60): 0.42,
    ("passing_yards", 0.60, 9.99): 0.08,
    ("carries", 0.10, 0.30): 0.15,
    ("carries", 0.30, 0.60): 0.41,
    # THE COMBINED MARKETS. Added with the markets themselves missing from here,
    # which auto-refused every combined line as "no measured skill" -- Kamara's
    # rush+reception and Shough's pass+rush among them. Measured the same way:
    #
    #   rush_reception_yards   0.10-0.30  4.7% (n=13,140)
    #                          0.30-0.60 21.8% (n=18,205)
    #   pass_rush_yards        0.10-0.30 22.2% (n=4,748)
    #                          0.30-0.60 54.6% (n=3,561)
    #
    # A rushing_yards control run through the same code returned 4.7% and 20.8%
    # against the 8% and 28% stored above, so the method agrees in these bands.
    # It returned 63.5% in the 0.60+ band against the stored 23%, because the bar
    # sweep reaches numbers no book would post and an outcome that is nearly
    # certain scores as skill. So the 0.60+ figures from that run are NOT used;
    # each combined stat takes its single-stat counterpart's value instead, which
    # is the conservative choice and is marked as borrowed, not measured.
    ("rush_reception_yards", 0.10, 0.30): 0.05,
    ("rush_reception_yards", 0.30, 0.60): 0.22,
    ("rush_reception_yards", 0.60, 9.99): 0.32,   # borrowed from receiving_yards
    ("pass_rush_yards", 0.10, 0.30): 0.22,
    ("pass_rush_yards", 0.30, 0.60): 0.55,
    ("pass_rush_yards", 0.60, 9.99): 0.08,        # borrowed from passing_yards
}
MIN_SKILL = 0.05      # below this the edge is not reported as an edge

# FOUR PRIOR GAMES WAS COSTING MOST OF THE BOARD IN WEEK 4. Anyone in his first
# season with a team has at most three, so Jahan Dotson, Austin Hooper,
# Zachariah Branch, Noah Fant and Bryce Lance were all refused on tonight's game
# for having joined their clubs this year. Skill by sample size says three is
# nearly as good as four:
#
#   prior games       2-3     4-5     6-9   10-15    16+
#   receptions 3.5  +24.4%  +29.2%  +29.7%  +28.6%  +23.2%
#   rush yds  69.5  +25.0%  +17.9%  +19.2%  +20.8%     --
#
# Three it is. Two is where it starts to thin out and the projection is one
# game's efficiency.
MIN_GAMES = 3


# WHAT AN INJURY REPORT IS WORTH, measured over 2022-2025 on every designated
# skill player with four prior games, against his OWN trailing six-game volume:
#
#   status                 listings  played   play%   volume   production
#   Out                         399       0    0.0%        -            -
#   Doubtful                     25       0    0.0%        -            -
#   Questionable                328     196   59.8%    95.1%       102.5%
#   on the report, no status     904     783   86.6%   103.2%       107.2%
#
# Out and Doubtful are absolute: 0 of 424. Those lines are refused.
#
# Questionable is a coin flip on him taking the field, and the practice column
# does not break it open -- Limited 61.2% (n=209), Full 58.2% (n=67), DNP 51.2%
# (n=43). But CONDITIONAL ON PLAYING he is himself: 98.5% of his usual volume
# and 111.3% of his usual production on the Limited line. So the cost of
# Questionable is not a worse player, it is a 40% chance of no game at all.
# That does not make the price wrong, so it is not refused -- it is flagged, and
# the board may not print it without the flag.
GONE = ("out", "doubtful")


def avail(status):
    """(ok, flag). Reads a report_status as the data says to read it."""
    st = (status or "").strip().lower()
    if st in GONE:
        return False, None
    if st == "questionable":
        return True, "QUESTIONABLE -- played 60% of the time (n=328)"
    return True, None


def gate(stat, proj, bar, starter, qb_games_n, dr, cc, share=None,
         status=None):
    """(ok, reason). The whole admission chain in one testable place.

    It lives out here because the last three times I put a rule inside main() --
    `spec in COMPARE`, the history-unavailable line, and these gates -- the
    selftest could not reach it and the rule shipped broken. main() reads files;
    a rule that only runs there is a rule nothing checks."""
    ok, flag = avail(status)
    if not ok:
        return False, f"listed {status.strip().lower()} (0 of 424 such players played)"
    if starter is None:
        return False, "no identified starter"
    if qb_games_n is None or qb_games_n < MIN_GAMES:
        return False, f"under {MIN_GAMES} games with {starter}"
    if dr is None:
        return False, "role drift unmeasurable"
    if dr > DRIFT_MAX:
        return False, f"role shifting (share moved {dr:.3f})"
    # The cast check applies only to a rotational player; above CAST_SHARE_MAX
    # he is the focal point and the turnover around him does not predict error.
    if share is None or share < CAST_SHARE_MAX:
        if cc is None:
            return False, "cast change unmeasurable"
        if cc > CAST_MAX:
            return False, (f"rotational player ({share*100:.0f}% share) and the "
                           f"players around him changed (turnover {cc:.2f})"
                           if share is not None else
                           f"the players around him changed (turnover {cc:.2f})")
    sk = skill_of(stat, proj, bar)
    if sk < MIN_SKILL:
        d = abs(proj - bar) / proj * 100 if proj else 0.0
        return False, f"no measured skill at {d:.0f}% from the projection"
    return True, sk


def skill_of(stat, proj, bar):
    """The measured skill for a line this far from its projection, or 0.0."""
    if proj <= 0:
        return 0.0
    d = abs(proj - bar) / proj
    for (st, lo, hi), v in SKILL.items():
        if st == stat and lo <= d < hi:
            return v
    return 0.0


# THE BOOK AND THE STATS SPELL NAMES DIFFERENTLY. FanDuel posts "Brian Robinson
# Jr." and "Kyle Pitts Sr."; nflverse has "Brian Robinson" and "Kyle Pitts". The
# first version matched on the exact string, found nothing for Robinson, resolved
# his team to None and refused every line he had -- for a back with 30 carries
# this season. Suffixes are stripped from both sides before matching.
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)


def norm_name(n):
    return SUFFIX.sub("", (n or "").strip()).lower()


def _f(v):
    try:
        return float(v) if v not in (None, "", "NA") else 0.0
    except (TypeError, ValueError):
        return 0.0


def load():
    rows = []
    for y in SEASONS:
        p = os.path.join(SPW, f"spw{y}.csv")
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("season_type") or "REG") == "REG":
                    rows.append((y, r))
    derive(rows)
    return rows


def derive(rows):
    """Add the combined outcome and volume columns the file does not carry.

    Written as strings because every reader downstream goes through
    _f(r.get(col)) and must not need to know which columns are real."""
    for _y, r in rows:
        for stat, (parts, volcol, volparts) in DERIVED.items():
            r[stat] = str(sum(_f(r.get(c)) for c in parts))
            r[volcol] = str(sum(_f(r.get(c)) for c in volparts))
    return rows


TOT, SPD, TEAM = {}, {}, {}


def build(rows, stat):
    """Out-of-sample rows: (player, projection, volume, outcome, opp, pos,
    season, game total, team spread)."""
    volcol, pos = STATS[stat]
    by = defaultdict(list)
    for y, r in rows:
        if (r.get("position") or "") not in pos:
            continue
        by[(y, norm_name(r.get("player_display_name")))].append(
            (int(r.get("week") or 0), _f(r.get(volcol)), _f(r.get(stat)),
             r.get("opponent_team"), r.get("position")))
    out = []
    for (y, who), v in by.items():
        v.sort()
        if len(v) < 5:
            continue
        for i in range(4, len(v)):
            pr = v[:i]
            vol = sum(x[1] for x in pr) / len(pr)
            rt = sum(x[2] for x in pr) / max(1e-9, sum(x[1] for x in pr))
            tm = TEAM.get((y, who))
            k = (str(y), str(v[i][0]), tm)
            out.append((who, vol * rt, vol, v[i][2], v[i][3], v[i][4], y,
                        TOT.get(k), SPD.get(k)))
    return out


def injuries(path="inj26b.csv", week=None):
    """norm_name -> (report_status, injury) for the latest week on file.

    Only the latest week: an "Out" from week 1 says nothing about tonight, and
    carrying it forward would refuse healthy players all season."""
    rep = {}
    if not os.path.exists(path):
        return rep
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("season_type") or "REG") != "REG":
                continue
            if int(r.get("season") or 0) != CURRENT:
                continue
            rows.append(r)
    if not rows:
        return rep
    wk = week if week is not None else max(int(r.get("week") or 0) for r in rows)
    for r in rows:
        if int(r.get("week") or 0) != wk:
            continue
        rep[norm_name(r.get("full_name"))] = (
            (r.get("report_status") or "").strip(),
            (r.get("report_primary_injury") or "").strip())
    return rep


def schedule(path="sched26b.csv"):
    """(season, week, team) -> (game total, that team's spread). The spread is
    positive when the team is favoured, which is the sign the rushing effect
    runs with."""
    tot, spd = {}, {}
    if not os.path.exists(path):
        return tot, spd
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            y, w = r.get("season"), r.get("week")
            try:
                t = float(r.get("total_line") or 0)
                sl = float(r.get("spread_line") or 0)
            except ValueError:
                continue
            if not t:
                continue
            tot[(y, w, r.get("home_team"))] = t
            tot[(y, w, r.get("away_team"))] = t
            spd[(y, w, r.get("home_team"))] = sl
            spd[(y, w, r.get("away_team"))] = -sl
    return tot, spd


def team_volume(rows):
    """(season, week, team, volume column) -> the team's total."""
    tt = defaultdict(float)
    for y, r in rows:
        tm = r.get("team") or r.get("recent_team")
        w = int(r.get("week") or 0)
        for col in VOL_COLS:
            tt[(y, w, tm, col)] += _f(r.get(col))
    return tt


def position_cast(rows):
    """(season, week, team, position, volume column) -> [(volume, player), ...]."""
    c = defaultdict(list)
    for y, r in rows:
        tm = r.get("team") or r.get("recent_team")
        w = int(r.get("week") or 0)
        pos = r.get("position") or ""
        for col in VOL_COLS:
            v = _f(r.get(col))
            if v > 0:
                c[(y, w, tm, pos, col)].append((v, r.get("player_display_name")))
    return c


def cast_change(rows, who, stat, cst, qb_games=None):
    """How much the position group's personnel around him has turned over."""
    volcol, _ = STATS[stat]
    key = norm_name(who)
    hist = [(y, r) for y, r in rows
            if norm_name(r.get("player_display_name")) == key]
    if not hist:
        return None
    hist.sort(key=lambda t: (t[0], int(t[1].get("week") or 0)))
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, int(r.get("week") or 0), r.get("position") or "") for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < MIN_GAMES:
        return None
    sel.sort()

    def others(games):
        s = set()
        for y, w, pos in games:
            top = sorted(cst.get((y, w, tm, pos, volcol), []), reverse=True)
            s |= {nm for _v, nm in top[:CAST_TOP]} - {who}
        return s

    a, b = others(sel[-3:]), others(sel[:-3] or sel)
    if not (a | b):
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def share_of(rows, who, stat, tt, qb_games=None):
    """His average share of the team's volume over the games used."""
    volcol, _ = STATS[stat]
    key = norm_name(who)
    hist = [(y, r) for y, r in rows
            if norm_name(r.get("player_display_name")) == key]
    if not hist:
        return None
    hist.sort(key=lambda t: (t[0], int(t[1].get("week") or 0)))
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, int(r.get("week") or 0), r) for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if not sel:
        return None
    vals = []
    for y, w, r in sel:
        den = tt.get((y, w, tm, volcol), 0.0)
        if den > 0:
            vals.append(_f(r.get(volcol)) / den)
    return sum(vals) / len(vals) if vals else None


def drift(rows, who, stat, tt, qb_games=None):
    """How much his share of the team's volume has moved. None if unmeasurable."""
    volcol, _ = STATS[stat]
    key = norm_name(who)
    hist = [(y, r) for y, r in rows
            if norm_name(r.get("player_display_name")) == key]
    if not hist:
        return None
    hist.sort(key=lambda t: (t[0], int(t[1].get("week") or 0)))
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, int(r.get("week") or 0), r) for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < MIN_GAMES:
        return None
    sel.sort()
    shares = []
    for y, w, r in sel:
        den = tt.get((y, w, tm, volcol), 0.0)
        shares.append(_f(r.get(volcol)) / den if den > 0 else 0.0)
    recent, early = shares[-3:], (shares[:-3] or shares)
    return abs(sum(recent) / len(recent) - sum(early) / len(early))


def project(rows, who, stat, qb_games=None):
    """Trailing volume x efficiency, on THIS team, optionally only the games a
    given quarterback started -- the split that turned London's 2.7 targets a
    game into 10.4 and made every Atlanta number tonight wrong."""
    volcol, _ = STATS[stat]
    key = norm_name(who)
    hist = [(y, r) for y, r in rows
            if norm_name(r.get("player_display_name")) == key]
    if not hist:
        return None
    # his LATEST game decides the team, so sort before taking the last one --
    # file order is not chronological across seasons.
    hist.sort(key=lambda t: (t[0], int(t[1].get("week") or 0)))
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, r) for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < MIN_GAMES:
        return None
    sel.sort(key=lambda t: (t[0], int(t[1].get("week") or 0)))
    w = [0.5 ** ((len(sel) - 1 - j) / HALF_LIFE) for j in range(len(sel))]
    sw = sum(w)
    vol = sum(_f(r.get(volcol)) * wt for (_y, r), wt in zip(sel, w)) / sw
    tv = sum(_f(r.get(volcol)) * wt for (_y, r), wt in zip(sel, w))
    ts = sum(_f(r.get(stat)) * wt for (_y, r), wt in zip(sel, w))
    rate = ts / max(1e-9, tv)
    pos = (sel[-1][1].get("position") or "").upper()
    return vol * rate, vol, len(sel), tm, pos


NFLPROPS_STAT = {"rush yds": "rushing_yards", "rec yds": "receiving_yards",
                 "receptions": "receptions", "pass yds": "passing_yards"}


def parse_nflprops(path):
    """The board nflprops.py prints, which covers every game in the horizon
    rather than the one game a sweep targets. One line per candidate:

      Brock Purdy  Over  19.5 rush yds  -102  all 7/13= 54% ...
    """
    out = []
    pat = re.compile(
        r"^  (\S.{0,21}?)\s{2,}(Over|Under)\s+([\d.]+)\s+"
        r"(rush yds|rec yds|receptions|pass yds)\s+(-?\d+)\s")
    for line in open(path, encoding="utf-8"):
        m = pat.match(line)
        if not m:
            continue
        who, side, bar, lab, price = m.groups()
        out.append((NFLPROPS_STAT[lab], who.strip(), side, float(bar),
                    int(price), ""))
    return out


def parse_env(path):
    """`# env <team> spread <x>` and `# env <team> total <x>` lines a board dump
    writes. Replaces a hardcoded table that had to be edited per slate and was
    silently wrong for every game it had not been updated for."""
    out = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^# env (\S+) (spread|total) ([-+]?[\d.]+)\s*$", line)
        if m:
            out[(m.group(1), m.group(2))] = float(m.group(3))
    return out


def parse(path):
    """(stat, player, side, bar, price, game). The game comes from the
    `# game <away> @ <home>` header a board dump writes -- without it the output
    lists lines from four different fixtures with no way to tell which."""
    cur, out, game = None, [], ""
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^# game (.+?)\s*$", line)
        if m:
            game = m.group(1); continue
        # a single-game sweep heads its file with "Away @ Home   <kickoff>"
        # instead of a # game line, and without this the game column reads "?"
        m = re.match(r"^(\w[\w .'-]+ @ \w[\w .'-]+?)\s{2,}\d{4}-\d\d-\d\d", line)
        if m and not game:
            game = m.group(1).strip(); continue
        m = re.match(r"^  ([a-z0-9_]+)  \(\d+\)\s*$", line)
        if m:
            cur = m.group(1); continue
        m = re.match(r"^      (.{20}) (.{22})\s*([-\d.]*)\s*([+-]\d+)\s+[\d.]+%\s*$", line)
        if m and cur in MK:
            d, n, pt, pr = (m.group(1).strip(), m.group(2).strip(),
                            m.group(3).strip(), int(m.group(4)))
            if not d or not pt:
                continue
            side = ("Over" if n.startswith("Over")
                    else "Under" if n.startswith("Under") else None)
            if side:
                out.append((MK[cur], d, side, float(pt), pr, game))
    return out


def imp(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def money(price, p, stake=10.0):
    """(profit if it wins, expected profit) on `stake`.

    One function, used by both the board and its test. The test used to carry
    its own copy of the formula, which meant breaking the real one changed
    nothing -- a duplicated calculation is an untested calculation."""
    win = stake * price / 100.0 if price > 0 else stake * 100.0 / -price
    return win, p * win - (1 - p) * stake


def selftest():
    f = 0

    def ck(c, m):
        nonlocal f
        if not c:
            print(f"  FAIL {m}"); f += 1

    ck(abs(imp(-110) - 0.5238) < 1e-3, "imp")
    # the money columns: profit on a win, and expected profit per $10 staked
    w, r = money(100, 0.50)
    ck(abs(w - 10.0) < 1e-9 and abs(r) < 1e-9,
       f"even money at 50% returns nothing: {w} {r}")
    w, r = money(-200, 0.75)
    ck(abs(w - 5.0) < 1e-9 and abs(r - 1.25) < 1e-9,
       f"-200 at 75%: wins $5, expects +$1.25, got {w} {r}")
    w, r = money(300, 0.20)
    ck(abs(w - 30.0) < 1e-9 and abs(r - (-2.0)) < 1e-9,
       f"+300 at 20% loses money: {w} {r}")
    w, r = money(-113, 0.652)
    ck(r > 0, f"a +12-point edge must show a positive return: {r}")
    # the skill gate: a main line must score zero, an alt rung in the measured
    # band must score the band's value
    ck(skill_of("receptions", 7.2, 7.0) == 0.0,
       f"a bar at the projection has no skill: {skill_of('receptions',7.2,7.0)}")
    ck(skill_of("receptions", 7.2, 4.5) == 0.29,
       f"38% away is the 30-60% band: {skill_of('receptions',7.2,4.5)}")
    # 6.5 is only 9.7% from 7.2, which is the DEAD ZONE, not the 10-30% band --
    # worth pinning, because that is the rung a book posts as the main line.
    ck(skill_of("receptions", 7.2, 6.5) == 0.0,
       f"9.7% away is still the dead zone: {skill_of('receptions',7.2,6.5)}")
    ck(skill_of("receptions", 7.2, 6.0) == 0.07,
       f"17% away is the 10-30% band: {skill_of('receptions',7.2,6.0)}")
    ck(skill_of("receiving_yards", 114.6, 84.5) == 0.05,
       f"receiving yards at 26% away is the 10-30% band: "
       f"{skill_of('receiving_yards',114.6,84.5)}")
    ck(skill_of("receiving_yards", 114.6, 39.5) == 0.32,
       f"66% away is the far band: {skill_of('receiving_yards',114.6,39.5)}")
    ck(skill_of("receptions", 0.0, 4.5) == 0.0, "a zero projection is no skill")
    # name normalisation: the book's suffixes must not hide a player's history
    ck(norm_name("Brian Robinson Jr.") == norm_name("Brian Robinson"),
       "Jr. must not split a player in two")
    ck(norm_name("Kyle Pitts Sr.") == norm_name("Kyle Pitts"), "Sr. likewise")
    ck(norm_name("Odell Beckham Jr") == norm_name("Odell Beckham"), "no full stop")
    ck(norm_name("Robert Griffin III") == norm_name("Robert Griffin"), "numerals")
    ck(norm_name("Drake London") != norm_name("Drake Londonn"),
       "it must not collapse different players")
    ck(norm_name(None) == "", "a missing name is empty, not a crash")
    # a player whose only games are with the current starter must still price
    fake = [(2026, {"player_display_name": "New Guy Jr.", "position": "WR",
                    "team": "ATL", "week": str(w), "targets": "6",
                    "receptions": "4", "receiving_yards": "50",
                    "season_type": "REG", "opponent_team": "NO"})
            for w in (1, 2, 3)]
    pj = project(fake, "New Guy", "receptions")
    ck(pj is not None and pj[2] == 3,
       f"three games must be enough, and the suffix must not matter: {pj}")
    # cast_change: a stable room scores 0, a fully replaced one scores 1
    def mk(who, week, mates):
        return [(2026, {"player_display_name": n, "position": "RB", "team": "NO",
                        "week": str(week), "targets": str(v), "carries": str(v),
                        "receptions": "1", "rushing_yards": "10",
                        "receiving_yards": "10", "season_type": "REG",
                        "opponent_team": "ATL"})
                for n, v in [(who, 5)] + mates]
    stable = []
    for w in (1, 2, 3, 4, 5, 6):
        stable += mk("K", w, [("Neal", 4)])
    cs = position_cast(stable)
    ck(cast_change(stable, "K", "receptions", cs) == 0.0,
       f"an unchanged room is 0: {cast_change(stable,'K','receptions',cs)}")
    swapped = []
    for w in (1, 2, 3):
        swapped += mk("K", w, [("Neal", 4)])
    for w in (4, 5, 6):
        swapped += mk("K", w, [("Etienne", 4)])
    cs2 = position_cast(swapped)
    v = cast_change(swapped, "K", "receptions", cs2)
    ck(v == 1.0,
       f"a fully replaced room is 1.0 exactly -- 0.67 means the player himself "
       f"is being counted as his own competition: {v}")
    ck(cast_change(swapped, "Nobody", "receptions", cs2) is None, "absent player")

    # gate(): every refusal reachable, in the order they fire
    ok, why = gate("receptions", 7.2, 4.5, None, 10, 0.01, 0.0)
    ck(not ok and "starter" in why, f"no starter: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 2, 0.01, 0.0)
    ck(not ok and f"under {MIN_GAMES} games" in why, f"thin QB sample: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", MIN_GAMES, 0.01, 0.0)
    ck(ok, f"exactly the minimum must pass: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, None, 0.0)
    ck(not ok and "unmeasurable" in why, f"drift unmeasurable: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.25, 0.0)
    ck(not ok and "shifting" in why, f"drift too high: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, None)
    ck(not ok and "unmeasurable" in why, f"cast unmeasurable: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.75, share=0.09)
    ck(not ok and "around him changed" in why,
       f"a rotational player with a changed cast is refused: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.75, share=0.31)
    ck(ok, f"a 31%-share focal player must NOT be gated on cast: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, None, share=0.31)
    ck(ok, "a focal player needs no cast measurement at all")
    # the combined markets. The file has no column for either; they are derived.
    row = {"carries": "10", "targets": "4", "rushing_yards": "50",
           "receiving_yards": "30", "attempts": "25", "passing_yards": "240",
           "position": "RB", "player_display_name": "Combo Guy", "team": "NO",
           "week": "1", "season_type": "REG"}
    derive([(2026, row)])
    ck(row["rush_reception_yards"] == "80.0",
       f"rush+rec yards must SUM, not pick one: {row['rush_reception_yards']}")
    ck(row["rush_reception_vol"] == "14.0",
       f"and so must its volume, carries plus targets: {row['rush_reception_vol']}")
    ck(row["pass_rush_yards"] == "290.0",
       f"pass+rush yards: {row['pass_rush_yards']}")
    ck(row["pass_rush_vol"] == "35.0",
       f"attempts plus carries: {row['pass_rush_vol']}")
    empty = {"position": "WR", "season_type": "REG"}
    derive([(2026, empty)])
    ck(empty["rush_reception_yards"] == "0.0",
       f"missing columns are zero, not a crash: {empty}")
    for st in ("rush_reception_yards", "pass_rush_yards"):
        ck(st in STATS, f"{st} must be a gradeable stat")
        ck(STATS[st][0] in VOL_COLS,
           f"{st}'s volume column must be one team_volume actually sums, or "
           f"every share is zero and every line is refused: {STATS[st][0]}")
    ck(MK.get("player_rush_reception_yds") == "rush_reception_yards"
       and MK.get("player_pass_rush_yds") == "pass_rush_yards",
       "the board's market names must map to them")
    # a derived stat must flow all the way through team_volume and share
    combo = []
    for w in (1, 2, 3, 4, 5):
        combo.append((2026, dict(row, week=str(w))))
        combo.append((2026, {"player_display_name": "Other", "position": "RB",
                             "team": "NO", "week": str(w), "carries": "10",
                             "targets": "4", "rushing_yards": "40",
                             "receiving_yards": "10", "season_type": "REG"}))
    derive(combo)
    tv = team_volume(combo)
    ck(tv[(2026, 1, "NO", "rush_reception_vol")] == 28.0,
       f"the team's combined volume must sum both players: "
       f"{tv.get((2026, 1, 'NO', 'rush_reception_vol'))}")
    sh = share_of(combo, "Combo Guy", "rush_reception_yards", tv)
    ck(sh is not None and abs(sh - 0.5) < 1e-9,
       f"and his share of it must come out at a half: {sh}")
    pj = project(combo, "Combo Guy", "rush_reception_yards")
    ck(pj is not None and abs(pj[0] - 80.0) < 1e-6,
       f"the projection must be the combined 80, not either half: {pj}")
    # ...and load() must actually CALL it. Testing derive() directly left the
    # call site inside load() untested: removing it caught nothing.
    import tempfile as _t2
    sd = _t2.mkdtemp()
    with open(os.path.join(sd, "spw2026.csv"), "w") as fh:
        fh.write("season_type,position,player_display_name,team,week,carries,"
                 "targets,rushing_yards,receiving_yards,attempts,passing_yards\n")
        fh.write("REG,RB,Loaded Guy,NO,1,10,4,50,30,0,0\n")
    _old_spw = globals()["SPW"]
    globals()["SPW"] = sd
    try:
        lrows = load()
    finally:
        globals()["SPW"] = _old_spw
    ck(len(lrows) == 1, f"one row loaded: {lrows}")
    ck(lrows[0][1].get("rush_reception_yards") == "80.0",
       f"load() must derive the combined columns, not just define them: "
       f"{lrows[0][1].get('rush_reception_yards')}")
    ck(lrows[0][1].get("pass_rush_vol") == "10.0",
       f"both of them: {lrows[0][1].get('pass_rush_vol')}")
    os.unlink(os.path.join(sd, "spw2026.csv")); os.rmdir(sd)
    # the injury report. Out and Doubtful never played (0 of 424); Questionable
    # played 59.8% of 328 listings, so it is flagged and priced, not refused.
    ck(avail("Out") == (False, None), "Out is out")
    ck(avail("out")[0] is False, "and the file's casing must not matter")
    ck(avail("Doubtful") == (False, None), "Doubtful never played either")
    ck(avail("Questionable")[0] is True,
       "Questionable must still be PRICED -- 60% of them played")
    ck(avail("Questionable")[1] is not None,
       "but it must never reach the board unflagged")
    ck(avail("") == (True, None) and avail(None) == (True, None),
       "no designation is no flag")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.0, share=0.31,
                   status="Out")
    ck(not ok and "out" in why.lower(),
       f"an Out player is refused before anything else is measured: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.0, share=0.31,
                   status="Doubtful")
    ck(not ok and "doubtful" in why.lower(), f"so is Doubtful: {why}")
    # ...and refused EVEN WHEN every other measurement is missing, because the
    # reason has to name the injury, not a data gap
    ok, why = gate("receptions", 7.2, 4.5, None, None, None, None, status="Out")
    ck(not ok and "out" in why.lower(),
       f"the reason must be the injury, not the missing starter: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.0, share=0.31,
                   status="Questionable")
    ck(ok, f"Questionable must pass the gate: {why}")
    # the loader takes the LATEST week only
    import tempfile as _tf
    fd, ip = _tf.mkstemp(suffix=".csv")
    os.write(fd, (b"season,season_type,week,team,position,full_name,"
                  b"report_primary_injury,report_status\n"
                  b"2026,REG,1,NO,TE,Healed Guy,Ankle,Out\n"
                  b"2026,REG,4,NO,TE,Noah Fant,Abdomen,Questionable\n"
                  b"2025,REG,4,NO,TE,Last Year,Knee,Out\n"))
    os.close(fd)
    rep = injuries(ip)
    ck(norm_name("Noah Fant") in rep, f"the latest week must be read: {rep}")
    ck(norm_name("Healed Guy") not in rep,
       f"a week-1 Out must NOT follow a player all season: {rep}")
    ck(norm_name("Last Year") not in rep,
       f"and last season's report is not this week's: {rep}")
    ck(rep[norm_name("Noah Fant")] == ("Questionable", "Abdomen"),
       f"status and injury both: {rep}")
    os.unlink(ip)
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, None, share=0.09)
    ck(not ok and "unmeasurable" in why, f"a rotational player does: {why}")
    ok, why = gate("receptions", 7.2, 7.0, "QB", 10, 0.01, 0.0)
    ck(not ok and "no measured skill" in why, f"dead zone: {why}")
    ok, why = gate("receptions", 7.2, 4.5, "QB", 10, 0.01, 0.0)
    ck(ok and why == 0.29, f"a clean line passes and returns its skill: {ok} {why}")
    # a DIFFERENT band must return a DIFFERENT skill -- otherwise the pass
    # branch could be returning a constant and every line would read 25%.
    ok2, why2 = gate("receptions", 7.2, 6.0, "QB", 10, 0.01, 0.0)
    ck(ok2 and why2 == 0.07,
       f"the 10-30% band must return 0.07, not a constant: {why2}")
    # passing yards peak in the middle band and fall off far out -- the shape
    # differs by stat, which a single constant could not express
    ck(skill_of("passing_yards", 300.0, 180.0) == 0.42, "passing 40% away")
    ck(skill_of("passing_yards", 300.0, 100.0) == 0.08, "passing 67% away is weak")
    ok3, why3 = gate("receiving_yards", 114.6, 39.5, "QB", 10, 0.01, 0.0)
    ck(ok3 and why3 == 0.32, f"receiving yards far out returns 0.32: {why3}")
    # the dead zone is the 0-10% band and ONLY that band
    for st in ("receptions", "receiving_yards", "rushing_yards", "carries"):
        ck(skill_of(st, 100.0, 95.0) == 0.0, f"{st} at 5% away is dead")
        ck(skill_of(st, 100.0, 80.0) > 0.0, f"{st} at 20% away is not dead")
    # parse: a market key we do not map must be ignored, a mapped one kept
    import tempfile
    txt = ("  player_receptions  (2)\n"
           "      Juwan Johnson        Over                       3.5   -160  61.5%\n"
           "      Juwan Johnson        Under                      3.5   +118  45.9%\n"
           "  player_sacks  (1)\n"
           "      Chase Young          Over                       0.5   -114  53.3%\n")
    p = tempfile.mktemp(suffix=".txt")
    open(p, "w").write(txt)
    rows = parse(p)
    ck(len(rows) == 2, f"only mapped markets parsed, got {rows}")
    ck(all(len(r) == 6 for r in rows), f"every row carries a game slot: {rows}")
    ck(rows[0][2] == "Over" and rows[1][2] == "Under", "both sides parsed")
    ck(all(r[0] == "receptions" for r in rows), "market mapped to the nflverse stat")
    os.unlink(p)
    # the nflprops format, which covers every game rather than one
    txt2 = ("  Brock Purdy            Over    19.5 rush yds        -102  all  7/13= 54%\n"
            "  Drake London           Under    5.5 receptions       106  all  8/15= 53%\n"
            "  George Kittle          Under    4.5 receptions       104  all  8/15= 53%\n"
            "  not a candidate line at all\n")
    p2 = tempfile.mktemp(suffix=".txt")
    open(p2, "w").write(txt2)
    # the env lines a board dump writes
    p3 = tempfile.mktemp(suffix=".txt")
    open(p3, "w").write("# game A @ B\n# env ATL spread -1.5\n"
                        "# env NO total 47.5\nnot an env line\n")
    e3 = parse_env(p3)
    ck(e3 == {("ATL", "spread"): -1.5, ("NO", "total"): 47.5},
       f"env parsed: {e3}")
    ck(parse_env(p2) == {}, "a board with no env lines yields nothing")
    os.unlink(p3)
    # the game header must attach to the lines that follow it
    p4 = tempfile.mktemp(suffix=".txt")
    open(p4, "w").write(
        "# game Atlanta Falcons @ New Orleans Saints\n"
        "  player_receptions  (1)\n"
        "      Drake London         Over                      5.5   -140  0.0%\n"
        "# game Tampa Bay Buccaneers @ Dallas Cowboys\n"
        "  player_receptions  (1)\n"
        "      CeeDee Lamb          Over                      6.5   +116  0.0%\n")
    # a sweep's own header line must also be recognised as the game
    p5 = tempfile.mktemp(suffix=".txt")
    open(p5, "w").write(
        "Atlanta Falcons @ New Orleans Saints   2026-10-06T00:15:00Z\n\n"
        "  player_receptions  (1)\n"
        "      Drake London         Over                      5.5   -140  0.0%\n")
    r5 = parse(p5)
    ck(len(r5) == 1 and r5[0][5] == "Atlanta Falcons @ New Orleans Saints",
       f"a sweep header must name the game, not leave it blank: {r5}")
    os.unlink(p5)
    # the team must come from his LATEST game, and file order is not
    # chronological: a 2025 row for an old club can sit after a 2026 row.
    jumbled = [
        (2026, {"player_display_name": "Mover", "position": "WR", "team": "NEW",
                "week": "3", "targets": "8", "receptions": "6",
                "receiving_yards": "70", "season_type": "REG",
                "opponent_team": "X"}),
        (2026, {"player_display_name": "Mover", "position": "WR", "team": "NEW",
                "week": "2", "targets": "7", "receptions": "5",
                "receiving_yards": "60", "season_type": "REG",
                "opponent_team": "X"}),
        (2026, {"player_display_name": "Mover", "position": "WR", "team": "NEW",
                "week": "1", "targets": "9", "receptions": "7",
                "receiving_yards": "80", "season_type": "REG",
                "opponent_team": "X"}),
    ] + [
        (2025, {"player_display_name": "Mover", "position": "WR", "team": "OLD",
                "week": str(w), "targets": "1", "receptions": "0",
                "receiving_yards": "0", "season_type": "REG",
                "opponent_team": "X"}) for w in (1, 2, 3, 4, 5)
    ]
    pm = project(jumbled, "Mover", "receptions")
    ck(pm is not None and pm[3] == "NEW",
       f"the team must be his latest, not whatever sorted last in the file: "
       f"{pm[3] if pm else None}")
    ck(pm is not None and pm[2] == 3,
       f"and only the NEW-team games count: {pm[2] if pm else None}")
    r4 = parse(p4)
    ck(len(r4) == 2, f"two rows: {r4}")
    ck(r4[0][5] == "Atlanta Falcons @ New Orleans Saints", f"first game: {r4[0]}")
    ck(r4[1][5] == "Tampa Bay Buccaneers @ Dallas Cowboys",
       f"the header must switch, not stick: {r4[1]}")
    os.unlink(p4)
    r2 = parse_nflprops(p2)
    ck(len(r2) == 3, f"three candidates parsed, got {len(r2)}: {r2}")
    ck(all(len(r) == 6 for r in r2), "the nflprops parser matches the shape")
    ck(r2[0] == ("rushing_yards", "Brock Purdy", "Over", 19.5, -102, ""),
       f"first row, with an empty game slot: {r2[0]}")
    ck(r2[1][2] == "Under" and r2[1][4] == 106, f"a plus price on Under: {r2[1]}")
    ck(r2[2][1] == "George Kittle", f"a two-word surname: {r2[2]}")
    os.unlink(p2)
    # project: the QB filter must actually narrow the sample
    fake = [(2026, {"player_display_name": "X", "position": "WR", "team": "ATL",
                    "week": str(w), "targets": "10" if w == 3 else "2",
                    "receptions": "8" if w == 3 else "1",
                    "season_type": "REG", "opponent_team": "NO"})
            for w in (1, 2, 3, 4, 5)]
    a = project(fake, "X", "receptions")
    b = project(fake, "X", "receptions", qb_games={(2026, 3)})
    ck(a is not None and b is None, f"a 1-game QB split must refuse: {b}")
    b2 = project(fake, "X", "receptions", qb_games={(2026, w) for w in (1, 2, 3, 4)})
    ck(b2 is not None and b2[1] != a[1], f"QB filter must change volume: {b2} vs {a}")
    # recency: a player whose last game spiked must project ABOVE his flat mean
    rising = [(2026, {"player_display_name": "R", "position": "WR", "team": "ATL",
                      "week": str(w), "targets": str(2 + 2 * w),
                      "receptions": str(1 + w), "season_type": "REG",
                      "opponent_team": "NO"})
              for w in (1, 2, 3, 4, 5, 6)]
    pr = project(rising, "R", "receptions")
    flat = sum(1 + w for w in (1, 2, 3, 4, 5, 6)) / 6
    ck(pr is not None and pr[0] > flat,
       f"a rising role must project above the flat mean: {pr[0]:.2f} vs {flat:.2f}")
    falling = [(2026, {"player_display_name": "F", "position": "WR", "team": "ATL",
                       "week": str(w), "targets": str(14 - 2 * w),
                       "receptions": str(7 - w), "season_type": "REG",
                       "opponent_team": "NO"})
               for w in (1, 2, 3, 4, 5, 6)]
    pf = project(falling, "F", "receptions")
    flat2 = sum(7 - w for w in (1, 2, 3, 4, 5, 6)) / 6
    ck(pf is not None and pf[0] < flat2,
       f"a falling role must project below the flat mean: {pf[0]:.2f} vs {flat2:.2f}")
    print("score2 selftest:", "ok" if f == 0 else f"{f} FAILURES")
    return 1 if f else 0


def main(path, min_edge=0.03, only=None):
    """only: substring of the game to keep. A board that spans four fixtures and
    does not let you ask for one of them is a board you cannot bet from -- Ryan
    had to tell me that Tuten plays Sunday."""
    rows = load()
    if not rows:
        print(f"no spw*.csv found in {SPW}"); return 1
    print(f"{len(rows)} player-weeks loaded from {SPW}\n")
    # which weeks each starting QB played, so a team's skill players are
    # projected off the games their actual starter played
    qbs = defaultdict(set)
    for y, r in rows:
        if (r.get("position") or "") == "QB" and _f(r.get("attempts")) >= 10:
            tm = r.get("team") or r.get("recent_team")
            qbs[(tm, r.get("player_display_name"))].add((y, int(r.get("week") or 0)))
    starter = {}
    for (tm, who), gs in qbs.items():
        cur = [w for (yy, w) in gs if yy == CURRENT]
        if not cur:
            continue
        if tm not in starter or max(cur) > starter[tm][1]:
            starter[tm] = (who, max(cur), gs)
    global TOT, SPD, TEAM
    TOT, SPD = schedule()
    hurt = injuries()
    print(f"injury report: {len(hurt)} players listed this week\n")
    for y, r in rows:
        TEAM[(y, r.get("player_display_name"))] = (r.get("team")
                                                   or r.get("recent_team"))
    print(f"schedule: {len(TOT)} team-games with a posted total\n")
    tt = team_volume(rows)
    cst = position_cast(rows)
    models, biases, defs, envs = {}, {}, {}, {}
    for stat in STATS:
        rs = build(rows, stat)
        if len(rs) < 500:
            continue
        m = calib.Model(rs)
        models[stat] = m
        defs[stat] = {}
    env_posted = parse_env(path)
    if env_posted:
        TONIGHT.update(env_posted)
        print(f"read {len(env_posted)} posted environment values from the board")
    board = parse(path)
    if only:
        print(f"filtered to games matching {only!r}")
    if not board:
        board = parse_nflprops(path)
        if board:
            print("(read as an nflprops board rather than a sweep)")
    print(f"{len(board)} outcomes parsed\n")
    want = defaultdict(set)
    for stat, who, side, bar, price, _gm in board:
        want[stat].add(bar)
    for stat in models:
        biases[stat] = {bar: models[stat].bias(stat, bar) for bar in sorted(want[stat])}
        defs[stat] = {bar: models[stat].defence(bar) for bar in sorted(want[stat])}
        # receiving keys off the game total, rushing off the spread -- that is
        # where each one tested better.
        mode = "spread" if stat in ("rushing_yards", "carries") else "total"
        envs[stat] = {bar: (models[stat].env(bar, mode) + (mode,))
                      for bar in sorted(want[stat])}
    out, seen = [], set()
    skipped = defaultdict(int)
    for stat, who, side, bar, price, gm in board:
        if only and only.lower() not in (gm or "").lower():
            continue
        if stat not in models or (who, stat, side, bar) in seen:
            continue
        seen.add((who, stat, side, bar))
        pj = project(rows, who, stat)
        if pj is None:
            continue
        proj, vol, ng, tm, pos = pj
        # THE QB SPLIT IS NOT OPTIONAL. If there are too few games with this
        # team's current starter, the line is UNKNOWABLE -- it does not fall
        # back to the all-quarterbacks projection. That fallback is what put
        # Olamide Zaccheaus at the top of the board on 19 Atlanta games when he
        # has played ONE with Penix, and it is the same contamination the split
        # was added to remove. A silent fallback to the thing you filtered out
        # is worse than no filter, because it looks filtered.
        st = starter.get(tm)
        pj2 = project(rows, who, stat, qb_games=st[2]) if st else None
        if pj2 is None:
            ok, why = gate(stat, proj, bar, st[0] if st else None, None, None, None,
                           status=hurt.get(norm_name(who), ('', ''))[0])
            skipped[why] += 1
            continue
        proj, vol, ng = pj2[0], pj2[1], pj2[2]
        if proj <= 0:
            continue
        d = drift(rows, who, stat, tt, qb_games=st[2])
        cc = cast_change(rows, who, stat, cst, qb_games=st[2])
        shr = share_of(rows, who, stat, tt, qb_games=st[2])
        status, hurtwith = hurt.get(norm_name(who), ('', ''))
        ok, why = gate(stat, proj, bar, st[0], ng, d, cc, share=shr,
                       status=status)
        if not ok:
            skipped[why] += 1
            continue
        sk = why
        dfn, league = defs[stat][bar]
        erate, eleague, emode = envs[stat][bar]
        ek = TONIGHT.get((tm, "spread" if emode == "spread" else "total"))
        ekey = None if ek is None else (
            round(max(-14.0, min(14.0, ek)) / calib.ENV_BAND) * calib.ENV_BAND
            if emode == "spread"
            else round(ek / calib.ENV_BAND) * calib.ENV_BAND)
        p, n = models[stat].p(stat, proj, vol, bar, side,
                              bias=biases[stat][bar], defn=dfn, league=league,
                              opp=None, pos=pos, drop_player=who,
                              envrate=erate, envleague=eleague, envkey=ekey)
        if p is None:
            continue
        out.append((p - imp(price), p, n, who, side, bar, stat, price, proj, ng,
                    tm, sk, gm, avail(status)[1], hurtwith))
    out.sort(reverse=True)
    print(f"{len(out)} priced.\n")
    print("  hits   my probability this wins.")
    print("  edge   that probability MINUS the one the price implies, in")
    print("         percentage points. -113 implies 53.1%, so a 65.2% line is")
    print("         +12.1. It is not a return on money.")
    print("  skill  how much better the model is than guessing the band average,")
    print("         for lines this far from the projection. 21% means it removes")
    print("         21% of that guess's error. ZERO MEANS THE MODEL KNOWS")
    print("         NOTHING HERE and the edge figure above is meaningless.")
    print("  $10    what ten dollars returns in profit if it wins.")
    print("  ret    expected profit per $10 staked, at my probability. This is")
    print("         the money number; edge is not.\n")
    print(f"  {'edge':>6s} {'hits':>6s} {'bet':34s} {'price':>6s} {'proj':>7s} "
          f"{'skill':>6s} {'$10':>7s} {'ret':>7s}  game")
    print("-" * 104)
    for e, p, n, who, side, bar, stat, price, proj, ng, tm, sk, gm, flag, hw in out:
        if e < min_edge:
            continue
        lab = f"{who} {side} {bar:g} {stat.replace('_',' ')}"
        short = " @ ".join(w.split()[-1] for w in gm.split(" @ ")) if gm else "?"
        win, ret = money(price, p)
        print(f"  {e*100:+5.1f} {p*100:5.1f}%  {lab[:34]:34s} {price:+6d} "
              f"{proj:7.1f} {sk*100:5.0f}% {win:7.2f} {ret:+7.2f}  {short}")
        if flag:
            print(f"         ^^ {who} is {flag}"
                  f"{' -- ' + hw if hw else ''}")
    neg = sum(1 for r in out if r[0] < min_edge)
    print(f"\n  {neg} of {len(out)} fall below the {min_edge*100:.0f}-point cutoff")
    if skipped:
        print("\n  refused rather than guessed:")
        for k, v in sorted(skipped.items(), key=lambda x: -x[1]):
            print(f"    {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("-")]
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    me = 0.03
    if "--min-edge" in sys.argv:
        me = float(sys.argv[sys.argv.index("--min-edge") + 1])
    only = None
    if "--game" in sys.argv:
        only = sys.argv[sys.argv.index("--game") + 1]
    sys.exit(main(a[0] if a else "sweep.txt", me, only))

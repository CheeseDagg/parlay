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
}
MK = {
    "player_receptions": "receptions", "player_receptions_alternate": "receptions",
    "player_reception_yds": "receiving_yards",
    "player_reception_yds_alternate": "receiving_yards",
    "player_rush_yds": "rushing_yards", "player_rush_yds_alternate": "rushing_yards",
    "player_pass_yds": "passing_yards", "player_pass_yds_alternate": "passing_yards",
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
}
MIN_SKILL = 0.05      # below this the edge is not reported as an edge


def gate(stat, proj, bar, starter, qb_games_n, dr, cc, share=None):
    """(ok, reason). The whole admission chain in one testable place.

    It lives out here because the last three times I put a rule inside main() --
    `spec in COMPARE`, the history-unavailable line, and these gates -- the
    selftest could not reach it and the rule shipped broken. main() reads files;
    a rule that only runs there is a rule nothing checks."""
    if starter is None:
        return False, "no identified starter"
    if qb_games_n is None or qb_games_n < 4:
        return False, f"under 4 games with {starter}"
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
        by[(y, r.get("player_display_name"))].append(
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
        for col in ("targets", "carries"):
            tt[(y, w, tm, col)] += _f(r.get(col))
    return tt


def position_cast(rows):
    """(season, week, team, position, volume column) -> [(volume, player), ...]."""
    c = defaultdict(list)
    for y, r in rows:
        tm = r.get("team") or r.get("recent_team")
        w = int(r.get("week") or 0)
        pos = r.get("position") or ""
        for col in ("targets", "carries"):
            v = _f(r.get(col))
            if v > 0:
                c[(y, w, tm, pos, col)].append((v, r.get("player_display_name")))
    return c


def cast_change(rows, who, stat, cst, qb_games=None):
    """How much the position group's personnel around him has turned over."""
    volcol, _ = STATS[stat]
    hist = [(y, r) for y, r in rows if r.get("player_display_name") == who]
    if not hist:
        return None
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, int(r.get("week") or 0), r.get("position") or "") for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < 4:
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
    hist = [(y, r) for y, r in rows if r.get("player_display_name") == who]
    if not hist:
        return None
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
    hist = [(y, r) for y, r in rows if r.get("player_display_name") == who]
    if not hist:
        return None
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, int(r.get("week") or 0), r) for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < 4:
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
    hist = [(y, r) for y, r in rows if r.get("player_display_name") == who]
    if not hist:
        return None
    tm = hist[-1][1].get("team") or hist[-1][1].get("recent_team")
    sel = [(y, r) for y, r in hist
           if (r.get("team") or r.get("recent_team")) == tm
           and (qb_games is None or (y, int(r.get("week") or 0)) in qb_games)]
    if len(sel) < 4:
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
        out.append((NFLPROPS_STAT[lab], who.strip(), side, float(bar), int(price)))
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
    cur, out = None, []
    for line in open(path, encoding="utf-8"):
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
                out.append((MK[cur], d, side, float(pt), pr))
    return out


def imp(a):
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def selftest():
    f = 0

    def ck(c, m):
        nonlocal f
        if not c:
            print(f"  FAIL {m}"); f += 1

    ck(abs(imp(-110) - 0.5238) < 1e-3, "imp")
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
    ok, why = gate("receptions", 7.2, 4.5, "QB", 3, 0.01, 0.0)
    ck(not ok and "under 4 games" in why, f"thin QB sample: {why}")
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
    r2 = parse_nflprops(p2)
    ck(len(r2) == 3, f"three candidates parsed, got {len(r2)}: {r2}")
    ck(r2[0] == ("rushing_yards", "Brock Purdy", "Over", 19.5, -102),
       f"first row: {r2[0]}")
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


def main(path, min_edge=0.03):
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
    if not board:
        board = parse_nflprops(path)
        if board:
            print("(read as an nflprops board rather than a sweep)")
    print(f"{len(board)} outcomes parsed\n")
    want = defaultdict(set)
    for stat, who, side, bar, price in board:
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
    for stat, who, side, bar, price in board:
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
            ok, why = gate(stat, proj, bar, st[0] if st else None, None, None, None)
            skipped[why] += 1
            continue
        proj, vol, ng = pj2[0], pj2[1], pj2[2]
        if proj <= 0:
            continue
        d = drift(rows, who, stat, tt, qb_games=st[2])
        cc = cast_change(rows, who, stat, cst, qb_games=st[2])
        shr = share_of(rows, who, stat, tt, qb_games=st[2])
        ok, why = gate(stat, proj, bar, st[0], ng, d, cc, share=shr)
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
                    tm, sk))
    out.sort(reverse=True)
    print(f"{len(out)} priced.  EDGE = calibrated probability minus the price\n")
    print(f"  {'edge':>6s} {'hits':>6s} {'bet':38s} {'price':>6s} {'proj':>7s} "
          f"{'gms':>4s} {'skill':>6s}")
    print("-" * 84)
    for e, p, n, who, side, bar, stat, price, proj, ng, tm, sk in out:
        if e < min_edge:
            continue
        lab = f"{who} {side} {bar:g} {stat.replace('_',' ')}"
        print(f"  {e*100:+5.1f} {p*100:5.1f}%  {lab[:38]:38s} {price:+6d} "
              f"{proj:7.1f} {ng:4d} {sk*100:5.0f}%")
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
    sys.exit(main(a[0] if a else "sweep.txt", me))

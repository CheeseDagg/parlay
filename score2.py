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


def build(rows, stat):
    """Out-of-sample (player, projection, volume, outcome, opp, pos, season) rows."""
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
            out.append((who, vol * rt, vol, v[i][2], v[i][3], v[i][4], y))
    return out


def team_volume(rows):
    """(season, week, team, volume column) -> the team's total."""
    tt = defaultdict(float)
    for y, r in rows:
        tm = r.get("team") or r.get("recent_team")
        w = int(r.get("week") or 0)
        for col in ("targets", "carries"):
            tt[(y, w, tm, col)] += _f(r.get(col))
    return tt


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
    tt = team_volume(rows)
    models, biases, defs = {}, {}, {}
    for stat in STATS:
        rs = build(rows, stat)
        if len(rs) < 500:
            continue
        m = calib.Model(rs)
        models[stat] = m
        defs[stat] = {}
    board = parse(path)
    print(f"{len(board)} outcomes parsed\n")
    want = defaultdict(set)
    for stat, who, side, bar, price in board:
        want[stat].add(bar)
    for stat in models:
        biases[stat] = {bar: models[stat].bias(stat, bar) for bar in sorted(want[stat])}
        defs[stat] = {bar: models[stat].defence(bar) for bar in sorted(want[stat])}
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
        if not st:
            skipped["no identified starter"] += 1
            continue
        pj2 = project(rows, who, stat, qb_games=st[2])
        if pj2 is None:
            skipped[f"under 4 games with {st[0]}"] += 1
            continue
        proj, vol, ng = pj2[0], pj2[1], pj2[2]
        if proj <= 0:
            continue
        d = drift(rows, who, stat, tt, qb_games=st[2])
        if d is None or d > DRIFT_MAX:
            skipped[f"role shifting (share moved {d:.3f})" if d is not None
                    else "role drift unmeasurable"] += 1
            continue
        dfn, league = defs[stat][bar]
        p, n = models[stat].p(stat, proj, vol, bar, side,
                              bias=biases[stat][bar], defn=dfn, league=league,
                              opp=None, pos=pos, drop_player=who)
        if p is None:
            continue
        out.append((p - imp(price), p, n, who, side, bar, stat, price, proj, ng, tm))
    out.sort(reverse=True)
    print(f"{len(out)} priced.  EDGE = calibrated probability minus the price\n")
    print(f"  {'edge':>6s} {'hits':>6s} {'bet':40s} {'price':>6s} {'proj':>7s} {'gms':>4s}")
    print("-" * 78)
    for e, p, n, who, side, bar, stat, price, proj, ng, tm in out:
        if e < min_edge:
            continue
        lab = f"{who} {side} {bar:g} {stat.replace('_',' ')}"
        print(f"  {e*100:+5.1f} {p*100:5.1f}%  {lab[:40]:40s} {price:+6d} "
              f"{proj:7.1f} {ng:4d}")
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

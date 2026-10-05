#!/usr/bin/env python3
"""lm.py -- the trends view every app sells, next to what the data actually says.

    python3 lm.py <board-file>
    python3 lm.py --selftest

Linemate's core product is a visualised hit rate over a player's last 5, 10 and
20 games. 555,000 people read that number. This prints it, then prints what is
wrong with it, line by line, so the difference is visible instead of asserted:

  L5/L10/L20   the trends number, exactly as those apps compute it: his own
               games, his own outcomes, counted off the stat file.
  TRUE         the same count after the games he played and produced NOTHING in
               are added back. The weekly stat file has no row for a player who
               touched the ball zero times, so 244 of 603 players who took a snap
               in 2026 are missing at least one week. Every trends app in this
               market is counting "the last ten games he produced in" and calling
               it the last ten games. The bias is upward and it is worst for
               exactly the long-shot players their feeds promote.
  VALID        whether that sample describes the player who takes the field
               tonight: same quarterback, role not moving, cast not turned over,
               not injured. Drake London is 6 of 10 over 69.5 receiving yards in
               Michael Penix Jr.'s starts and 0 of 5 with anyone else. A trends
               app shows 5 of 15 and calls it a cold streak.
  MINE         the calibrated probability -- what actually happened to the
               thousands of comparable player-games, not to him.

Measured gaps between the trends number and the truth, 2022-2025:

    his own hit rate over-predicts by  +5.8 / +8.2 / +11.8 points
    at trailing volumes of              4-6 /  6-8 /     8+  targets

so the number is worst exactly where the betting volume is.
"""
import csv, os, re, sys
from collections import defaultdict

import score2 as S

WINDOWS = (5, 10, 20)


def played_weeks(path_by_year):
    """(norm name) -> {(season, week): team} for every game he took a snap in.

    This is the half the stat file does not have. Without it L10 is not the last
    ten games, it is the last ten he recorded something in."""
    out = defaultdict(dict)
    for yr, path in path_by_year.items():
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if S._f(r.get("offense_snaps")) <= 0:
                    continue
                out[S.norm_name(r.get("player"))][(yr, int(r.get("week") or 0))] = \
                    r.get("team")
    return out


def hit_rates(rows, who, stat, bar, side, snaps=None):
    """[(window, hits, n)] for each window, over his last games on this team.

    With `snaps`, the games he played and produced nothing in are added back as
    zeros -- which is the honest count and the one nobody shows."""
    key = S.norm_name(who)
    hist = [(y, int(r.get("week") or 0), r) for y, r in rows
            if S.norm_name(r.get("player_display_name")) == key]
    if not hist:
        return None, None
    hist.sort(key=lambda t: (t[0], t[1]))
    tm = hist[-1][2].get("team") or hist[-1][2].get("recent_team")
    got = {(y, w): r for y, w, r in hist
           if (r.get("team") or r.get("recent_team")) == tm}
    weeks = set(got)
    if snaps:
        for (y, w), t in (snaps.get(key) or {}).items():
            if t == tm:
                weeks.add((y, w))
    order = sorted(weeks, reverse=True)

    def count(seq):
        out = []
        for n in WINDOWS:
            sel = seq[:n]
            if len(sel) < n:
                out.append((n, None, len(sel)))
                continue
            h = 0
            for k in sel:
                r = got.get(k)
                v = S._f(r.get(stat)) if r is not None else 0.0
                if (v > bar) if side == "Over" else (v < bar):
                    h += 1
            out.append((n, h, n))
        return out

    naive = count([k for k in order if k in got])
    true = count(order) if snaps else naive
    return naive, true


def fmt(cells):
    out = []
    for n, h, got in cells:
        out.append(f"{h}/{n}" if h is not None else f" -/{n}")
    return out


def main(path):
    rows = S.load()
    S.TOT, S.SPD = S.schedule()
    tt = S.team_volume(rows)
    cst = S.position_cast(rows)
    hurt = S.injuries()
    snaps = played_weeks({2025: "snaps2025.csv", 2026: "snaps26b.csv"})
    for y, r in rows:
        S.TEAM[(y, r.get("player_display_name"))] = (r.get("team")
                                                     or r.get("recent_team"))
    q = defaultdict(set)
    for y, r in rows:
        if (r.get("position") or "") == "QB" and S._f(r.get("attempts")) >= 10:
            q[((r.get("team") or r.get("recent_team")),
               r.get("player_display_name"))].add((y, int(r.get("week") or 0)))
    start = {}
    for (tm, who), gs in q.items():
        cur = [w for (yy, w) in gs if yy == S.CURRENT]
        if cur and (tm not in start or max(cur) > start[tm][1]):
            start[tm] = (who, max(cur), gs)

    board = S.parse(path)
    print(f"{len(board)} lines\n")
    print("  L5/L10/L20  the trends number every app shows: his own last games.")
    print("  TRUE        the same count with the games he played and produced")
    print("              nothing in added back -- the stat file has no row for")
    print("              those, so the published number silently drops them.")
    print("  VALID       does that sample describe tonight's player at all.\n")
    hdr = (f"  {'bet':<42} {'L5':>5} {'L10':>5} {'L20':>5}  "
           f"{'TRUE L10':>8} {'VALID':<42}")
    print(hdr); print("-" * len(hdr))
    shown = 0
    for stat, who, side, bar, price, gm in board:
        if stat not in S.STATS:
            continue
        naive, true = hit_rates(rows, who, stat, bar, side, snaps)
        if naive is None:
            continue
        pj = S.project(rows, who, stat)
        why = "no projection"
        if pj is not None:
            tm = pj[3]
            st = start.get(tm)
            pj2 = S.project(rows, who, stat, qb_games=st[2]) if st else None
            if pj2 is None:
                why = f"NO -- under {S.MIN_GAMES} games with {st[0] if st else '?'}"
            else:
                ok, r = S.gate(stat, pj2[0], bar, st[0], pj2[2],
                               S.drift(rows, who, stat, tt, qb_games=st[2]),
                               S.cast_change(rows, who, stat, cst, qb_games=st[2]),
                               share=S.share_of(rows, who, stat, tt, qb_games=st[2]),
                               status=hurt.get(S.norm_name(who), ("", ""))[0])
                why = (f"yes -- {r*100:.0f}% skill, {pj2[2]} games with {st[0]}"
                       if ok else "NO -- " + r)
        n5, n10, n20 = fmt(naive)
        t10 = fmt(true)[1]
        gap = "" if t10 == n10 else "  <-- DIFFERENT"
        lab = f"{who} {side} {bar:g} {stat.replace('_', ' ')}"
        print(f"  {lab[:42]:<42} {n5:>5} {n10:>5} {n20:>5}  {t10:>8}  "
              f"{why[:42]:<42}{gap}")
        shown += 1
    print(f"\n  {shown} lines compared")
    return 0


def selftest():
    bad = []

    def ck(c, m):
        if not c:
            bad.append(m); print("  FAIL", m)

    def row(y, w, tm, yds, who="Ghost"):
        return (y, {"player_display_name": who, "position": "WR", "team": tm,
                    "week": str(w), "targets": "5", "receptions": "3",
                    "receiving_yards": str(yds), "season_type": "REG",
                    "opponent_team": "X"})
    # five productive games, all over the bar
    rows = [row(2026, w, "NO", 80) for w in (1, 2, 3, 4, 5)]
    naive, true = hit_rates(rows, "Ghost", "receiving_yards", 69.5, "Over")
    ck(naive[0] == (5, 5, 5), f"five from five over: {naive}")
    ck(naive[1] == (10, None, 5), f"ten is not available from five games: {naive}")
    # now say he also PLAYED three more games and did nothing in them
    snaps = {"ghost": {(2026, w): "NO" for w in range(1, 9)}}
    naive, true = hit_rates(rows, "Ghost", "receiving_yards", 69.5, "Over", snaps)
    ck(naive[0] == (5, 5, 5), "the published number is unchanged")
    ck(true[0] == (5, 2, 5),
       f"but the TRUE last five is 2 of 5 -- three were zero-touch games "
       f"the stat file has no row for: {true}")
    ck(naive[0][1] != true[0][1],
       "the whole point is that these two numbers differ")
    # an Under must count the other way
    naive, _t = hit_rates(rows, "Ghost", "receiving_yards", 69.5, "Under")
    ck(naive[0] == (5, 0, 5), f"nothing is under when everything is over: {naive}")
    # only this team's games count
    # the old-team games must sit INSIDE the window, or dropping the team
    # filter changes nothing and the test passes for free
    mixed = [row(2026, w, "OLD", 200) for w in (1, 2, 3, 4, 5)] + \
            [row(2026, w, "NO", 10) for w in (6, 7, 8)]
    naive, _t = hit_rates(mixed, "Ghost", "receiving_yards", 69.5, "Over")
    ck(naive[0] == (5, None, 3),
       f"only three games on his current team, so there is no L5 at all -- "
       f"his old team's 200-yard games must not pad it out: {naive}")
    # and the most RECENT games, not the first ones
    recent = [row(2026, w, "NO", 200) for w in (1, 2, 3)] + \
             [row(2026, w, "NO", 10) for w in (4, 5, 6, 7, 8)]
    naive, _t = hit_rates(recent, "Ghost", "receiving_yards", 69.5, "Over")
    ck(naive[0] == (5, 0, 5),
       f"L5 is the LAST five, not the first five: {naive}")
    ck(hit_rates(rows, "Nobody", "receiving_yards", 69.5, "Over")[0] is None,
       "an unknown player is None, not zero")
    # played_weeks itself: a row with zero offensive snaps is NOT a game played
    import tempfile
    fd, sp = tempfile.mkstemp(suffix=".csv")
    os.write(fd, (b"week,player,team,offense_snaps\n"
                  b"1,Ghost,NO,42\n"
                  b"2,Ghost,NO,0\n"
                  b"3,Ghost,NO,\n"
                  b"4,Ghost,NO,7\n"))
    os.close(fd)
    pw = played_weeks({2026: sp})
    ck(set(pw["ghost"]) == {(2026, 1), (2026, 4)},
       f"a zero-snap row is an inactive, not a game he played: {pw['ghost']}")
    ck(played_weeks({2026: sp + ".missing"}) == {},
       "a missing file is empty, not a crash")
    os.unlink(sp)
    print("lm selftest:", "FAILED" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    a = [x for x in sys.argv[1:] if not x.startswith("-")]
    sys.exit(main(a[0] if a else "sweep.txt"))

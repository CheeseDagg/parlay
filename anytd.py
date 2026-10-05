#!/usr/bin/env python3
"""anytd.py -- price the anytime-touchdown market, which nothing here graded.

    python3 anytd.py <sweep-file>
    python3 anytd.py --selftest

Of 1,415 lines in a sweep of one game, score2.py prices 183: receptions,
receiving yards, rushing yards, passing yards. player_anytime_td is the most-bet
prop in football and it was simply absent. This fills that in, built and checked
the same way as everything else here.

WHAT WAS MEASURED, 16,380 player-games, 2022-2025, base rate 20.3%:

    method                                Brier   skill over base
    base rate for everyone              0.16200             0.0%
    his own rate of scoring games       0.15922             1.7%
    his own touchdowns per touch        0.15044             4.0%
    SHRUNK rate, calibrated             0.14554            10.2%

Leave-one-PLAYER-out gives the same 0.14556, so the figure is not leaking
through the player's own rows.

THE RATE CANNOT BE HIS OWN. Estimating touchdowns per touch from a player's own
history projected 4,517 of 16,380 player-games at zero -- 28% of the board
declared impossible -- because a back with no touchdown in three games has a
measured rate of exactly 0.000. Drake London, Alvin Kamara, Kyle Pitts and Jahan
Dotson all came out at 0.0% for tonight. Zero over a small sample is not a rate,
it is an absence of information, and this is the same error as the own-hit-rate
on yardage in its most extreme form. So the rate is shrunk toward what the
position actually scores, by PSEUDO_TOUCHES pseudo-touches at the league rate.
The weight was tuned, not chosen:

    pseudo-touches     0       10      25      50     100     200     400
    Brier         .15044  .14834  .14701  .14606  .14561  .14554  .14570
    zeros           4517     278     276     274     274     274     274

THE CEILING. The top projection bucket scored 55.5% (n=364), and no bucket
anywhere reaches 60%:

    projection   n     predicted  actual
    0.00-0.08   3113      4.4%     5.5%
    0.08-0.15   3673     11.4%    11.0%
    0.15-0.25   4074     19.9%    19.4%
    0.25-0.35   3171     29.6%    30.1%
    0.35-0.50   1985     40.9%    40.7%
    0.50-1.01    364     55.0%    55.5%

So an anytime price of -150 (60% implied) or worse cannot be right about anyone,
and the model refuses to pretend otherwise: CEILING caps it. Predicted tracks
actual to within 1.1 points in every bucket, so unlike the yardage model this
one needs no bias correction.

WHAT IT STILL DOES NOT KNOW: nothing in here is aware of how many points the
team scores. Atlanta has five offensive touchdowns in three games; the model
reads only each player's own touches and the league rate per touch. A team
expected to score twice all night and one expected to score five times get the
same treatment at equal volume. Do not use this to compare players across games.
"""
import bisect, csv, math, os, re, statistics, sys
from collections import defaultdict

SEASONS = [2022, 2023, 2024, 2025]
CURRENT = 2026
SPW = os.environ.get("SPW_DIR", ".")
HALF_LIFE = 5.0
PSEUDO_TOUCHES = 200.0      # tuned above
WIN = 0.04                  # calibration half-width in probability
MIN_BUCKET = 300
MIN_GAMES = 3
CEILING = 0.56              # the measured top of the distribution
POS = ("RB", "WR", "TE")
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)


def norm_name(n):
    return SUFFIX.sub("", (n or "").strip()).lower()


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def logs(years, spw=None):
    """(name, pos) -> chronological [(season, week, team, touches, tds)]."""
    spw = SPW if spw is None else spw
    out = defaultdict(list)
    for y in years:
        p = os.path.join(spw, f"spw{y}.csv")
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("season_type") or "REG") != "REG":
                    continue
                pos = (r.get("position") or "").upper()
                if pos not in POS:
                    continue
                out[(norm_name(r.get("player_display_name")), pos)].append(
                    (y, int(r.get("week") or 0),
                     r.get("team") or r.get("recent_team"),
                     _f(r.get("carries")) + _f(r.get("targets")),
                     _f(r.get("rushing_tds")) + _f(r.get("receiving_tds"))))
    for k in out:
        out[k].sort()
    return out


def league(lg):
    """Touchdowns per touch, by position. Measured: RB .0304, TE .0519,
    WR .0478 -- a tight end scores on a touch more often than a receiver."""
    pool = defaultdict(lambda: [0.0, 0.0])
    for (_who, pos), games in lg.items():
        for g in games:
            pool[pos][0] += g[4]
            pool[pos][1] += g[3]
    return {p: (t / o if o else 0.0) for p, (t, o) in pool.items()}


def project(prior, pos, lr):
    """(probability, touches per game). The rate is shrunk; the probability is
    capped at the measured ceiling, because no profile in four seasons beat it."""
    if len(prior) < MIN_GAMES:
        return None
    w = [0.5 ** ((len(prior) - 1 - j) / HALF_LIFE) for j in range(len(prior))]
    sw = sum(w)
    per = sum(g[3] * wt for g, wt in zip(prior, w)) / sw
    touches = sum(g[3] * wt for g, wt in zip(prior, w))
    tds = sum(g[4] * wt for g, wt in zip(prior, w))
    rate = (tds + lr * PSEUDO_TOUCHES) / (touches + PSEUDO_TOUCHES)
    return min(CEILING, 1.0 - math.exp(-(per * rate))), per


class Cal:
    """What actually happened to OTHER players with a projection this size."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r[1])
        self.projs = [r[1] for r in self.rows]

    def p(self, proj, drop=None):
        lo = bisect.bisect_left(self.projs, proj - WIN)
        hi = bisect.bisect_right(self.projs, proj + WIN)
        sel = [r for r in self.rows[lo:hi] if r[0] != drop]
        if len(sel) < MIN_BUCKET:
            i = bisect.bisect_left(self.projs, proj)
            a, b = max(0, i - MIN_BUCKET), min(len(self.rows), i + MIN_BUCKET)
            sel = [r for r in self.rows[a:b] if r[0] != drop]
        if not sel:
            return None, 0
        return min(CEILING, statistics.mean(r[2] for r in sel)), len(sel)


def training(lg, lr):
    rows = []
    for (who, pos), games in lg.items():
        for i in range(len(games)):
            tm = games[i][2]
            prior = [g for g in games[:i] if g[2] == tm][-10:]
            pj = project(prior, pos, lr.get(pos, 0.04))
            if pj is None:
                continue
            rows.append((who, pj[0], 1.0 if games[i][4] > 0 else 0.0))
    return rows


def starters(spw=None):
    """team -> (quarterback, set of (season, week) he started).

    THE SAME RULE score2.py ENFORCES. Without it this module priced Kevin
    Austin Jr. at +1300 off 4.1 touches a game -- a 2025 number. He has played
    ONE game in 2026 and sits behind Olave, Vele, Lance, two tight ends and
    three backs. Charlie Woerner, one 2026 game, came out at 7.4% on 2025
    Atlanta snaps with a different quarterback. A silent fall back to last
    season is worse than no filter, because the output looks filtered.
    """
    spw = SPW if spw is None else spw
    qbs = defaultdict(set)
    for y in (CURRENT - 1, CURRENT):
        p = os.path.join(spw, f"spw{y}.csv")
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("season_type") or "REG") != "REG":
                    continue
                if (r.get("position") or "") != "QB" or _f(r.get("attempts")) < 10:
                    continue
                tm = r.get("team") or r.get("recent_team")
                qbs[(tm, r.get("player_display_name"))].add(
                    (y, int(r.get("week") or 0)))
    out = {}
    for (tm, who), gs in qbs.items():
        cur = [w for (yy, w) in gs if yy == CURRENT]
        if not cur:
            continue
        if tm not in out or max(cur) > out[tm][1]:
            out[tm] = (who, max(cur), gs)
    return out


def starter_games(allg, team, st, n=10):
    """His last n games on THIS team with THIS quarterback. Nothing else.

    Extracted because it lived in main(), where the mutation harness could not
    reach it: breaking the filter changed no test. That is the fourth rule in
    this project to hide in main() -- `spec in COMPARE`, the history-unavailable
    line, the score2 gates, and this."""
    if st is None:
        return []
    return [g for g in allg if g[2] == team and (g[0], g[1]) in st[2]][-n:]


def imp(price):
    return (-price) / (-price + 100.0) if price < 0 else 100.0 / (price + 100.0)


def money(price, p, stake=10.0):
    win = stake * price / 100.0 if price > 0 else stake * 100.0 / -price
    return win, p * win - (1 - p) * stake


NAME_W = 20   # the sweep truncates the name column


def parse(path):
    """[(name, price)] from the player_anytime_td block, and ONLY that block.

    The name column is truncated at 20 characters, so "Atlanta Falcons Defe"
    and a long player name arrive cut off. A truncated name must never be
    resolved by prefix to a different player -- that is how a surname match put
    Javonte Williams on a Kyren Williams ticket. Truncated names are returned
    as-is and the caller refuses what it cannot match exactly."""
    out, inblock = [], False
    with open(path, encoding="utf-8") as f:
        for line in f:
            # the name may carry digits: player_anytime_td_h1 is a
            # DIFFERENT market and must end the block, not be ignored
            m = re.match(r"^  ([a-z0-9_]+)\s+\(\d+\)", line)
            if m:
                inblock = m.group(1) == "player_anytime_td"
                continue
            if not inblock:
                continue
            # ONE space is enough: a name that fills the 20-character
            # column leaves exactly one before the side, and demanding
            # two silently dropped every truncated name.
            m = re.match(r"^ {6}(.{1,%d}?)\s+(Yes|No)\s+([+-]\d+)" % NAME_W, line)
            if m:
                out.append((m.group(1).strip(), m.group(2), int(m.group(3))))
    return out


def resolve(name, lg):
    """A board name to a (norm_name, pos) key, or None. Exact match only unless
    the board's name is TRUNCATED, and then only if exactly one player's name
    starts with it -- two candidates means refuse, never guess."""
    key = norm_name(name)
    hits = [k for k in lg if k[0] == key]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return None
    if len(name) >= NAME_W:
        pre = [k for k in lg if k[0].startswith(key)]
        if len(pre) == 1:
            return pre[0]
    return None


def main(path, min_edge=0.03):
    hist = logs(SEASONS)
    if not hist:
        print(f"no spw files in {SPW}", file=sys.stderr)
        return 2
    lr = league(hist)
    cal = Cal(training(hist, lr))
    cur = logs([CURRENT - 1, CURRENT])
    qb = starters()
    board = parse(path)
    print(f"{len(cal.rows)} player-games trained, "
          f"base rate {statistics.mean(r[2] for r in cal.rows)*100:.1f}%")
    print(f"{len(board)} anytime-touchdown lines on the board\n")
    print("  model   the probability he scores. Capped at 56%: the top bucket of")
    print("          16,380 player-games scored 55.5% and none reached 60%, so a")
    print("          price of -150 or worse cannot be right about anybody.")
    print("  edge    that probability minus the one the price implies.")
    print("  ret     expected profit per $10 staked. This is the money number.")
    print("  Nothing here knows how many points the team is expected to score.\n")
    print(f"  {'edge':>6} {'model':>6} {'player':<22} {'pos':<4} {'touch':>6} "
          f"{'price':>7} {'implied':>8} {'n':>6} {'ret':>7}")
    print("-" * 88)
    out, refused = [], []
    for name, side, price in board:
        if side != "Yes":
            continue
        k = resolve(name, cur)
        if k is None:
            refused.append((name, "no unambiguous player of that name"))
            continue
        allg = cur[k]
        if not allg:
            refused.append((name, "no games on file"))
            continue
        tm = allg[-1][2]
        st = qb.get(tm)
        if st is None:
            refused.append((name, f"no identified starter for {tm}"))
            continue
        # NO FALLBACK. Games with this team AND this quarterback, or nothing.
        prior = starter_games(allg, tm, st)
        pj = project(prior, k[1], lr.get(k[1], 0.04))
        if pj is None:
            refused.append((name, f"{len(prior)} game(s) with {st[0]}, "
                                  f"needs {MIN_GAMES}"))
            continue
        p, n = cal.p(pj[0], drop=k[0])
        if p is None:
            refused.append((name, "no comparable projections to calibrate on"))
            continue
        _w, ret = money(price, p)
        out.append((p - imp(price), p, name, k[1], pj[1], price, n, ret))
    out.sort(reverse=True)
    for e, p, name, pos, per, price, n, ret in out:
        print(f"  {e*100:+6.1f} {p*100:5.1f}% {name:<22} {pos:<4} {per:>6.1f} "
              f"{price:>+7d} {imp(price)*100:>7.1f}% {n:>6} {ret:>+7.2f}")
    if refused:
        print("\n  refused rather than guessed:")
        for name, why in refused:
            print(f"    {name:<24} {why}")
    return 0


def selftest():
    bad = []

    def ck(c, m):
        if not c:
            bad.append(m)
            print("  FAIL", m)

    # the shrinkage is the whole point: a player with no touchdowns must not
    # project at zero
    cold = [(2026, w, "NO", 12.0, 0.0) for w in (1, 2, 3)]
    pj = project(cold, "RB", 0.0304)
    ck(pj is not None and pj[0] > 0.10,
       f"no touchdowns in three games is not a 0% chance: {pj}")
    hot = [(2026, w, "NO", 12.0, 2.0) for w in (1, 2, 3)]
    gap = project(hot, "RB", 0.0304)[0] - pj[0]
    ck(gap > 0.08,
       f"two touchdowns a game must move it MATERIALLY, not to the fourth "
       f"decimal -- a shrinkage heavy enough to erase his own record is the "
       f"same as having no model: {gap:.4f}")
    # volume has to matter
    lowv = project([(2026, w, "NO", 2.0, 0.0) for w in (1, 2, 3)], "RB", 0.0304)
    ck(lowv[0] < pj[0], f"two touches must beat nothing less than twelve: {lowv}")
    # the ceiling
    huge = [(2026, w, "NO", 40.0, 6.0) for w in (1, 2, 3)]
    ck(project(huge, "RB", 0.0304)[0] <= CEILING + 1e-9,
       "the ceiling must hold against any input")
    ck(project([(2026, 1, "NO", 9.0, 1.0)], "RB", 0.0304) is None,
       "one game is not enough to project from")
    # a position with a higher league rate must project higher on equal volume
    ck(project(cold, "TE", 0.0519)[0] > project(cold, "RB", 0.0304)[0],
       "the position's own rate must come through the shrinkage")
    # the calibration must drop the player's own rows
    # kept under the ceiling on purpose: if both figures were capped the test
    # could not tell whether the player was dropped at all
    rows = [("star", 0.50, 0.0)] * 400
    rows += ([("other", 0.50, 1.0)] * 100) + ([("other", 0.50, 0.0)] * 200)
    c = Cal(rows)
    p_all, _n = c.p(0.50)
    p_drop, _n = c.p(0.50, drop="star")
    ck(abs(p_all - 100 / 700) < 1e-9,
       f"the bucket with him in it: {p_all}")
    ck(abs(p_drop - 1 / 3) < 1e-9 and p_drop > p_all,
       f"dropping his own 400 rows must change it: {p_all} {p_drop}")
    hotrows = [("a", 0.50, 1.0)] * 300 + [("b", 0.50, 1.0)] * 300
    hc = Cal(hotrows)
    ck(abs(hc.p(0.50)[0] - CEILING) < 1e-9,
       f"a bucket that went 600 for 600 must still be capped at the measured "
       f"ceiling: {hc.p(0.50)[0]}")
    # money
    w, r = money(-200, 1.0)
    ck(abs(w - 5.0) < 1e-9, f"-200 returns $5 on $10: {w}")
    w, r = money(370, 0.291)
    ck(abs(w - 37.0) < 1e-9 and abs(r - (0.291 * 37 - 0.709 * 10)) < 1e-9,
       f"+370 at 29.1%: {w} {r}")
    ck(abs(imp(-210) - 210 / 310) < 1e-9, "implied from a negative price")
    ck(abs(imp(370) - 100 / 470) < 1e-9, "implied from a positive price")
    # the parser must take the anytime block and nothing else
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".txt")
    os.write(fd, (b"Atlanta Falcons @ New Orleans Saints   2026-10-06T00:15:00Z\n\n"
                  b"  player_anytime_td  (3)\n"
                  b"      Bijan Robinson       Yes                              -210  67.7%\n"
                  b"      Brian Robinson Jr.   Yes                              +370  21.3%\n"
                  b"      Atlanta Falcons Defe Yes                              +700  12.5%\n"
                  b"  player_anytime_td_h1  (1)\n"
                  b"      Bijan Robinson       Yes                              +130  43.5%\n"
                  b"  player_receptions  (1)\n"
                  b"      Drake London         Over                      5.5   -140  0.0%\n"))
    os.close(fd)
    got = parse(p)
    ck(len(got) == 3, f"three lines, not the first-half block or receptions: {got}")
    ck(("Atlanta Falcons Defe", "Yes", 700) in got,
       f"a name that FILLS the column leaves one space, not two: {got}")
    ck(("Bijan Robinson", "Yes", -210) in got, f"the price must be signed: {got}")
    ck(not any(g[2] == 130 for g in got),
       f"the FIRST-HALF block must not leak in -- same player, different "
       f"market, half the chance: {got}")
    os.unlink(p)
    # name resolution
    lg = {("bijan robinson", "RB"): [], ("brian robinson", "RB"): [],
          ("atlanta falcons defense", "RB"): [], ("chris olave", "WR"): []}
    ck(resolve("Brian Robinson Jr.", lg) == ("brian robinson", "RB"),
       "the suffix must not block the match")
    ck(resolve("Atlanta Falcons Defe", lg) == ("atlanta falcons defense", "RB"),
       "a truncated name with one candidate resolves")
    ck(resolve("Nobody At All", lg) is None, "an unknown name is refused")
    amb = dict(lg)
    amb[("brian robinson smith", "RB")] = []
    ck(resolve("Brian Robinson Jr", amb) == ("brian robinson", "RB"),
       "an exact match still wins when a longer name also exists")
    # the candidates must be LONGER than the truncated board name, or the
    # prefix branch is never reached and the assertion passes for free
    amb2 = {("atlanta falcons defense", "RB"): [],
            ("atlanta falcons defenders", "WR"): []}
    ck(len("Atlanta Falcons Defe") == NAME_W, "the fixture must be truncated")
    ck(resolve("Atlanta Falcons Defe", amb2) is None,
       f"a truncated name matching TWO players must be refused, not guessed: "
       f"{resolve('Atlanta Falcons Defe', amb2)}")
    one = {("atlanta falcons defense", "RB"): []}
    ck(resolve("Atlanta Falcons Defe", one) == ("atlanta falcons defense", "RB"),
       "but one candidate still resolves")
    # the starter split: a player's games with a quarterback who is no longer
    # the starter must not reach the projection at all
    fd, sp = tempfile.mkstemp(suffix="")
    os.close(fd); os.unlink(sp); os.makedirs(sp)
    hdr = ("season_type,position,player_display_name,team,week,attempts,"
           "carries,targets,rushing_tds,receiving_tds\n")
    with open(os.path.join(sp, f"spw{CURRENT}.csv"), "w") as f:
        f.write(hdr)
        for w in (1, 2):
            f.write(f"REG,QB,Old Arm,ATL,{w},30,0,0,0,0\n")
        f.write(f"REG,QB,New Arm,ATL,3,30,0,0,0,0\n")
        for w in (1, 2, 3):
            f.write(f"REG,WR,Bench Guy,ATL,{w},0,0,4,0,0\n")
    with open(os.path.join(sp, f"spw{CURRENT-1}.csv"), "w") as f:
        f.write(hdr)
        # a quarterback who started LAST season and does not start now. If the
        # CURRENT filter goes, he becomes ATL's starter on week 17 > week 3.
        for w in (16, 17):
            f.write(f"REG,QB,Gone Arm,ATL,{w},30,0,0,0,0\n")
        for w in (16, 17):
            f.write(f"REG,WR,Bench Guy,ATL,{w},0,0,4,0,0\n")
    st = starters(sp)
    ck(st.get("ATL") and st["ATL"][0] == "New Arm",
       f"the starter is the most RECENT one, not the most frequent: {st}")
    ck(st["ATL"][2] == {(CURRENT, 3)},
       f"and only his own starts count: {st['ATL'][2]}")
    lg2 = logs([CURRENT], sp)
    g = lg2[("bench guy", "WR")]
    ck("Gone Arm" not in [v[0] for v in st.values()],
       f"last season's quarterback must not be anyone's starter now: {st}")
    lg3 = logs([CURRENT - 1, CURRENT], sp)
    allg = lg3[("bench guy", "WR")]
    ck(len(allg) == 5, f"he has five games on file in all: {allg}")
    kept = starter_games(allg, "ATL", st.get("ATL"))
    ck(len(kept) == 1,
       f"but only ONE with the current starter -- the other four belong to "
       f"quarterbacks who are not playing: {kept}")
    ck(project(kept, "WR", 0.0478) is None,
       "and one game must project nothing, with no fall back to the other four")
    ck(starter_games(allg, "ATL", None) == [],
       "no identified starter means no games, not all of them")
    ck(starter_games(allg, "NO", st.get("ATL")) == [],
       "and the team filter must hold too")
    for fn in os.listdir(sp):
        os.unlink(os.path.join(sp, fn))
    os.rmdir(sp)
    print("anytd selftest:", "FAILED" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    a = [x for x in sys.argv[1:] if not x.startswith("-")]
    sys.exit(main(a[0] if a else "sweep.txt"))

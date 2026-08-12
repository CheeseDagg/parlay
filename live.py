#!/usr/bin/env python3
"""live.py — in-game survival odds for a totals leg, without hand arithmetic.

    python3 live.py --line 9.5 --runs 9 --state B5
    python3 live.py --line 8.5 --runs 8 --state T2 --outs 2 --hot
    python3 live.py --line 9.5 --runs 7 --state M2 --others .97,.96,.92

Every number this prints was being derived by hand, live, message by message,
on 8/10 and 8/11 -- including once with Poisson, which RULES.md #17 exists to
forbid: Poisson says ~62% of half-innings are scoreless when the real rate is
~72%, and that error understated a live leg THREEFOLD the night it mattered.

MODEL. Per half-inning: scoreless with probability q (0.72 normal, 0.68 when
both starters are getting hit, --q to override), and a scoring half adds
1/2/3/4 runs with P = .55/.25/.12/.08 of the scoring mass -- coarse MLB
half-inning shape, consistent with the q it rides beside. Survival is the
probability the ADDED runs across the remaining halves stay within the
cushion, by direct convolution. Zero cushion collapses to q^K exactly, which
is the rule-17 formula.

STATE. T3 = top of the 3rd in progress, M3 = middle break, B3 = bottom in
progress, E3 = inning over. The F5 window ends after E5 -- and per rule 18
(pinned in TheTool's selftests), M5 is NOT settled: the home fifth can still
lose an under. An in-progress half counts through --outs: 0 outs is a full
half, 2 outs is a third of one.
"""
import sys

SCORING = {1: 0.55, 2: 0.25, 3: 0.12, 4: 0.08}   # runs added by a scoring half

def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default

def halves_left(state, outs=0):
    """(full_halves, partial_fraction) remaining in the F5 window."""
    kind, inn = state[0].upper(), int(state[1:])
    if inn > 5:
        return 0, 0.0
    rest = 2 * (5 - inn)
    part = (3 - outs) / 3.0
    if kind == 'T':
        return rest + 1, part          # bottom of this inning + later, plus now
    if kind == 'M':
        return rest + 1, 0.0           # the bottom half is whole and unplayed
    if kind == 'B':
        return rest, part
    if kind == 'E':
        return rest, 0.0
    raise ValueError(state)

def survival(cushion, full, part_frac, q):
    """P(added runs across the remaining halves <= cushion)."""
    if cushion < 0:
        return 0.0
    # dist[r] = P(exactly r runs added so far), truncated above cushion
    dist = [1.0] + [0.0] * cushion
    def convolve(zero_p):
        nonlocal dist
        nxt = [0.0] * (cushion + 1)
        score_mass = 1 - zero_p
        for r, p in enumerate(dist):
            if not p:
                continue
            nxt[r] += p * zero_p
            for k, w in SCORING.items():
                if r + k <= cushion:
                    nxt[r + k] += p * score_mass * w
        dist = nxt
    for _ in range(full):
        convolve(q)
    if part_frac > 0:
        # a partial half scores nothing with probability q**frac; the shape of
        # what it adds when it does score is the same as any half's
        convolve(q ** part_frac)
    return sum(dist)

def main():
    line = float(flag('line'))
    runs = int(flag('runs'))
    state = flag('state')
    outs = int(flag('outs', 0))
    q = float(flag('q', 0.68 if '--hot' in sys.argv else 0.72))
    cushion = int(line - runs) if line > runs else -1
    full, part = halves_left(state, outs)
    p = survival(cushion, full, part, q)
    tag = f"U{line} with {runs} in, {state}" + (f" {outs} out" if outs else "")
    print(f"{tag}: cushion {max(cushion,0)}, ~{full + (1 if part else 0)} halves left, q={q}")
    print(f"leg survival: {p*100:.1f}%")
    others = flag('others')
    if others:
        t = p
        for x in others.split(','):
            t *= float(x)
        print(f"ticket ({len(others.split(','))} other legs): {t*100:.2f}%")
    return 0

def selftest():
    ok = [0, 0]
    def chk(c, msg):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    chk(halves_left('E5') == (0, 0.0), "E5 -> nothing left, the leg is settled")
    chk(halves_left('M5') == (1, 0.0),
        "M5 -> ONE whole half left (rule 18: the middle of the 5th is not done)")
    chk(halves_left('B5', 0) == (0, 1.0), "B5, 0 outs -> just the half in progress")
    chk(halves_left('T2', 2) == (7, 1/3),
        "T2 with 2 outs -> seven whole halves plus a third of this one")
    chk(halves_left('T6') == (0, 0.0), "the 6th inning is outside the F5 window")

    chk(abs(survival(0, 1, 0, 0.72) - 0.72) < 1e-12,
        "zero cushion, one half = 0.72 exactly -- the rule-17 formula")
    chk(abs(survival(0, 8, 0, 0.68) - 0.68 ** 8) < 1e-12,
        "zero cushion, K halves, hot game = 0.68^K exactly (the 8/10 case)")
    chk(survival(-1, 4, 0, 0.72) == 0.0, "already past the line = dead, no waiting")
    chk(survival(50, 9, 0, 0.72) > 0.999, "a huge cushion is a formality")
    s1, s2 = survival(1, 6, 0, 0.72), survival(2, 6, 0, 0.72)
    chk(s2 > s1 > survival(0, 6, 0, 0.72), "survival rises with cushion, monotone")
    chk(survival(1, 6, 0, 0.72) > survival(1, 8, 0, 0.72),
        "and falls with more halves to sweat")
    # 8/11, the killer leg's last stand: U9.5, 9 in, bottom 5 to play, a game
    # running two runs an inning. q=0.6 was the number used live.
    p = survival(0, 1, 0, 0.60)
    chk(abs(p - 0.60) < 1e-12,
        f"the CHC@WSH B5 read reproduces ({p:.2f} -- it lost, and 40% of the "
        "time it loses is the honest statement of that)")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

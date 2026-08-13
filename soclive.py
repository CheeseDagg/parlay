#!/usr/bin/env python3
"""soclive.py — in-match probabilities for soccer legs, without hand arithmetic.

    python3 soclive.py --lh=1.9 --la=0.75 --score=0-1 --min=54
    python3 soclive.py --lh=1.9 --la=0.75 --score=0-1 --min=60 --red=home
    python3 soclive.py --league=soccer_sweden_allsvenskan --score=1-1 --min=78 --under=5.5
    python3 soclive.py --selftest

live.py exists because MLB in-game numbers were being derived by hand,
message by message, and rule 17 was written when a hand-Poisson understated
a live leg threefold. On 8/13 the identical failure happened in soccer:
Hammarby's double chance was re-derived ad hoc three times during the match
(85 pregame -> "~46" at 0-1 -> "~17" with the red card), each time with
different assumptions invented on the spot. This file is those numbers,
computed one way, tested against that day.

MODEL, and what is measured versus assumed:
  * goals arrive as independent Poissons per side (standard, imperfect --
    it ignores momentum and game-state effects; stated, not hidden);
  * a side's full-match lambda comes from --lh/--la, or from a league's
    measured mean (sococalib/sochist) split 55/45 home/away -- the split is
    an ASSUMPTION cited in the output, not a measurement;
  * remaining fraction is (90 + stoppage - minute)/90, stoppage default 4;
  * a red card multiplies the short side's rate by 0.65 and the full side's
    by 1.15 -- literature-shaped ASSUMPTION, printed whenever used.

Rule 18's shape applies here too: nothing is "safe" until it cannot lose.
An under with the line already passed prints 0 exactly; an under one goal
from the line prints the real survival, never a round-up.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME_SHARE = 0.55            # of a match's goals -- assumption, cited in output
RED_SHORT, RED_FULL = 0.65, 1.15
MAXG = 9                     # Poisson tail truncation for the remaining minutes


def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


def pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def league_lambdas(key):
    """(lh, la, source) from measured league means, or None if unmeasured."""
    for fname, path in (('sococalib.json', ('leagues',)), ('sochist.json', ('leagues',))):
        try:
            with open(os.path.join(HERE, fname)) as fh:
                d = json.load(fh)
        except Exception:
            continue
        leagues = d.get('leagues') or {}
        try:
            import socbase
            name = socbase.CALIB.get(key) or socbase.MAP.get(key)
        except Exception:
            name = None
        row = leagues.get(name) if name else None
        if row:
            mean = (row.get('mean_goals')
                    or (row.get('result') or {}).get('mean_goals'))
            if mean:
                return mean * HOME_SHARE, mean * (1 - HOME_SHARE), f'{name} ({fname})'
    return None


def state(lh, la, score, minute, red=None, stoppage=4):
    """Remaining-match rates and the current score, one place."""
    hs, as_ = (int(x) for x in score.split('-'))
    rem = max(0.0, (90 + stoppage - minute) / 90)
    rl, ra = lh * rem, la * rem
    if red == 'home':
        rl, ra = rl * RED_SHORT, ra * RED_FULL
    elif red == 'away':
        rl, ra = rl * RED_FULL, ra * RED_SHORT
    return rl, ra, hs, as_


def outcomes(rl, ra, hs, as_):
    """P(home win), P(draw), P(away win) from here to full time."""
    ph = pd_ = pa = 0.0
    for h in range(MAXG + 1):
        for a in range(MAXG + 1):
            p = pois(rl, h) * pois(ra, a)
            t = (hs + h) - (as_ + a)
            if t > 0:
                ph += p
            elif t == 0:
                pd_ += p
            else:
                pa += p
    return ph, pd_, pa


def under_p(rl, ra, hs, as_, line):
    """P(final total < line). Already past the line prints ZERO exactly --
    goals never come off the board, rule 18's soccer twin."""
    cur = hs + as_
    if cur > line:
        return 0.0
    lam = rl + ra
    room = int(math.floor(line - cur))       # more goals allowed, X.5 lines
    return sum(pois(lam, k) for k in range(room + 1))


def main():
    league = flag('league')
    if flag('lh') and flag('la'):
        lh, la, src = float(flag('lh')), float(flag('la')), 'given'
    elif league:
        got = league_lambdas(league)
        if not got:
            print(f"{league} has no measured mean -- pass --lh/--la explicitly "
                  "(coverage.json says which leagues are measured)")
            return 1
        lh, la, src = got
    else:
        print("need --lh/--la or --league"); return 2
    score, minute = flag('score', '0-0'), int(flag('min', '0'))
    red, stop = flag('red'), int(flag('stop', '4'))
    rl, ra, hs, as_ = state(lh, la, score, minute, red, stop)
    ph, pd_, pa = outcomes(rl, ra, hs, as_)
    print(f"lambdas {lh:.2f}/{la:.2f} ({src}; 55/45 home split is an assumption)"
          + (f"; RED {red}: x{RED_SHORT}/x{RED_FULL} assumed" if red else ''))
    print(f"score {hs}-{as_} at {minute}'+{stop} -> remaining rates {rl:.2f}/{ra:.2f}")
    print(f"  home win {ph*100:5.1f}%   draw {pd_*100:5.1f}%   away win {pa*100:5.1f}%")
    print(f"  home DC  {(ph+pd_)*100:5.1f}%   away DC {(pa+pd_)*100:5.1f}%")
    u = flag('under')
    if u:
        print(f"  Under {u}: {under_p(rl, ra, hs, as_, float(u))*100:5.1f}%")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    # The 8/13 Hammarby trajectory, computed ONE way instead of three.
    rl, ra, hs, as_ = state(1.9, 0.75, '0-0', 0)
    ph, pd_, pa = outcomes(rl, ra, hs, as_)
    chk(abs((ph + pd_) - 0.846) < 0.045,
        f"pregame: a 1.9/0.75 favourite's DC prices {(ph+pd_)*100:.1f}%, beside "
        "the 84.6% the odds implied on 8/13")
    rl, ra, hs, as_ = state(1.9, 0.75, '0-1', 54)
    ph54, pd54, _ = outcomes(rl, ra, hs, as_)
    chk(0.38 <= ph54 + pd54 <= 0.52,
        f"0-1 at 54': DC {(ph54+pd54)*100:.1f}% -- the coin flip it actually was")
    rl, ra, hs, as_ = state(1.9, 0.75, '0-1', 60, red='home')
    phr, pdr, _ = outcomes(rl, ra, hs, as_)
    chk(phr + pdr < (ph54 + pd54) - 0.10 and phr + pdr < 0.30,
        f"down a man it collapses to {(phr+pdr)*100:.1f}% -- the card cost "
        "double digits, which is what the ad-hoc 17% was gesturing at")

    rl, ra, hs, as_ = state(1.0, 1.0, '1-1', 90, stoppage=4)
    ph2, pd2, pa2 = outcomes(rl, ra, hs, as_)
    chk(pd2 > 0.85 and abs(ph2 - pa2) < 0.02,
        "level in the 90th, the draw dominates and the sides are symmetric")
    chk(abs(ph2 + pd2 + pa2 - 1) < 1e-9, "outcome probabilities sum to one")

    chk(under_p(0.5, 0.4, 4, 3, 6.5) == 0.0,
        "seven goals in: Under 6.5 prints ZERO exactly -- goals never come "
        "off the board, and a dead leg must never price as alive")
    u6 = under_p(0.5, 0.4, 3, 3, 6.5)
    chk(0 < u6 < 1 and abs(u6 - math.exp(-0.9)) < 1e-9,
        "six goals in: Under 6.5 is exactly P(no more goals), never 'safe'")
    chk(under_p(0.3, 0.3, 0, 0, 2.5) > under_p(0.3, 0.3, 1, 1, 2.5),
        "the same line with goals already in is strictly worse")

    r0 = state(2.0, 1.0, '0-0', 70)
    r1 = state(2.0, 1.0, '0-0', 70, red='away')
    chk(r1[0] > r0[0] and r1[1] < r0[1],
        "a red to the away side raises the home rate and cuts the away rate, "
        "and the output names both multipliers as assumptions")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

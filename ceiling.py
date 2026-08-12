"""Best FanDuel ticket whose TOTAL price is no longer than a cap.

This is the mirror image of solve2.py and it needs its own solver, not a flag.
solve2 maximises hit probability subject to price >= a floor, and its price
buckets saturate at the target because anything above the floor is equally
acceptable. Here the constraint runs the other way: a Bet Reset token that caps
at -200 makes price something you must not EXCEED, and saturation would throw
away exactly the information the cap needs.

A pure ceiling is degenerate -- the empty ticket has price 1.00 and probability
1.00, so "maximise p subject to d <= cap" is solved by betting nothing. The
real objective is to spend the whole allowance: get as close to the cap as
possible from underneath, and among the tickets that land in that window, take
the one most likely to win. So the constraint is a WINDOW, [lo, hi], and the
DP keeps exact price buckets rather than saturating.

  usage: python3 ceiling.py FanDuel -200 --maxlegs=6
         python3 ceiling.py FanDuel -200 --maxlegs=6 --maxmlb=0
         (started legs are excluded by default; --anytime lifts that)

Bucket arithmetic mirrors solve2: db uses FLOOR, so a leg's price contribution
is understated and the reported total is a lower bound. That is the safe
direction against a floor and the WRONG direction against a ceiling, so the
window's upper edge is checked against the true product at the end, not against
the bucket index.
"""
import math, sys
from collections import Counter
import numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import board
from board import build
from times import ct

BOOK = sys.argv[1] if len(sys.argv) > 1 else 'FanDuel'
CAP_AM = float(sys.argv[2]) if len(sys.argv) > 2 else -200.0
CAP = 1 + (CAP_AM / 100 if CAP_AM > 0 else 100 / -CAP_AM)
STEP, NEG = 0.0005, -1e18


def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


MAXLEGS = int(flag('maxlegs', 6))
MAXMLB = int(flag('maxmlb', MAXLEGS))
FLOORFRAC = float(flag('floorfrac', 0.97))   # how much of the cap must be used
MINPRICE = int(flag('minprice', 0))

# ON BY DEFAULT, for the reason spelled out in solve2.py: a started game is not
# bettable, so excluding it is what "candidate leg" means rather than a flag to
# remember. Forgetting --now here produced a finished ticket that looked exactly
# like a live one. --anytime lifts it explicitly; --now is a no-op alias.
CUTOFF = None if '--anytime' in sys.argv else board._utcnow()

# --by=YYYY-MM-DD: see the note on board.build's `horizon`. A ceiling ticket is
# the one a promo token gets spent on, which makes the horizon MORE important
# here than in solve2, not less -- a token that expires this week is worth
# nothing against a leg that does not settle until October.
HORIZON = flag('by', None)

markets = build(BOOK, no_plus='--allow-plus' not in sys.argv,
                min_price=MINPRICE, cutoff=CUTOFF, horizon=HORIZON)
if board.FEED_DEAD:
    print("  ceiling: not one leg in the raw pool is still to come. Anything "
          "printed below is a question about a board that has already resolved.")

NB = int(math.floor(math.log(CAP) / STEP)) + 1      # exact, no saturation
LO = int(math.floor(math.log(CAP * FLOORFRAC) / STEP))
keys = sorted(markets)
for k in keys:
    for o in markets[k]:
        o['db'] = int(math.floor(math.log(o['d']) / STEP))

# A[mi][n, b, m] would be a fourth axis for the baseball cap; instead, as in
# solve2, split the pools and convolve. Here the tables are small enough that
# the split costs nothing.
POOLS = {'MLB': [k for k in keys if markets[k][0]['sport'] == 'MLB'],
         'OTH': [k for k in keys if markets[k][0]['sport'] != 'MLB']}


def tables(ks):
    A = np.full((MAXLEGS + 1, NB), NEG); A[0, 0] = 0.0
    snaps = [A.copy()]
    for k in ks:
        cur = A.copy()
        for o in markets[k]:
            db, lp = o['db'], math.log(o['p'])
            if db >= NB:
                continue
            src = A[:-1]
            sh = np.full_like(src, NEG)
            sh[:, db:] = src[:, :NB - db] if db else src
            cur[1:] = np.maximum(cur[1:], np.where(sh < NEG / 2, NEG, sh + lp))
        A = cur; snaps.append(A.copy())
    return snaps


def rebuild(ks, snaps, n, b):
    pick = []
    for mi in range(len(ks), 0, -1):
        if n == 0:
            break
        if abs(snaps[mi][n, b] - snaps[mi - 1][n, b]) < 1e-9:
            continue
        for o in markets[ks[mi - 1]]:
            if o['db'] > b:
                continue
            if abs(snaps[mi][n, b] - (math.log(o['p']) +
                                      snaps[mi - 1][n - 1, b - o['db']])) < 1e-9:
                pick.append(o); n, b = n - 1, b - o['db']; break
        else:
            sys.exit(f"reconstruction failed at {ks[mi - 1]}")
    return pick


sO, sM = tables(POOLS['OTH']), tables(POOLS['MLB'])
AO, AM = sO[-1], sM[-1]

best = (NEG, None, None, None, None)
for no in range(MAXLEGS + 1):
    for nm in range(min(MAXMLB, MAXLEGS - no) + 1):
        if no + nm == 0:
            continue
        for bo in range(NB):
            if AO[no, bo] < NEG / 2:
                continue
            for bm in range(NB - bo):
                if AM[nm, bm] < NEG / 2:
                    continue
                b = bo + bm
                if b < LO:
                    continue
                v = AO[no, bo] + AM[nm, bm]
                if v > best[0]:
                    best = (v, no, bo, nm, bm)

if best[0] < NEG / 2:
    sys.exit(f"No {BOOK} ticket lands inside the window under {CAP_AM:g}.")

val, no, bo, nm, bm = best
pick = rebuild(POOLS['OTH'], sO, no, bo) + rebuild(POOLS['MLB'], sM, nm, bm)

jp = jd = 1.0
for v in pick:
    jp *= v['p']; jd *= v['d']
am = -100 / (jd - 1) if jd < 2 else (jd - 1) * 100
assert abs(math.log(jp) - val) < 1e-6, "replay != dp"
assert jd <= CAP + 1e-9, f"price {jd:.4f} over cap {CAP:.4f}"
assert len({v['lab'] for v in pick}) == len(pick), "duplicate leg"
if CUTOFF:
    assert all(v['t'] > CUTOFF for v in pick), "started leg on ticket"

pick.sort(key=lambda v: (v['t'], -v['p']))
print(f"{'='*92}\n{BOOK} -- total price no longer than {CAP_AM:g}, "
      f"max {MAXLEGS} legs, max {MAXMLB} baseball\n{'='*92}")
print(f"{'#':>2}  {'start (CT)':16s} {'leg':36s} {'price':>7s} {'p(hit)':>8s}  fam")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {ct(v['t']):16s} {v['lab']:36s} {v['price']:>+7d} "
          f"{v['p']:8.4f}  {v['fam']}")
print(f"\n  joint hit probability (independent): {jp*100:.2f}%")
print(f"  parlay price: {jd:.4f}x  = {am:+.0f}  ->  $200 returns ${jd*200:,.2f}")
print("  family mix: " + str(dict(Counter(v['fam'] for v in pick))))
c = Counter(v['grp'] for v in pick)
print("  correlated stacks: " +
      (", ".join(f"{k}({n})" for k, n in sorted(c.items()) if n > 1) or "none"))

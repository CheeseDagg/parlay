"""25-leg single-book solver with a cap on how many baseball legs may be used.

  usage: python3 solve2.py FanDuel 21.0 --now --minprice=200 --maxmlb=12
         python3 solve2.py FanDuel 21.0 --now --minprice=200 --sweep

Why this is not just solve.py with a filter: a cap on one sport is a second
knapsack constraint, and bolting it onto the price DP as a third axis costs
26 x 6092 x 26 floats per market snapshot -- gigabytes. But the two pools are
disjoint by construction (fights share no market key with baseball), so the
problem separates: build an exact "exactly n legs, price bucket b" table for
each pool independently, then convolve the two tables over the split.

Price buckets saturate at the target rather than being clamped per-leg. That
matters for the convolution: a pool that on its own already clears the target
must contribute "no further price needed" to the other pool, and saturation
encodes exactly that, whereas per-leg clamping does not compose.

db uses FLOOR, not round, so every leg's price contribution is understated.
The reported price is therefore a lower bound on the true one -- the ticket can
come in above target, never below. The assertion at the end checks it for real.
"""
import math, sys
from collections import Counter
import numpy as np
sys.path.insert(0, '/root/parlay')
import board
from board import build
from times import et

BOOK   = sys.argv[1] if len(sys.argv) > 1 else 'FanDuel'
TARGET = float(sys.argv[2]) if len(sys.argv) > 2 else 21.0
STEP, NEG = 0.0005, -1e18

def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default

# Leg count is a real lever, not cosmetics: fewer legs means each one has to buy
# more price to reach the same target, so a shorter ticket forces LIGHTER
# favourites. Shrinking the ticket and tightening the price floor pull opposite
# ways and both cannot be maximised at once.
N_LEGS = int(flag('legs', 25))

CUTOFF = None
if '--now' in sys.argv:
    from datetime import datetime, timezone
    CUTOFF = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
MINPRICE = int(flag('minprice', 0))
# A promo token can cap how heavy each leg may be. That is a per-leg CEILING,
# the exact mirror of the floor, and it has to be applied at pool construction
# for the same reason: filtering afterwards edits the answer, filtering first
# changes what is being optimised.
MAXPRICE = int(flag('maxprice', 0))
MAXMLB   = int(flag("maxmlb", N_LEGS))
DROP     = set(filter(None, (flag('drop', '') or '').split(',')))
DROPFAM  = set(filter(None, (flag('nofam', '') or '').split(',')))
DROPLAB  = [x for x in (flag('noleg', '') or '').split(',') if x]
# --mlagree keeps only those moneyline legs the MLB model has an opinion on AND
# agrees with. It is a selection filter, not a repricing: the leg's quoted
# probability stays the de-vigged market number either way.
MLAGREE  = '--mlagree' in sys.argv
# --power re-runs the whole optimisation believing heavy favourites are worth
# more than proportional de-vig says. If the heavy-favourite structure is being
# unfairly penalised, this is where it shows up: the solver is free to rebuild
# the ticket under the assumption that flatters it.
board.METHOD = 'power' if '--power' in sys.argv else 'mult'

markets = build(BOOK, no_plus='--allow-plus' not in sys.argv,
                min_price=MINPRICE, cutoff=CUTOFF, drop=DROP,
                max_price=MAXPRICE, drop_fam=DROPFAM, drop_lab=DROPLAB,
                nostack='--nostack' in sys.argv)

if MLAGREE:
    for k in list(markets):
        markets[k] = [o for o in markets[k]
                      if o['fam'] != 'ML' or (o.get('mp') or 0) > 0.5]
        if not markets[k]:
            del markets[k]

NBT = int(math.ceil(math.log(TARGET) / STEP)); NB = NBT + 1
for k in markets:
    for o in markets[k]:
        o['db'] = min(int(math.floor(math.log(o['d']) / STEP)), NBT)

# The split is baseball vs NOT baseball, not baseball vs fights. Once boxing,
# WNBA, tennis, CFL and soccer joined the board the second pool stopped being
# "the MMA card" and became "everything whose price is not driven by a
# run-scoring process" -- which is also exactly the set that is uncorrelated
# with the MLB legs, so the convolution argument is unchanged.
POOLS = {'MLB':   sorted(k for k in markets if markets[k][0]['sport'] == 'MLB'),
         'FIGHT': sorted(k for k in markets if markets[k][0]['sport'] != 'MLB')}


def tables(keys):
    """A[mi] = value after considering the first mi markets.
    A[mi][n, b] = max sum log p using exactly n legs, price bucket b saturating
    at NBT. Snapshots kept so the pick can be reconstructed backwards."""
    A = np.full((N_LEGS + 1, NB), NEG); A[0, 0] = 0.0
    snaps = [A.copy()]
    for k in keys:
        cur = A.copy()
        for o in markets[k]:
            db, lp = o['db'], math.log(o['p'])
            src = A[:-1]
            sh = np.full_like(src, NEG)
            if db == 0:
                sh[:] = src
            else:
                if db < NB:
                    sh[:, db:] = src[:, :NB - db]
                # everything that would land past the target saturates onto it
                sh[:, NBT] = np.maximum(sh[:, NBT], src[:, NB - db:].max(axis=1)
                                        if NB - db < NB else NEG)
            cur[1:] = np.maximum(cur[1:], np.where(sh < NEG / 2, NEG, sh + lp))
        A = cur; snaps.append(A.copy())
    return snaps


def rebuild(keys, snaps, n, b):
    """Walk the snapshots backwards, peeling off one market at a time."""
    pick = []
    for mi in range(len(keys), 0, -1):
        if n == 0:
            break
        if abs(snaps[mi][n, b] - snaps[mi - 1][n, b]) < 1e-9:
            continue
        for o in markets[keys[mi - 1]]:
            db, lp = o['db'], math.log(o['p'])
            lo = b - db if b < NBT else max(0, NBT - db)
            hi = b - db if b < NBT else NBT
            for pb in range(max(0, lo), hi + 1):
                if abs(snaps[mi][n, b] - (lp + snaps[mi - 1][n - 1, pb])) < 1e-9:
                    pick.append(o); n, b = n - 1, pb; break
            else:
                continue
            break
        else:
            sys.exit(f"reconstruction failed at {keys[mi - 1]}")
    return pick


snapM, snapF = tables(POOLS['MLB']), tables(POOLS['FIGHT'])
AM, AF = snapM[-1], snapF[-1]
# suffix max over price so "at least this much price" is one lookup
SM = np.maximum.accumulate(AM[:, ::-1], axis=1)[:, ::-1]

n_fight_markets = len(POOLS['FIGHT'])


def best_for(min_fight):
    best = (NEG, None, None)
    for m in range(min_fight, min(n_fight_markets, N_LEGS) + 1):
        nm = N_LEGS - m
        if nm > len(POOLS['MLB']):
            continue
        for b1 in range(NB):
            v1 = AF[m, b1]
            if v1 < NEG / 2:
                continue
            need = max(0, NBT - b1)
            v = v1 + SM[nm, need]
            if v > best[0]:
                best = (v, m, b1)
    return best


if '--sweep' in sys.argv:
    print(f"{BOOK}  >= {TARGET:g}x, {N_LEGS} legs, all legs -{MINPRICE} or heavier"
          if MINPRICE else f"{BOOK}  >= {TARGET:g}x, {N_LEGS} legs")
    print(f"{'other':>7s} {'baseball':>9s} {'hit prob':>10s}")
    for m in range(0, min(n_fight_markets, N_LEGS) + 1):
        nm = N_LEGS - m
        if nm > len(POOLS['MLB']):
            continue
        v = max((AF[m, b1] + SM[nm, max(0, NBT - b1)] for b1 in range(NB)
                 if AF[m, b1] > NEG / 2), default=NEG)
        if v > NEG / 2:
            print(f"{m:>7d} {nm:>9d} {math.exp(v)*100:>9.2f}%")
    sys.exit()

MIN_FIGHT = max(0, N_LEGS - MAXMLB)
val, m, b1 = best_for(MIN_FIGHT)
if val < NEG / 2:
    sys.exit(f"No {N_LEGS}-leg {BOOK} ticket meets these constraints.")

need = max(0, NBT - b1)
b2 = int(np.argmax(AM[N_LEGS - m, need:] >= SM[N_LEGS - m, need] - 1e-12)) + need
pick = rebuild(POOLS['FIGHT'], snapF, m, b1) + \
       rebuild(POOLS['MLB'], snapM, N_LEGS - m, b2)

jp = jd = 1.0
for v in pick:
    jp *= v['p']; jd *= v['d']
assert len(pick) == N_LEGS, f"got {len(pick)} legs"
assert abs(math.log(jp) - val) < 1e-6, f"replay {math.log(jp)} != dp {val}"
assert jd >= TARGET, f"price {jd:.3f}x under target"
assert len({v['lab'] for v in pick}) == N_LEGS, "duplicate leg"
if MINPRICE:
    assert all(v['price'] <= -MINPRICE for v in pick), "leg under price floor"
if MAXPRICE:
    assert all(v['price'] >= -MAXPRICE for v in pick), "leg over price ceiling"
assert sum(1 for v in pick if v['sport'] == 'MLB') <= MAXMLB, "mlb cap broken"
if CUTOFF:
    assert all(v['t'] > CUTOFF for v in pick), "started leg on ticket"

pick.sort(key=lambda v: (v['t'], -v['p']))
hdr = f"{BOOK} -- {N_LEGS} legs, >= {TARGET:g}x, max {MAXMLB} baseball"
if MINPRICE:
    hdr += f", every leg -{MINPRICE} or heavier"
if MAXPRICE:
    hdr += f", every leg -{MAXPRICE} or longer"
print(f"{'='*98}\n{hdr}\n{'='*98}")
print(f"{'#':>2}  {'start (ET)':12s} {'leg':36s} {'price':>7s} {'p(hit)':>8s}  fam")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {et(v['t']):12s} {v['lab']:36s} {v['price']:>+7d} {v['p']:8.4f}  {v['fam']}")
print(f"\n  joint hit probability (independent): {jp:.4f} = {jp*100:.2f}%")
print(f"  parlay price: {jd:.2f}x  (+{round((jd-1)*100)})  ->  $100 returns ${jd*100:,.2f}")
c = Counter(v['grp'] for v in pick)
print("  correlated stacks: " + (", ".join(f"{k}({n})" for k, n in sorted(c.items())
      if n > 1 and v and not k.startswith(('UFC', 'PFL', 'REG'))) or "none"))
print("  family mix: " + str(dict(Counter(v['fam'] for v in pick))))
print(f"  sports: {sum(1 for v in pick if v['sport']!='MLB')} non-baseball, "
      f"{sum(1 for v in pick if v['sport']=='MLB')} baseball")

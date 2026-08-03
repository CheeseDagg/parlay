"""FanDuel, 25 legs, priced at 20-1 or better -- and of every such ticket, the
one most likely to hit.

The unconstrained build maximises probability and lands at 5.26x. Forcing 21.0x
is a real constraint, so this is a constrained optimisation, not a re-sort:
choose exactly 25 legs from the posted FanDuel ladder, at most one per market,
maximising sum(log p) subject to sum(log decimal) >= log(21).

Solved exactly by DP rather than greedily. A greedy "swap in the longest legs
until the price clears" walk gets a materially worse ticket, because the leg
worth lengthening is the one where the model disagrees with the price most, and
that is not the same as the one with the biggest price.

The DP runs backwards over markets and carries "log-price still needed",
clamped at zero. Reconstruction then walks FORWARD and re-derives the same
value, so a mis-clamped bucket shows up as a mismatch instead of as a silently
wrong ticket.
"""
import json, math, sys
import numpy as np
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF

TARGET_DEC = 21.0          # 20-to-1
N_LEGS     = 25
STEP       = 0.0005

def dec(am):
    am = float(am)
    return 1 + (am / 100 if am > 0 else 100 / -am)

def pois_sf(k, lam):
    t = math.exp(-lam); c = t
    for i in range(1, int(k) + 1):
        t *= lam / i; c += t
    return 1 - c

def devig(yes, no):
    a, b = 1 / dec(yes), 1 / dec(no)
    return a / (a + b)

FD_K = open('/root/parlay/fd_k_ladder.txt').read()

LAM = {b['pitcher']: b['lam'] for b in json.load(
    open('/root/MLBTool/mlb/data/kprops.json'))['board']}

markets = {}
for line in FD_K.strip().splitlines():
    if not line.strip(): continue
    p, pt, price = line.split('|')
    pt = float(pt)
    markets.setdefault(('K', p), []).append({
        'p': pois_sf(int(pt - 0.5), LAM[p]), 'd': dec(price),
        'lab': f"{p} {int(pt+0.5)}+ Ks", 'price': int(price),
        'game': GAME_OF.get(p, '?')})

for line in TOTALS_RAW.strip().splitlines():
    if not line.strip(): continue
    g, bk, pt, over, under = line.split('|')
    if bk != 'FanDuel':
        continue
    markets.setdefault(('TOT', g), []).append({
        'p': devig(int(under), int(over)), 'd': dec(int(under)),
        'lab': f"{g} Under {pt}", 'price': int(under), 'game': g})

keys = sorted(markets)
M = len(keys)
NBT = int(math.ceil(math.log(TARGET_DEC) / STEP))
NB = NBT + 1
NEG = -1e18

for k in keys:
    for o in markets[k]:
        o['db'] = min(int(round(math.log(o['d']) / STEP)), NBT)

# g[n][b] for the current suffix: best sum log p using n more legs and needing
# b more buckets of log-price. b == 0 means the price requirement is already met.
g = np.full((N_LEGS + 1, NB), NEG)
g[0, 0] = 0.0
suffix = [None] * (M + 1)
suffix[M] = g.copy()

for mi in range(M - 1, -1, -1):
    nxt = suffix[mi + 1]
    cur = nxt.copy()                                  # skip this market
    for o in markets[keys[mi]]:
        db, lp = o['db'], math.log(o['p'])
        # take[n][b] = lp + nxt[n-1][max(0, b-db)]
        src = nxt[:-1]                                # counts 0..N-1
        shifted = np.empty_like(src)
        if db == 0:
            shifted[:] = src
        else:
            shifted[:, :db + 1] = src[:, 0][:, None]
            if db + 1 < NB:
                shifted[:, db + 1:] = src[:, 1:NB - db]
        take = np.where(shifted < NEG / 2, NEG, shifted + lp)
        cur[1:] = np.maximum(cur[1:], take)
    suffix[mi] = cur

best = suffix[0][N_LEGS, NBT]
if best < NEG / 2:
    sys.exit(f"No 25-leg FanDuel ticket reaches {TARGET_DEC}x.")

# --- forward reconstruction, re-deriving the DP value at each step
pick, n, b = [], N_LEGS, NBT
for mi in range(M):
    if n == 0:
        break
    if abs(suffix[mi][n, b] - suffix[mi + 1][n, b]) < 1e-9:
        continue                                       # skipping is optimal here
    for o in markets[keys[mi]]:
        nb = max(0, b - o['db'])
        if abs(suffix[mi][n, b] - (math.log(o['p']) + suffix[mi + 1][n - 1, nb])) < 1e-9:
            pick.append(o); n, b = n - 1, nb
            break
    else:
        sys.exit(f"reconstruction failed at market {keys[mi]}")

jp = 1.0; jd = 1.0
for v in pick:
    jp *= v['p']; jd *= v['d']
assert len(pick) == N_LEGS, f"got {len(pick)} legs"
assert abs(math.log(jp) - best) < 1e-6, f"replay {math.log(jp)} != dp {best}"
assert jd >= TARGET_DEC, f"price {jd:.3f}x is under target"
assert len({(v['lab'].split(' ')[0], v['game']) for v in pick}) <= N_LEGS

pick.sort(key=lambda v: -v['p'])
print(f"{'='*92}\nFanDuel -- 25 legs, most likely ticket that still pays 20-1\n{'='*92}")
print(f"{'#':>2}  {'leg':32s} {'game':10s} {'price':>7s} {'p(hit)':>8s}")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {v['lab']:32s} {v['game']:10s} {v['price']:>+7d} {v['p']:8.4f}")
am = round((jd - 1) * 100)
print(f"\n  joint hit probability (independent): {jp:.4f} = {jp*100:.2f}%")
print(f"  parlay price: {jd:.2f}x  (+{am})  ->  $100 returns ${jd*100:,.2f}")
print(f"  fair price at model p: {1/jp:.2f}x    EV per $100: ${jp*jd*100-100:+.2f}")
from collections import Counter
c = Counter(v['game'] for v in pick)
print("  same-game stacks: " + ", ".join(f"{g}({n})" for g, n in sorted(c.items()) if n > 1))

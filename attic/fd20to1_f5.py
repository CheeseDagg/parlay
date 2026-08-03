"""FanDuel, 25 legs, >= 20-1, most likely to hit -- now with first-five totals.

Same exact DP as fd20to1.py (backward suffix over markets carrying "log-price
still needed", forward reconstruction that re-derives the value at each step).
The only change is the candidate pool.

Three market families now:
  K    -- alternate pitcher strikeout Overs, Poisson off kprops lambda
  TOT  -- full-game alternate totals, de-vigged from the matched pair
  F5   -- first-five alternate totals, de-vigged from the matched pair

MERGE POLICY (this is the substantive modelling choice, not a detail):
by default the full-game total and the first-five total of the SAME GAME share
one market key, so the solver may take at most one of them. They are not
nested, but they are the same underlying run-scoring process measured twice --
holding both is close to holding one leg and paying for two, and it is exactly
the kind of pair FanDuel's SGP+ engine reprices hardest. Pass --split to let
the solver hold both and see what that buys.

Both sides of every total are offered to the solver. Deep Unders are where the
probability is; low Overs are where the cheap price is. Which one the ticket
actually wants is a question about the shape of the constraint, so it is left
to the optimiser rather than pre-decided by me.
"""
import json, math, sys
import numpy as np
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF
from f5 import F5_RAW

TARGET_DEC = float(sys.argv[1]) if len(sys.argv) > 1 else 21.0
SPLIT      = '--split' in sys.argv
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

LAM = {b['pitcher']: b['lam'] for b in json.load(
    open('/root/MLBTool/mlb/data/kprops.json'))['board']}

markets = {}

# ---- K legs
for line in open('/root/parlay/fd_k_ladder.txt').read().strip().splitlines():
    if not line.strip(): continue
    p, pt, price = line.split('|')
    pt = float(pt)
    markets.setdefault(('K', p), []).append({
        'p': pois_sf(int(pt - 0.5), LAM[p]), 'd': dec(price),
        'lab': f"{p} {int(pt+0.5)}+ Ks", 'price': int(price),
        'game': GAME_OF.get(p, '?'), 'fam': 'K'})

# ---- full-game totals (FanDuel only)
for line in TOTALS_RAW.strip().splitlines():
    if not line.strip(): continue
    g, bk, pt, over, under = line.split('|')
    if bk != 'FanDuel': continue
    key = ('TOT', g) if SPLIT else ('GT', g)
    markets.setdefault(key, []).append({
        'p': devig(int(under), int(over)), 'd': dec(int(under)),
        'lab': f"{g} Under {pt}", 'price': int(under), 'game': g, 'fam': 'FG'})
    markets.setdefault(key, []).append({
        'p': devig(int(over), int(under)), 'd': dec(int(over)),
        'lab': f"{g} Over {pt}", 'price': int(over), 'game': g, 'fam': 'FG'})

# ---- first-five totals (FanDuel only)
for line in F5_RAW.strip().splitlines():
    if not line.strip(): continue
    g, pt, over, under = line.split('|')
    key = ('F5', g) if SPLIT else ('GT', g)
    markets.setdefault(key, []).append({
        'p': devig(int(under), int(over)), 'd': dec(int(under)),
        'lab': f"{g} F5 Under {pt}", 'price': int(under), 'game': g, 'fam': 'F5'})
    markets.setdefault(key, []).append({
        'p': devig(int(over), int(under)), 'd': dec(int(over)),
        'lab': f"{g} F5 Over {pt}", 'price': int(over), 'game': g, 'fam': 'F5'})

# a leg with p == 0 or d <= 1 is not a leg
for k in markets:
    markets[k] = [o for o in markets[k] if o['p'] > 1e-9 and o['d'] > 1.0]

keys = sorted(markets)
M = len(keys)
NBT = int(math.ceil(math.log(TARGET_DEC) / STEP))
NB = NBT + 1
NEG = -1e18

for k in keys:
    for o in markets[k]:
        o['db'] = min(int(round(math.log(o['d']) / STEP)), NBT)

g = np.full((N_LEGS + 1, NB), NEG); g[0, 0] = 0.0
suffix = [None] * (M + 1); suffix[M] = g.copy()

for mi in range(M - 1, -1, -1):
    nxt = suffix[mi + 1]
    cur = nxt.copy()                                  # skip this market
    for o in markets[keys[mi]]:
        db, lp = o['db'], math.log(o['p'])
        src = nxt[:-1]
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

pick, n, b = [], N_LEGS, NBT
for mi in range(M):
    if n == 0: break
    if abs(suffix[mi][n, b] - suffix[mi + 1][n, b]) < 1e-9:
        continue
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
assert len({v['lab'] for v in pick}) == N_LEGS, "duplicate leg"

pick.sort(key=lambda v: -v['p'])
mode = "split FG/F5" if SPLIT else "one total per game"
print(f"{'='*96}\nFanDuel -- 25 legs, >= {TARGET_DEC:.0f}x, max hit probability  [{mode}]\n{'='*96}")
print(f"{'#':>2}  {'leg':34s} {'game':10s} {'price':>7s} {'p(hit)':>8s}  fam")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {v['lab']:34s} {v['game']:10s} {v['price']:>+7d} {v['p']:8.4f}  {v['fam']}")
am = round((jd - 1) * 100)
print(f"\n  joint hit probability (independent): {jp:.4f} = {jp*100:.2f}%")
print(f"  parlay price: {jd:.2f}x  (+{am})  ->  $100 returns ${jd*100:,.2f}")
from collections import Counter
c = Counter(v['game'] for v in pick)
print("  legs per game >1: " + ", ".join(f"{g}({k})" for g, k in sorted(c.items()) if k > 1))
print("  family mix: " + str(dict(Counter(v['fam'] for v in pick))))

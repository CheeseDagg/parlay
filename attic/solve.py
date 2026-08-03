"""One 25-leg single-book ticket solver. Four market families, either book,
optional minimum price.

  usage: python3 solve.py FanDuel 21.0
         python3 solve.py DraftKings 1.001

Families:
  K   alternate pitcher strikeout Overs   -- Poisson off kprops lambda
  GT  full-game + first-five alt totals   -- de-vigged matched pair
  MMA fight moneylines                    -- de-vigged matched pair

Market keys, i.e. what the solver may take at most one of:
  ('K', pitcher)  -- the strikeout ladder is nested, one rung only
  ('GT', game)    -- full-game AND first-five share a key. They are not nested,
                     but they are one run-scoring process measured twice, and
                     they are exactly the pair an SGP+ engine reprices hardest.
  ('F', fight)    -- both fighters, so the solver cannot take both sides

MMA legs are the only ones on the board uncorrelated with everything else, so
they are also the only ones whose contribution to the displayed price survives
the book's same-game repricing intact.

Exact DP: backward suffix over markets carrying "log-price still needed"
(clamped at 0), forward reconstruction that re-derives the DP value at each
step so a mis-clamp surfaces as a mismatch rather than a silently wrong ticket.
"""
import json, math, sys
from collections import Counter
import numpy as np
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF
from f5 import F5_RAW
from mma import MMA_RAW
from times import START, FIGHT_START, et

BOOK       = sys.argv[1] if len(sys.argv) > 1 else 'FanDuel'
TARGET_DEC = float(sys.argv[2]) if len(sys.argv) > 2 else 1.001
N_LEGS, STEP = 25, 0.0005

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
def add(key, **kw):
    markets.setdefault(key, []).append(kw)

# ---- K legs
if BOOK == 'FanDuel':
    for line in open('/root/parlay/fd_k_ladder.txt').read().strip().splitlines():
        if not line.strip(): continue
        p, pt, price = line.split('|')
        add(('K', p), p=pois_sf(int(float(pt) - 0.5), LAM[p]), d=dec(price),
            lab=f"{p} {int(float(pt)+0.5)}+ Ks", price=int(price),
            grp=GAME_OF.get(p, '?'), fam='K', t=START.get(GAME_OF.get(p, ''), 'Z'))
else:
    for line in open('/root/parlay/kraw.txt').read().strip().splitlines():
        if not line.strip(): continue
        bk, p, pt, price = line.split('|')
        if bk != BOOK or p not in LAM: continue
        add(('K', p), p=pois_sf(int(float(pt) - 0.5), LAM[p]), d=dec(price),
            lab=f"{p} {int(float(pt)+0.5)}+ Ks", price=int(price),
            grp=GAME_OF.get(p, '?'), fam='K', t=START.get(GAME_OF.get(p, ''), 'Z'))

# ---- full-game totals
for line in TOTALS_RAW.strip().splitlines():
    if not line.strip(): continue
    g, bk, pt, over, under = line.split('|')
    if bk != BOOK: continue
    add(('GT', g), p=devig(int(under), int(over)), d=dec(under),
        lab=f"{g} Under {pt}", price=int(under), grp=g, fam='FG', t=START[g])
    add(('GT', g), p=devig(int(over), int(under)), d=dec(over),
        lab=f"{g} Over {pt}", price=int(over), grp=g, fam='FG', t=START[g])

# ---- first-five totals (FanDuel only; DraftKings' F5 ladder stops at 5.5 and
#      its deepest leg de-vigs to .674, below every K leg already on that ticket)
if BOOK == 'FanDuel':
    for line in F5_RAW.strip().splitlines():
        if not line.strip(): continue
        g, pt, over, under = line.split('|')
        add(('GT', g), p=devig(int(under), int(over)), d=dec(under),
            lab=f"{g} F5 Under {pt}", price=int(under), grp=g, fam='F5', t=START[g])
        add(('GT', g), p=devig(int(over), int(under)), d=dec(over),
            lab=f"{g} F5 Over {pt}", price=int(over), grp=g, fam='F5', t=START[g])

# ---- MMA moneylines
for line in MMA_RAW.strip().splitlines():
    if not line.strip(): continue
    bk, card, who, price, opp = line.split('|')
    if bk != BOOK: continue
    add(('F', card, who), p=devig(int(price), int(opp)), d=dec(price),
        lab=f"{who} ML", price=int(price), grp=card, fam='MMA', t=FIGHT_START[who])
    add(('F', card, who), p=devig(int(opp), int(price)), d=dec(opp),
        lab=f"{who}'s opponent ML", price=int(opp), grp=card, fam='MMA', t=FIGHT_START[who])

# DROP LEGS THAT HAVE ALREADY STARTED. A leg whose game is underway is not
# bettable at the posted price, so it is not a candidate -- it has to come out
# of the pool BEFORE the DP runs, not get swapped out afterwards, or the solver
# is optimising against legs that do not exist. --now uses the wall clock;
# --drop=GAME,GAME removes named games regardless of time.
CUTOFF = None
if '--now' in sys.argv:
    from datetime import datetime, timezone
    CUTOFF = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
DROP = set()
for a in sys.argv:
    if a.startswith('--drop='):
        DROP |= set(a.split('=', 1)[1].split(','))

# NO PLUS MONEY. Every leg must be a negative American price, i.e. decimal < 2.0.
# This is a real constraint, not a filter on presentation: it removes the whole
# cheap-price tail the solver was using to reach 21x, so the remaining legs have
# to buy that price at worse |log p| / log d ratios. Expect the hit rate to fall.
NO_PLUS = '--allow-plus' not in sys.argv
for k in markets:
    markets[k] = [o for o in markets[k] if o['p'] > 1e-9 and o['d'] > 1.0
                  and not (NO_PLUS and o['price'] > 0)
                  and o['grp'] not in DROP
                  and not (CUTOFF and o['t'] <= CUTOFF)]
markets = {k: v for k, v in markets.items() if v}
if CUTOFF or DROP:
    gone = sorted(DROP) + ([f"anything starting before {et(CUTOFF)}"] if CUTOFF else [])
    print(f"[excluded: {', '.join(gone)}]")

keys = sorted(markets)
M = len(keys)
NBT = int(math.ceil(math.log(TARGET_DEC) / STEP)); NB = NBT + 1; NEG = -1e18
for k in keys:
    for o in markets[k]:
        o['db'] = min(int(round(math.log(o['d']) / STEP)), NBT)

g0 = np.full((N_LEGS + 1, NB), NEG); g0[0, 0] = 0.0
suffix = [None] * (M + 1); suffix[M] = g0.copy()
for mi in range(M - 1, -1, -1):
    nxt = suffix[mi + 1]
    cur = nxt.copy()
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
        cur[1:] = np.maximum(cur[1:], np.where(shifted < NEG / 2, NEG, shifted + lp))
    suffix[mi] = cur

best = suffix[0][N_LEGS, NBT]
if best < NEG / 2:
    sys.exit(f"No 25-leg {BOOK} ticket reaches {TARGET_DEC}x.")

pick, n, b = [], N_LEGS, NBT
for mi in range(M):
    if n == 0: break
    if abs(suffix[mi][n, b] - suffix[mi + 1][n, b]) < 1e-9: continue
    for o in markets[keys[mi]]:
        nb = max(0, b - o['db'])
        if abs(suffix[mi][n, b] - (math.log(o['p']) + suffix[mi + 1][n - 1, nb])) < 1e-9:
            pick.append(o); n, b = n - 1, nb; break
    else:
        sys.exit(f"reconstruction failed at market {keys[mi]}")

jp = jd = 1.0
for v in pick: jp *= v['p']; jd *= v['d']
assert len(pick) == N_LEGS, f"got {len(pick)} legs"
assert abs(math.log(jp) - best) < 1e-6, f"replay {math.log(jp)} != dp {best}"
assert jd >= TARGET_DEC, f"price {jd:.3f}x under target"
assert len({v['lab'] for v in pick}) == N_LEGS, "duplicate leg"

pick.sort(key=lambda v: (v['t'], -v['p']))
print(f"{'='*98}\n{BOOK} -- 25 legs, >= {TARGET_DEC:g}x, max hit probability\n{'='*98}")
print(f"{'#':>2}  {'start (ET)':12s} {'leg':36s} {'price':>7s} {'p(hit)':>8s}  fam")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {et(v['t']):12s} {v['lab']:36s} {v['price']:>+7d} {v['p']:8.4f}  {v['fam']}")
print(f"\n  joint hit probability (independent): {jp:.4f} = {jp*100:.2f}%")
print(f"  parlay price: {jd:.2f}x  (+{round((jd-1)*100)})  ->  $100 returns ${jd*100:,.2f}")
c = Counter(v['grp'] for v in pick)
print("  correlated stacks: " + (", ".join(f"{k}({n})" for k, n in sorted(c.items())
      if n > 1 and not k.startswith(('UFC', 'PFL', 'REG'))) or "none"))
print("  family mix: " + str(dict(Counter(v['fam'] for v in pick))))

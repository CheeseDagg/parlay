"""Best 25-leg single-book ticket for FanDuel and for DraftKings, 2026-07-31 MLB.

Ranked by probability of hitting, not by price. Two leg families:

  K legs     -- alternate pitcher strikeout Overs, priced off the kprops Poisson
                model (lambda = regressed K/9 x expected IP x opponent whiff mult).
  Total legs -- alternate game-total Unders, priced off the market itself by
                de-vigging the matched Over/Under pair. No home-grown run model:
                the closing total is better calibrated than anything I'd fit today.

Two different probability sources on one ticket is a real seam, so it is worth
saying which way each leans. The Poisson K model is mildly conservative at the
tail (real K counts are slightly under-dispersed), and multiplicative de-vig is
conservative on heavy favorites (it charges the favorite an equal share of the
vig when the empirical bias says the longshot side carries more of it). Both
errors point the same way: the numbers below are a floor, not a best guess.
"""
import json, math, sys
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF

def dec(am):
    am = float(am)
    return 1 + (am / 100 if am > 0 else 100 / -am)

def pois_sf(k, lam):
    """P(X > k) for integer k under Poisson(lam) -- i.e. P(Over k+0.5)."""
    t = math.exp(-lam); c = t
    for i in range(1, int(k) + 1):
        t *= lam / i; c += t
    return 1 - c

def devig(price_yes, price_no):
    """Multiplicative de-vig of a matched two-way pair -> P(yes)."""
    a, b = 1 / dec(price_yes), 1 / dec(price_no)
    return a / (a + b)

def power_devig(price_yes, price_no):
    """p_yes^k + p_no^k = 1. Assigns more of the vig to the longshot, which is
    what the favourite-longshot bias literature says actually happens. Reported
    alongside the multiplicative number so the spread between the two methods is
    visible rather than hidden inside one confident-looking decimal."""
    a, b = 1 / dec(price_yes), 1 / dec(price_no)
    lo, hi = 0.5, 4.0
    for _ in range(80):
        k = (lo + hi) / 2
        if a**k + b**k > 1: lo = k
        else: hi = k
    return a ** ((lo + hi) / 2)

# ---------------------------------------------------------------- K legs
KRAW = open('/root/parlay/kraw.txt').read()
board = json.load(open('/root/MLBTool/mlb/data/kprops.json'))['board']
LAM = {b['pitcher']: b['lam'] for b in board}
OPP = {b['pitcher']: b['opp'] for b in board}

kcand = {'FanDuel': {}, 'DraftKings': {}}
for line in KRAW.strip().splitlines():
    if not line.strip(): continue
    bk, p, pt, price = line.split('|')
    if p not in LAM:
        print('!! no model for', p); continue
    pt = float(pt)
    cur = kcand[bk].get(p)
    if cur is None or pt < cur['pt']:      # lowest line = highest hit probability
        kcand[bk][p] = {'pt': pt, 'price': int(price), 'p': pois_sf(int(pt - 0.5), LAM[p]),
                        'dec': dec(price), 'kind': 'K', 'name': p,
                        'game': GAME_OF.get(p, '?'), 'lab': f"{p} {int(pt+0.5)}+ Ks"}

# ------------------------------------------------------------ total legs
tot = {}
for line in TOTALS_RAW.strip().splitlines():
    if not line.strip(): continue
    g, bk, pt, over, under = line.split('|')
    tot.setdefault((bk, g), []).append((float(pt), int(over), int(under)))

tcand = {'FanDuel': {}, 'DraftKings': {}}
for (bk, g), rows in tot.items():
    # ONE under per game. Under 13.5 and Under 14.5 in the same game are nested,
    # not diversified -- holding both is just holding the lower one while paying
    # the book to pretend otherwise.
    best = None
    for pt, over, under in rows:
        p = devig(under, over)
        if best is None or p > best['p']:
            best = {'pt': pt, 'price': under, 'p': p, 'pw': power_devig(under, over),
                    'dec': dec(under), 'kind': 'TOT', 'name': g, 'game': g,
                    'lab': f"{g} Under {pt}"}
    tcand[bk][g] = best

# ------------------------------------------------------------------ build
def build(bk, n=25):
    pool = list(kcand[bk].values()) + list(tcand[bk].values())
    pool.sort(key=lambda v: -v['p'])
    return pool[:n], pool[n:]

for bk in ('DraftKings', 'FanDuel'):
    pick, drop = build(bk)
    print(f"\n{'='*94}\n{bk} -- 25 legs\n{'='*94}")
    print(f"{'#':>2}  {'leg':34s} {'game':10s} {'price':>7s} {'p(hit)':>8s}  src")
    jp = 1.0; jd = 1.0
    for i, v in enumerate(pick, 1):
        jp *= v['p']; jd *= v['dec']
        src = 'Poisson' if v['kind'] == 'K' else f"de-vig (power {v['pw']:.3f})"
        print(f"{i:2d}  {v['lab']:34s} {v['game']:10s} {v['price']:>7d} {v['p']:8.4f}  {src}")
    ks = sum(1 for v in pick if v['kind'] == 'K')
    print(f"\n  {ks} strikeout legs + {25-ks} game-total unders")
    print(f"  joint hit probability (independent): {jp:.4f}  = {jp*100:.1f}%")
    print(f"  parlay price: {jd:.2f}x  ->  $100 returns ${jd*100:,.2f}")
    # same-game overlaps
    from collections import Counter
    c = Counter(v['game'] for v in pick)
    dupes = {g: n for g, n in c.items() if n > 1 and g != '?'}
    if dupes:
        print("  same-game combinations (book will price these as SGP+, and the "
              "positive correlation\n    means true joint > the product above while "
              "the payout will be < the price above):")
        for g, n in sorted(dupes.items()):
            legs = [v['lab'] for v in pick if v['game'] == g]
            print(f"    {g}: {' + '.join(legs)}")
    print("  nearest misses: " + ", ".join(f"{v['lab']} ({v['p']:.3f})" for v in drop[:4]))

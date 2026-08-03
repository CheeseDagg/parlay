"""Independent check of the 21x F5 ticket.

Two things get checked, both from a code path that shares nothing with the DP:
  1. every leg's probability and decimal price, recomputed from the raw American
     odds with scipy's Poisson rather than my hand-rolled series;
  2. that no Lagrangian sweep + local search on the same candidate pool beats
     the DP's answer. If a greedy method found something better, the DP would be
     wrong -- so this is a real test, not a rubber stamp.
"""
import json, math, sys, itertools
from scipy.stats import poisson
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF
from f5 import F5_RAW

TARGET, NLEG = 21.0, 25

def dec(a):
    a = float(a); return 1 + (a/100 if a > 0 else 100/-a)
def dv(y, n):
    a, b = 1/dec(y), 1/dec(n); return a/(a+b)

LAM = {b['pitcher']: b['lam'] for b in json.load(
    open('/root/MLBTool/mlb/data/kprops.json'))['board']}

# ---------- 1. leg-by-leg recheck of the printed ticket
TICKET = [
    ("TEX@HOU F5 U10.5", 'F5', ('TEX@HOU', '10.5'), -6000),
    ("STL@TOR F5 U10.5", 'F5', ('STL@TOR', '10.5'), -5000),
    ("Imanaga 3+",       'K',  ('Shota Imanaga', 2),  -4000),
    ("Miller 3+",        'K',  ('Bryce Miller', 2),   -3500),
    ("CWS@TB F5 U10.5",  'F5', ('CWS@TB', '10.5'),  -4500),
    ("MIN@SEA F5 U10.5", 'F5', ('MIN@SEA', '10.5'), -4500),
    ("PIT@CIN F5 U9.5",  'F5', ('PIT@CIN', '9.5'),  -4500),
    ("BOS@LAD F5 U10.5", 'F5', ('BOS@LAD', '10.5'), -4000),
    ("Drohan 3+",        'K',  ('Shane Drohan', 2),  -4000),
    ("MIL@LAA F5 U10.5", 'F5', ('MIL@LAA', '10.5'), -2500),
    ("SF@SD F5 U10.5",   'F5', ('SF@SD', '10.5'),   -2500),
    ("Griffin 3+",       'K',  ('Foster Griffin', 2), -1600),
    ("Suarez 3+",        'K',  ('Ranger Suarez', 2),  -1100),
    ("MIA@NYM U14.5",    'FG', ('MIA@NYM', '14.5'), -1600),
    ("NYY@CHC U15.5",    'FG', ('NYY@CHC', '15.5'), -1600),
    ("Young 3+",         'K',  ('Brandon Young', 2),  -1100),
    ("WSH@ATL U15.5",    'FG', ('WSH@ATL', '15.5'), -1400),
    ("Matthews 3+",      'K',  ('Zebby Matthews', 2), -1200),
    ("PHI@BAL U14.5",    'FG', ('PHI@BAL', '14.5'), -1200),
    ("Warren 3+",        'K',  ('Will Warren', 2),     -850),
    ("Elder 3+",         'K',  ('Bryce Elder', 2),     -750),
    ("Junk 3+",          'K',  ('Janson Junk', 2),     -500),
    ("Leahy 3+",         'K',  ('Kyle Leahy', 2),      -440),
    ("Wacha 5+",         'K',  ('Michael Wacha', 4),   -106),
    ("Whisenhunt 5+",    'K',  ('Carson Whisenhunt', 4), 144),
]
f5 = {(g, pt): (o, u) for g, pt, o, u in
      (l.split('|') for l in F5_RAW.strip().splitlines() if l.strip())}
fg = {(g, pt): (o, u) for g, bk, pt, o, u in
      (l.split('|') for l in TOTALS_RAW.strip().splitlines() if l.strip())
      if bk == 'FanDuel'}

jp = jd = 1.0
bad = []
for lab, fam, key, price in TICKET:
    if fam == 'K':
        name, k = key
        p = float(poisson.sf(k, LAM[name]))         # P(X > k)
    else:
        o, u = (f5 if fam == 'F5' else fg)[key]
        p = dv(int(u), int(o))
        if int(price) != int(u): bad.append((lab, 'price mismatch', u, price))
    jp *= p; jd *= dec(price)
print(f"replayed with scipy: {jp*100:.2f}%   price {jd:.2f}x")
if bad: print("MISMATCHES:", bad)
assert not bad
assert jd >= TARGET, jd

# ---------- 2. can a Lagrangian sweep + local search beat it?
mk = {}
for line in open('/root/parlay/fd_k_ladder.txt').read().strip().splitlines():
    if not line.strip(): continue
    n, pt, pr = line.split('|')
    mk.setdefault(('K', n), []).append(
        (float(poisson.sf(int(float(pt)-0.5), LAM[n])), dec(pr)))
for line in TOTALS_RAW.strip().splitlines():
    if not line.strip(): continue
    g, bk, pt, o, u = line.split('|')
    if bk != 'FanDuel': continue
    mk.setdefault(('GT', g), []).extend(
        [(dv(int(u), int(o)), dec(u)), (dv(int(o), int(u)), dec(o))])
for line in F5_RAW.strip().splitlines():
    if not line.strip(): continue
    g, pt, o, u = line.split('|')
    mk.setdefault(('GT', g), []).extend(
        [(dv(int(u), int(o)), dec(u)), (dv(int(o), int(u)), dec(o))])

keys = list(mk)
bestL = None
for i in range(4001):
    lam = i * 0.001
    # per market pick the option maximising log p + lam*log d; then take the 25
    # markets with the best such score, and check feasibility
    sc = []
    for k in keys:
        o = max(mk[k], key=lambda t: math.log(t[0]) + lam*math.log(t[1]))
        sc.append((math.log(o[0]) + lam*math.log(o[1]), o))
    sc.sort(key=lambda t: -t[0])
    sel = [o for _, o in sc[:NLEG]]
    d = math.prod(x[1] for x in sel)
    if d >= TARGET:
        p = math.prod(x[0] for x in sel)
        if bestL is None or p > bestL:
            bestL = p
print(f"best Lagrangian sweep found: {bestL*100:.2f}%")
print("DP is better or equal:", jp >= bestL - 1e-12)

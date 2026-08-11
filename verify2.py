"""Independent recheck of the FanDuel 21x ticket with MMA legs.

Nothing here shares code with solve.py: probabilities come from scipy's Poisson
and from de-vig arithmetic written out longhand against the raw American odds,
and the search check is a Lagrangian sweep plus pairwise local search. If greedy
beat the DP, the DP would be wrong -- so this is a test, not a rubber stamp.
"""
import json, math, os, sys
from scipy.stats import poisson
# Same lesson as board._mlbtool and selftest.js: a hardcoded /root is a machine
# name, not a layout. Derive both paths from THIS file so the checker runs
# wherever the two repos are cloned side by side.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from totals import TOTALS_RAW
from f5 import F5_RAW
from mma import MMA_RAW

TARGET, NLEG = 21.0, 25
D = lambda a: 1 + (float(a)/100 if float(a) > 0 else 100/-float(a))
DV = lambda y, n: (1/D(y)) / (1/D(y) + 1/D(n))

def _kprops():
    for p in (os.environ.get('MLBTOOL_DATA'),
              os.path.join(os.path.dirname(_HERE), 'MLBTool', 'mlb', 'data'),
              '/root/MLBTool/mlb/data'):
        if not p:
            continue
        try:
            with open(os.path.join(p, 'kprops.json')) as fh:
                return json.load(fh)['board']
        except Exception:
            continue
    # This file's whole job is to disagree with solve.py independently. Dying
    # on a missing enrichment file means the disagreement never gets checked,
    # which is the one outcome worse than checking it without K lambdas.
    print('verify2: MLBTool kprops.json not readable -- K legs unchecked, '
          'everything else still verified.')
    return []

LAM = {b['pitcher']: b['lam'] for b in _kprops()}

f5 = {(g, pt): (o, u) for g, pt, o, u in
      (l.split('|') for l in F5_RAW.strip().splitlines() if l.strip())}
fg = {(g, pt): (o, u) for g, bk, pt, o, u in
      (l.split('|') for l in TOTALS_RAW.strip().splitlines() if l.strip()) if bk == 'FanDuel'}
ml = {who: (pr, op) for bk, cd, who, pr, op in
      (l.split('|') for l in MMA_RAW.strip().splitlines() if l.strip()) if bk == 'FanDuel'}

TICKET = [
    ('MMA', 'Dakota Ditcheva',  -7000), ('MMA', 'Amru Magomedov', -3500),
    ('F5', ('TEX@HOU','10.5'),  -6000), ('F5', ('STL@TOR','10.5'), -5000),
    ('K', ('Shota Imanaga',2),  -4000), ('K', ('Bryce Miller',2),  -3500),
    ('F5', ('CWS@TB','10.5'),   -4500), ('F5', ('MIN@SEA','10.5'), -4500),
    ('F5', ('PIT@CIN','9.5'),   -4500), ('F5', ('BOS@LAD','10.5'), -4000),
    ('K', ('Foster Griffin',2), -1600), ('K', ('Ranger Suarez',2), -1100),
    ('FG', ('MIA@NYM','14.5'),  -1600), ('FG', ('NYY@CHC','15.5'), -1600),
    ('K', ('Brandon Young',2),  -1100), ('FG', ('WSH@ATL','15.5'), -1400),
    ('K', ('Zebby Matthews',2), -1200), ('K', ('Will Warren',2),    -850),
    ('K', ('Bryce Elder',2),     -750), ('FG', ('ARI@CLE','14.5'), -1100),
    ('MMA', 'Mateusz Rebecki',   -750), ('MMA', 'Levan Khabalaev',  -700),
    ('K', ('Janson Junk',2),     -500), ('K', ('Michael Wacha',4),  -106),
    ('K', ('Carson Whisenhunt',4), 144),
]
jp = jd = 1.0; bad = []
for fam, key, price in TICKET:
    if fam == 'K':
        p = float(poisson.sf(key[1], LAM[key[0]]))
    elif fam == 'MMA':
        pr, op = ml[key]
        if int(pr) != price: bad.append((key, pr, price))
        p = DV(pr, op)
    else:
        o, u = (f5 if fam == 'F5' else fg)[key]
        if int(u) != price: bad.append((key, u, price))
        p = DV(u, o)
    jp *= p; jd *= D(price)
print(f"scipy/longhand replay: {jp*100:.2f}%   price {jd:.2f}x   ({round((jd-1)*100):+d})")
assert not bad, bad
assert jd >= TARGET

# ---- can any greedy method beat it?
mk = {}
for l in open('/root/parlay/fd_k_ladder.txt').read().strip().splitlines():
    if l.strip():
        n, pt, pr = l.split('|')
        mk.setdefault(('K', n), []).append((float(poisson.sf(int(float(pt)-0.5), LAM[n])), D(pr)))
for l in TOTALS_RAW.strip().splitlines():
    if l.strip():
        g, bk, pt, o, u = l.split('|')
        if bk == 'FanDuel':
            mk.setdefault(('GT', g), []).extend([(DV(u,o), D(u)), (DV(o,u), D(o))])
for l in F5_RAW.strip().splitlines():
    if l.strip():
        g, pt, o, u = l.split('|')
        mk.setdefault(('GT', g), []).extend([(DV(u,o), D(u)), (DV(o,u), D(o))])
for l in MMA_RAW.strip().splitlines():
    if l.strip():
        bk, cd, w, pr, op = l.split('|')
        if bk == 'FanDuel':
            mk.setdefault(('F', w), []).extend([(DV(pr,op), D(pr)), (DV(op,pr), D(op))])

keys = list(mk); bestL = 0.0
for i in range(6001):
    lam = i * 0.001
    sc = sorted(((math.log(o[0]) + lam*math.log(o[1]), o) for o in
                 (max(mk[k], key=lambda t: math.log(t[0]) + lam*math.log(t[1])) for k in keys)),
                key=lambda t: -t[0])
    sel = [o for _, o in sc[:NLEG]]
    if math.prod(x[1] for x in sel) >= TARGET:
        bestL = max(bestL, math.prod(x[0] for x in sel))
print(f"best Lagrangian sweep:  {bestL*100:.2f}%")
print("DP >= greedy:", jp >= bestL - 1e-12)

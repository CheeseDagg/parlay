"""Build the max-hit-probability 25-leg ticket for FD and DK from real posted
alternate strikeout lines + the kprops Poisson model."""
import json, math, itertools

# (book, pitcher, point, american price) -- verbatim from the-odds-api,
# markets=pitcher_strikeouts_alternate, bookmakers=draftkings,fanduel, 2026-07-31
RAW = """
FanDuel|Kyle Leahy|2.5|-440
FanDuel|Kyle Leahy|3.5|-148
FanDuel|Dylan Cease|4.5|-2500
FanDuel|Shota Imanaga|2.5|-4000
FanDuel|Shota Imanaga|3.5|-900
FanDuel|Will Warren|2.5|-850
FanDuel|Hunter Greene|3.5|-4000
FanDuel|Paul Skenes|4.5|-2500
FanDuel|Brandon Young|2.5|-1100
FanDuel|Tanner Bibee|2.5|-770
FanDuel|Mitch Bratt|2.5|-440
FanDuel|Erick Fedde|2.5|-225
FanDuel|Nick Martinez|2.5|-700
FanDuel|Freddy Peralta|2.5|-3000
FanDuel|Janson Junk|2.5|-500
FanDuel|Bryce Elder|2.5|-750
FanDuel|Foster Griffin|2.5|-1600
FanDuel|Hunter Brown|3.5|-1100
FanDuel|Nathan Eovaldi|3.5|-1400
FanDuel|Michael Wacha|2.5|-950
FanDuel|Tomoyuki Sugano|2.5|-310
FanDuel|Shane Drohan|2.5|-4000
FanDuel|Ryan Johnson|2.5|-620
FanDuel|Jeffrey Springs|2.5|-530
FanDuel|Carson Whisenhunt|2.5|-460
FanDuel|Ranger Suarez|2.5|-1100
FanDuel|Zebby Matthews|2.5|-1200
FanDuel|Bryce Miller|2.5|-3500
DraftKings|Dylan Cease|3.5|-3000
DraftKings|Kyle Leahy|1.5|-1820
DraftKings|Shota Imanaga|2.5|-3000
DraftKings|Will Warren|1.5|-3500
DraftKings|Paul Skenes|4.5|-1820
DraftKings|Hunter Greene|3.5|-3600
DraftKings|Brandon Young|2.5|-1060
DraftKings|Tanner Bibee|1.5|-2900
DraftKings|Mitch Bratt|1.5|-1340
DraftKings|Nick Martinez|1.5|-3000
DraftKings|Erick Fedde|1.5|-690
DraftKings|Freddy Peralta|2.5|-1540
DraftKings|Janson Junk|1.5|-1620
DraftKings|Foster Griffin|2.5|-940
DraftKings|Bryce Elder|1.5|-2200
DraftKings|Hunter Brown|2.5|-3800
DraftKings|Nathan Eovaldi|3.5|-1020
DraftKings|Michael Wacha|1.5|-2100
DraftKings|Tomoyuki Sugano|1.5|-950
DraftKings|Shane Drohan|2.5|-2900
DraftKings|Ryan Johnson|1.5|-1680
DraftKings|Jeffrey Springs|1.5|-2000
DraftKings|Carson Whisenhunt|1.5|-1580
DraftKings|Ranger Suarez|2.5|-860
DraftKings|Bryce Miller|2.5|-1860
DraftKings|Zebby Matthews|2.5|-930
"""

def dec(am):
    am = float(am)
    return 1 + (am/100 if am > 0 else 100/-am)

def pois_sf(k, lam):
    """P(X > k) for integer k, Poisson(lam) -- i.e. P(over k+0.5)."""
    t = math.exp(-lam); c = t
    for i in range(1, int(k)+1):
        t *= lam/i; c += t
    return 1 - c

board = json.load(open('/root/MLBTool/mlb/data/kprops.json'))['board']
LAM = {b['pitcher']: b['lam'] for b in board}
OPP = {b['pitcher']: b['opp'] for b in board}

legs = {'FanDuel': {}, 'DraftKings': {}}
for line in RAW.strip().splitlines():
    bk, p, pt, price = line.split('|')
    if p not in LAM:
        print('!! no model for', p); continue
    pt = float(pt)
    prob = pois_sf(int(pt - 0.5), LAM[p])
    cur = legs[bk].get(p)
    # lowest line = highest hit probability
    if cur is None or pt < cur['pt']:
        legs[bk][p] = {'pt': pt, 'price': int(price), 'p': prob,
                       'dec': dec(price), 'opp': OPP[p], 'lam': LAM[p]}

for bk in ('FanDuel', 'DraftKings'):
    cand = sorted(legs[bk].items(), key=lambda kv: -kv[1]['p'])
    print(f"\n{'='*86}\n{bk}: {len(cand)} pitchers with a posted alternate line\n{'='*86}")
    print(f"{'#':>2} {'pitcher':20s} {'vs':22s} {'bet':>10s} {'price':>7s} {'model p':>8s} {'mkt imp':>8s}")
    tot_p = 1.0; tot_d = 1.0
    for i, (p, v) in enumerate(cand[:25], 1):
        tot_p *= v['p']; tot_d *= v['dec']
        imp = 1/v['dec']
        print(f"{i:2d} {p:20s} {v['opp']:22s} {int(v['pt']+0.5)}+ Ks{'':>2s} "
              f"{v['price']:>7d} {v['p']:8.4f} {imp:8.4f}")
    print(f"\n  25-leg joint (model, independent): {tot_p:.4f}  ({tot_p*100:.1f}%)")
    print(f"  parlay decimal odds: {tot_d:.3f}x   -> $100 returns ${tot_d*100:.2f} "
          f"(profit ${tot_d*100-100:.2f})")
    print(f"  fair decimal at model p: {1/tot_p:.3f}x   -> ticket EV per $100: "
          f"${tot_p*tot_d*100-100:+.2f}")
    if len(cand) > 25:
        drop = cand[25:]
        print("  left out: " + ", ".join(f"{p} ({v['p']:.3f})" for p, v in drop))

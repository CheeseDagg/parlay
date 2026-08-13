#!/usr/bin/env python3
"""nflhist.py — NFL ground truth: results, spreads, totals, moneylines to 1999.

    python3 nflhist.py
    python3 nflhist.py --selftest

Built in AUGUST, on purpose. Every other sport got its empirical grounding
only after a losing night proved the de-vig had never been checked; the NFL
file (habitatring.com/games.csv, the nflverse mirror) was secured while it is
still preseason, so week 1 is priced against measurement from the first slip.

One file carries every game since 1999 WITH the market attached -- spread,
total line, both moneylines, both totals prices. That answers, before the
season starts:

  * moneyline de-vig calibration, mult vs power, on a 2-way market -- the
    third independent test of the question MLB and soccer answered opposite
    ways (MLB 2-way: mult; soccer 3-way: power). NFL is a 2-way with thin
    overround: which way does it fall?
  * totals calibration: when the under price implies 52%, how often under?
  * P(favourite wins) by spread bucket -- the almanac's translation table
    between "laying 7" and a probability
  * home edge and scoring era, modern window separated

Rows without a played result are skipped, never zeroed; rows without a price
are skipped for calibration but still count toward base rates.
"""
import csv, io, json, math, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'nflhist.json')
URL = "http://www.habitatring.com/games.csv"
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"
MODERN = 2015


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def _f(row, name):
    v = (row.get(name) or '').strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse(text):
    """[{season, type, home_score, away_score, spread, total_line, mlh, mla,
        under_odds, over_odds}] for PLAYED games only."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        hs, as_ = _f(row, 'home_score'), _f(row, 'away_score')
        season = _f(row, 'season')
        if hs is None or as_ is None or season is None:
            continue
        out.append({
            'season': int(season), 'type': (row.get('game_type') or '').strip(),
            'hs': int(hs), 'as': int(as_),
            'spread': _f(row, 'spread_line'),      # positive = home favoured
            'tl': _f(row, 'total_line'),
            'mlh': _f(row, 'home_moneyline'), 'mla': _f(row, 'away_moneyline'),
            'uo': _f(row, 'under_odds'), 'oo': _f(row, 'over_odds')})
    return out


def dec(am):
    return 1 + (am / 100 if am > 0 else 100 / -am)


def mult2(a, b):
    qa, qb = 1 / dec(a), 1 / dec(b)
    return qa / (qa + qb)


def power2(a, b):
    qa, qb = 1 / dec(a), 1 / dec(b)
    f = lambda k: qa ** k + qb ** k - 1
    lo, hi = 0.5, 3.0
    while f(hi) > 0:
        hi *= 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return qa ** ((lo + hi) / 2)


class Bins:
    def __init__(self):
        self.b = {}

    def add(self, p, hit):
        i = min(int(p * 20), 19)
        sp, sa, n = self.b.get(i, (0.0, 0.0, 0))
        self.b[i] = (sp + p, sa + (1 if hit else 0), n + 1)

    def error(self):
        N = sum(n for _, _, n in self.b.values())
        if not N:
            return None
        return sum(abs(sp / n - sa / n) * n for sp, sa, n in self.b.values()) / N

    def table(self, floor=150):
        return [{'bin': round(i * 0.05, 2), 'pred': round(sp / n, 4),
                 'act': round(sa / n, 4), 'n': n}
                for i, (sp, sa, n) in sorted(self.b.items()) if n >= floor]


def spread_table(games):
    """P(favourite wins outright) by closing-spread bucket. Pushes on the
    moneyline question are ties, counted as half -- an NFL tie is a real
    outcome and dropping it flatters the favourite."""
    buckets = {}
    for g in games:
        s = g['spread']
        if s is None or s == 0:
            continue
        fav_home = s > 0
        mag = abs(s)
        key = min(int(mag // 3) * 3, 15)          # 0-3, 3-6, ..., 15+
        fav_pts = g['hs'] if fav_home else g['as']
        dog_pts = g['as'] if fav_home else g['hs']
        w = 1.0 if fav_pts > dog_pts else (0.5 if fav_pts == dog_pts else 0.0)
        a, n = buckets.get(key, (0.0, 0))
        buckets[key] = (a + w, n + 1)
    return {f"{k}-{k+3 if k < 15 else ''}": {'p': round(a / n, 4), 'n': n}
            for k, (a, n) in sorted(buckets.items())}


def main():
    games = parse(get(URL))
    modern = [g for g in games if g['season'] >= MODERN]
    print(f"{len(games)} played games since 1999, {len(modern)} since {MODERN}\n")

    ml = [g for g in modern if g['mlh'] and g['mla']]
    r = {'mult': Bins(), 'power': Bins()}
    for g in ml:
        hit = g['hs'] > g['as']
        for meth, fn in (('mult', mult2), ('power', power2)):
            r[meth].add(fn(g['mlh'], g['mla']), hit)
            r[meth].add(fn(g['mla'], g['mlh']), not hit)
    print(f"  MONEYLINE reliability over {len(ml)} games (said vs happened):")
    for meth in ('mult', 'power'):
        print(f"    {meth:<6} {r[meth].error()*100:.2f} points")

    tot = [g for g in modern if g['uo'] and g['oo'] and g['tl']]
    ub = Bins()
    for g in tot:
        pu = mult2(g['uo'], g['oo'])
        ub.add(pu, (g['hs'] + g['as']) < g['tl'])
    pushes = sum(1 for g in tot if g['hs'] + g['as'] == g['tl'])
    print(f"  TOTALS (mult) over {len(tot)} games: {ub.error()*100:.2f} points"
          f"  ({pushes} pushes counted as under-losses; they void in practice)")

    st = spread_table(modern)
    print("\n  P(favourite wins outright) by closing spread:")
    for k, v in st.items():
        print(f"    {k:<7} {v['p']*100:5.1f}%  n={v['n']}")

    base = {'home_win': round(sum(1 for g in modern if g['hs'] > g['as']) / len(modern), 4),
            'mean_total': round(sum(g['hs'] + g['as'] for g in modern) / len(modern), 2)}
    print(f"\n  modern era: home wins {base['home_win']*100:.1f}%, "
          f"mean total {base['mean_total']}")
    with open(OUT, 'w') as fh:
        json.dump({'modern_since': MODERN, 'games': len(modern),
                   'ml_reliability': {m: r[m].error() for m in r},
                   'ml_bins_mult': r['mult'].table(),
                   'totals_reliability': ub.error(),
                   'spread_to_winprob': st, 'base': base}, fh, indent=1)
    print(f"wrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    csvt = ("game_id,season,game_type,away_team,away_score,home_team,home_score,"
            "spread_line,total_line,away_moneyline,home_moneyline,under_odds,over_odds\n"
            "a,2025,REG,KC,20,BUF,24,2.5,46.5,120,-140,-110,-110\n"
            "b,2026,REG,DAL,,PHI,,7,48.5,240,-290,-105,-115\n"
            "c,2025,POST,SF,17,SEA,17,-3,44,130,-150,-110,-110\n")
    g = parse(csvt)
    chk(len(g) == 2, "an unplayed game (blank scores) is skipped, never zeroed")
    chk(g[0]['spread'] == 2.5 and g[0]['tl'] == 46.5,
        "spread and total ride along with the result")

    p = mult2(-140, 120)
    chk(0.55 < p < 0.60, "mult on -140/+120 lands mid-50s")
    chk(abs(mult2(-140, 120) + mult2(120, -140) - 1) < 1e-12,
        "the two sides of a 2-way sum to one after de-vig")
    chk(power2(-140, 120) > mult2(-140, 120),
        "power hands the favourite more, same direction as every other market")

    st = spread_table([
        {'hs': 24, 'as': 20, 'spread': 2.5},
        {'hs': 20, 'as': 24, 'spread': 2.5},
        {'hs': 17, 'as': 17, 'spread': 2.5},
        {'hs': 10, 'as': 30, 'spread': -7.0}])
    b03 = st['0-3']
    chk(b03['n'] == 3 and abs(b03['p'] - 0.5) < 1e-9,
        "a tie counts the favourite half a win -- dropping ties flatters them")
    chk(st['6-9']['p'] == 1.0,
        "a negative spread means the AWAY side is favoured, and its win counts")

    b = Bins()
    b.add(0.6, True); b.add(0.6, False)
    chk(abs(b.error() - 0.1) < 1e-9, "reliability error is |said - happened|")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

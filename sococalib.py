#!/usr/bin/env python3
"""sococalib.py — calibrate the soccer de-vig against real closing odds.

    python3 sococalib.py
    python3 sococalib.py --selftest

MLB's de-vig turned out to be miscalibrated by 4+ points per leg, found only
because 6681 games of ground truth existed to check against. Soccer legs are
HALF of every ticket and their de-vig had no ground truth at all: openfootball
has scores but no odds, so the one test that caught the MLB error could not be
run on the sport where the money went.

football-data.co.uk has both: every match with the market's CLOSING odds
(average across books, else Pinnacle, else Bet365). With odds AND outcomes the
question stops being "what is the base rate" and becomes the sharper one:
WHEN THE DE-VIG SAYS 78%, HOW OFTEN DOES IT HAPPEN? That is calibration, and
it is answered here for:

  * the 3-way itself, mult vs power, binned by predicted probability
  * the favourite's DOUBLE CHANCE -- p(fav) + p(draw) -- the leg we actually bet
  * the under 2.5, where the file carries totals odds -- the other leg we bet

Plus league base rates for USA (MLS), MEX, ARG, BRA -- the competitions
openfootball lacks, which tonight's Leagues Cup legs were proxied against.

The closing line is used, not the opening: closing is the market's final
opinion and the standard benchmark. Anything this file says about calibration
is about FAIR PROBABILITY, not about beating the close -- nothing here claims
edge, it claims honest pricing of legs already chosen.
"""
import csv, io, json, math, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'sococalib.json')
BASE = "https://www.football-data.co.uk"
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"

# mmz4281 = Europe, one file per league-season. Seasons chosen for closing-odds
# columns (present from ~2019-20 on) and sample size.
SEASONS = ['1920', '2021', '2122', '2223', '2324', '2425', '2526']
DIVS = {'E0': 'England Premier League', 'E1': 'England Championship',
        'SP1': 'Spain La Liga', 'I1': 'Italy Serie A',
        'D1': 'Germany Bundesliga', 'F1': 'France Ligue 1',
        'N1': 'Netherlands Eredivisie', 'P1': 'Portugal Primeira Liga',
        'B1': 'Belgium Pro League'}
# new/ = one file per country, full history, different column names.
EXTRA = {'USA': 'USA MLS', 'MEX': 'Mexico Liga MX',
         'ARG': 'Argentina Primera', 'BRA': 'Brazil Serie A',
         'JPN': 'Japan J-League', 'CHN': 'China Super League',
         # added 8/13: all on the board, all previously 'measured absent'
         'DNK': 'Denmark Superliga', 'FIN': 'Finland Veikkausliiga',
         'NOR': 'Norway Eliteserien', 'POL': 'Poland Ekstraklasa',
         'RUS': 'Russia Premier League', 'SWE': 'Sweden Allsvenskan',
         'AUT': 'Austria Bundesliga (odds)', 'ROU': 'Romania Liga 1',
         'SWZ': 'Switzerland Super League', 'IRL': 'Ireland Premier'}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', 'replace')


def _f(row, *names):
    """First parseable float among the named columns, else None."""
    for n in names:
        v = (row.get(n) or '').strip()
        if v:
            try:
                return float(v)
            except ValueError:
                continue
    return None


def parse_rows(text, kind):
    """[{hg, ag, res, oh, od, oa, ou_u, ou_o, season}] from one CSV.

    kind='mmz'  FTHG/FTAG/FTR, closing avg first (AvgCH...), then pre-close
                avg, then Pinnacle, then B365. Totals odds when present.
    kind='new'  HG/AG/Res, AvgCH... else PSCH... else AvgH/PH. No totals.

    A row missing any of the three 1X2 odds is DROPPED, not patched: a match
    priced from two outcomes is exactly the de-vig error this file audits.
    """
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if kind == 'mmz':
            hg, ag, res = _f(row, 'FTHG'), _f(row, 'FTAG'), (row.get('FTR') or '').strip()
            oh = _f(row, 'AvgCH', 'AvgH', 'PSCH', 'PSH', 'B365CH', 'B365H')
            od = _f(row, 'AvgCD', 'AvgD', 'PSCD', 'PSD', 'B365CD', 'B365D')
            oa = _f(row, 'AvgCA', 'AvgA', 'PSCA', 'PSA', 'B365CA', 'B365A')
            uu = _f(row, 'AvgC<2.5', 'Avg<2.5', 'P<2.5', 'B365C<2.5', 'B365<2.5')
            uo = _f(row, 'AvgC>2.5', 'Avg>2.5', 'P>2.5', 'B365C>2.5', 'B365>2.5')
            season = (row.get('Date') or '')[-4:]
        else:
            hg, ag, res = _f(row, 'HG'), _f(row, 'AG'), (row.get('Res') or '').strip()
            oh = _f(row, 'AvgCH', 'AvgH', 'PSCH', 'PSH', 'PH')
            od = _f(row, 'AvgCD', 'AvgD', 'PSCD', 'PSD', 'PD')
            oa = _f(row, 'AvgCA', 'AvgA', 'PSCA', 'PSA', 'PA')
            uu = uo = None
            season = (row.get('Season') or '').strip()
        if hg is None or ag is None or res not in ('H', 'D', 'A'):
            continue
        if not (oh and od and oa and oh > 1 and od > 1 and oa > 1):
            continue
        out.append({'hg': int(hg), 'ag': int(ag), 'res': res,
                    'oh': oh, 'od': od, 'oa': oa,
                    'uu': uu, 'uo': uo, 'season': season})
    return out


def mult_split(qs):
    s = sum(qs)
    return [q / s for q in qs]


def power_split(qs):
    """sum(q^k)=1 by bisection -- no scipy on the runner, none needed."""
    f = lambda k: sum(q ** k for q in qs) - 1
    lo, hi = 0.5, 3.0
    while f(hi) > 0:
        hi *= 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    return [q ** k for q in qs]


class Bins:
    """Reliability bins: does 'the de-vig said p' match 'it happened p of the
    time'? Width 0.05; the summary number is the n-weighted mean |pred-actual|."""
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

    def table(self):
        return [{'bin': round(i * 0.05, 2), 'pred': round(sp / n, 4),
                 'act': round(sa / n, 4), 'n': n}
                for i, (sp, sa, n) in sorted(self.b.items())]


def audit(rows):
    """Per-method reliability for the 3-way, the favourite DC, and U2.5."""
    r3 = {'mult': Bins(), 'power': Bins()}
    rdc = {'mult': Bins(), 'power': Bins()}
    ru = Bins()
    for m in rows:
        qs = [1 / m['oh'], 1 / m['od'], 1 / m['oa']]
        for meth, split in (('mult', mult_split), ('power', power_split)):
            ph, pd_, pa = split(qs)
            for p, hit in ((ph, m['res'] == 'H'), (pd_, m['res'] == 'D'),
                           (pa, m['res'] == 'A')):
                r3[meth].add(p, hit)
            fav_home = m['oh'] <= m['oa']
            pdc = (ph if fav_home else pa) + pd_
            hit = m['res'] == ('H' if fav_home else 'A') or m['res'] == 'D'
            rdc[meth].add(pdc, hit)
        if m['uu'] and m['uo'] and m['uu'] > 1 and m['uo'] > 1:
            qu, qo = 1 / m['uu'], 1 / m['uo']
            ru.add(qu / (qu + qo), (m['hg'] + m['ag']) < 2.5)
    return r3, rdc, ru


def base_rates(rows):
    n = len(rows)
    d = sum(1 for m in rows if m['res'] == 'D')
    goals = [m['hg'] + m['ag'] for m in rows]
    return {'n': n, 'draw': round(d / n, 5),
            'home': round(sum(1 for m in rows if m['res'] == 'H') / n, 5),
            'away': round(sum(1 for m in rows if m['res'] == 'A') / n, 5),
            'mean_goals': round(sum(goals) / n, 3),
            'under': {str(r): round(sum(1 for g in goals if g < r) / n, 5)
                      for r in (1.5, 2.5, 3.5, 4.5, 5.5)}}


def main():
    allrows, per = [], {}
    for div, name in DIVS.items():
        rows = []
        for ssn in SEASONS:
            try:
                rows += parse_rows(get(f"{BASE}/mmz4281/{ssn}/{div}.csv"), 'mmz')
            except Exception:
                continue
        if rows:
            per[name] = rows
            allrows += rows
            print(f"  {name}: {len(rows)} matches with closing odds")
    for code, name in EXTRA.items():
        try:
            rows = parse_rows(get(f"{BASE}/new/{code}.csv"), 'new')
        except Exception as e:
            print(f"  {name}: {type(e).__name__}")
            continue
        if rows:
            per[name] = rows
            allrows += rows
            print(f"  {name}: {len(rows)} matches with closing odds")
    if not allrows:
        print("nothing parsed")
        return 1

    print(f"\n  {len(allrows)} matches with closing odds and results\n")
    r3, rdc, ru = audit(allrows)
    print("  DE-VIG RELIABILITY -- n-weighted mean |predicted - actual|")
    for meth in ('mult', 'power'):
        print(f"    3-way {meth:<6} {r3[meth].error()*100:5.2f} points"
              f"   |  favourite DC {meth:<6} {rdc[meth].error()*100:5.2f} points")
    if ru.error() is not None:
        print(f"    under 2.5 (2-way mult)  {ru.error()*100:5.2f} points over "
              f"{sum(n for _, _, n in ru.b.values())} matches")
    print("\n  favourite-DC reliability by bin (mult):")
    for row in rdc['mult'].table():
        if row['n'] >= 200:
            print(f"    said {row['pred']*100:5.1f}%  happened {row['act']*100:5.1f}%"
                  f"   n={row['n']}")
    print("\n  BASE RATES for the leagues openfootball lacks:")
    extras = {}
    for code, name in EXTRA.items():
        if name in per:
            b = base_rates(per[name])
            extras[name] = b
            print(f"    {name:<22} n={b['n']:<6} draw {b['draw']*100:.1f}%  "
                  f"goals {b['mean_goals']:.2f}  U2.5 {b['under']['2.5']*100:.1f}%")
    cur = sum(1 for m in allrows if m['season'] in ('2026', '2027', '2026/2027'))
    print(f"\n  rows from the CURRENT (2026-27 / 2026) season: {cur} -- form exists here")
    with open(OUT, 'w') as fh:
        json.dump({'matches': len(allrows),
                   'reliability': {
                       'three_way': {m: r3[m].error() for m in r3},
                       'fav_dc': {m: rdc[m].error() for m in rdc},
                       'fav_dc_bins_mult': rdc['mult'].table(),
                       'under25': ru.error()},
                   'leagues': {k: base_rates(v) for k, v in per.items()},
                   }, fh, indent=1)
    print(f"wrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    mmz = ("Div,Date,FTHG,FTAG,FTR,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5\n"
           "E0,13/08/2026,2,1,H,1.50,4.40,6.00,1.90,1.95\n"
           "E0,13/08/2026,0,0,D,2.10,3.30,3.60,,\n"
           "E0,13/08/2026,1,1,D,,3.30,3.60,1.9,1.9\n")
    rows = parse_rows(mmz, 'mmz')
    chk(len(rows) == 2 and rows[0]['oh'] == 1.5 and rows[1]['uu'] is None,
        "a row missing any 1X2 price is dropped -- a market de-vigged from two "
        "of three outcomes is the exact error this file audits")
    new = ("Country,League,Season,Date,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA\n"
           "USA,MLS,2026,12/08/2026,A,B,3,1,H,1.80,3.90,4.20\n")
    r2 = parse_rows(new, 'new')
    chk(len(r2) == 1 and r2[0]['season'] == '2026',
        "the new/ format parses on its own column names, season kept for form")

    qs = [1 / 1.37, 1 / 4.80, 1 / 6.50]
    pm, pp = mult_split(qs), power_split(qs)
    chk(abs(sum(pm) - 1) < 1e-9 and abs(sum(pp) - 1) < 1e-6,
        "both de-vigs renormalise to exactly one")
    chk(pp[0] > pm[0],
        "power hands the favourite MORE than mult does -- the direction that "
        "overstated every MLB ticket, now checkable on soccer")

    b = Bins()
    for _ in range(70):
        b.add(0.70, True)
    for _ in range(30):
        b.add(0.70, False)
    chk(abs(b.error()) < 1e-9,
        "a de-vig that says 70% for things happening 70% of the time scores a "
        "perfect zero -- the metric rewards honesty, not boldness")
    b2 = Bins()
    b2.add(0.999, True)
    chk(0.95 in [r['bin'] for r in b2.table()],
        "p=1 lands in the top bin instead of overflowing")

    r3, rdc, ru = audit([
        {'hg': 1, 'ag': 0, 'res': 'H', 'oh': 1.5, 'od': 4.4, 'oa': 6.0,
         'uu': 1.95, 'uo': 1.90, 'season': '2026'},
        {'hg': 0, 'ag': 2, 'res': 'A', 'oh': 6.0, 'od': 4.4, 'oa': 1.5,
         'uu': None, 'uo': None, 'season': '2026'}])
    chk(sum(n for _, _, n in rdc['mult'].b.values()) == 2,
        "the favourite DC is scored once per match, favourite by shorter price "
        "-- including when the favourite is the AWAY side")
    (sp, sa, n) = list(ru.b.values())[0]
    chk(n == 1 and sa == 1.0,
        "under 2.5 with one goal scored settles as a hit")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

#!/usr/bin/env python3
"""sochist.py — empirical goal totals and result rates for soccer.

    python3 sochist.py
    python3 sochist.py --selftest

Soccer is half of every ticket and had NO empirical grounding at all. Both
leg types we actually bet were priced from the market's de-vig alone:

  Under X.5 goals   -- a total, exactly like an MLB F5 under
  Double Chance     -- derived as 1 - p(underdog) off the 3-way

On 2026-08-13 that cost real money, and the de-vig itself turned out to be
miscalibrated in MLB (board.METHOD went power -> mult on 6681 games). There
was no way to run the same check on soccer because no soccer history was
readable from anywhere in the toolchain.

openfootball/football.json is plain JSON on GitHub raw, reachable from the
Actions runner, and carries full-time scores for the major leagues going back
seasons. That is enough to answer the two questions that matter:

  P(total goals <= X)  per league, which is what an alt-goal-under settles on
  P(home / draw / away) per league, which is what a Double Chance is built from

LEAGUE MATTERS AND POOLING HIDES IT. A 2.5-goal under is a different bet in
Serie A than in the Eredivisie, and the draw rate -- the entire reason a DC
exists -- swings by several points between competitions. So nothing here is
reported pooled without also being reported per league.

WHAT THIS IS NOT: it is league-season base rates, not a match model. It says
what a typical fixture in a competition does, which is the right prior for a
board that quotes every league off one de-vig, and the wrong number to bet a
specific match on without the price in front of you.
"""
import json, math, os, sys, urllib.request

RAW = "https://raw.githubusercontent.com/openfootball/football.json/master"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'sochist.json')
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"

# league file -> readable name. openfootball's codes are <country>.<tier>.
LEAGUES = {
    "en.1": "England Premier League", "en.2": "England Championship",
    "es.1": "Spain La Liga", "it.1": "Italy Serie A",
    "de.1": "Germany Bundesliga", "fr.1": "France Ligue 1",
    "nl.1": "Netherlands Eredivisie", "pt.1": "Portugal Primeira Liga",
    "at.1": "Austria Bundesliga", "be.1": "Belgium Pro League",
    "mx.1": "Mexico Liga MX", "br.1": "Brazil Serie A",
}
SEASONS = ["2022-23", "2023-24", "2024-25"]
RUNGS = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]


def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), p, min(1.0, c + h)


def parse(doc):
    """[(home_goals, away_goals)] from one openfootball league-season file.

    Only FULL TIME is used. A fixture with no score has not been played and
    must be skipped rather than read as 0-0 -- the same shape of error as
    counting a rain-shortened game as a low MLB total, and in the same
    direction: it would make every under look safer than it is.
    """
    out = []
    for m in doc.get('matches', []):
        sc = m.get('score') or {}
        ft = sc.get('ft')
        if not ft or len(ft) != 2:
            continue
        try:
            out.append((int(ft[0]), int(ft[1])))
        except (TypeError, ValueError):
            continue
    return out


def totals_table(games):
    n = len(games)
    rows = []
    for r in RUNGS:
        k = sum(1 for h, a in games if h + a < r)
        lo, p, hi = wilson(k, n)
        rows.append({'rung': r, 'n': n, 'p': round(p, 5),
                     'lo': round(lo, 5), 'hi': round(hi, 5)})
    return rows


def result_rates(games):
    n = len(games)
    if not n:
        return {}
    h = sum(1 for a, b in games if a > b)
    d = sum(1 for a, b in games if a == b)
    return {'n': n, 'home': round(h / n, 5), 'draw': round(d / n, 5),
            'away': round((n - h - d) / n, 5),
            'home_dc': round((h + d) / n, 5), 'away_dc': round((n - h) / n, 5),
            'mean_goals': round(sum(a + b for a, b in games) / n, 3)}


def chi_disp(groups, base):
    """Is the spread across leagues bigger than binomial noise? Same test as
    f5hist -- a leaderboard is not a finding until dispersion says so."""
    rows = [(k, v) for k, v in groups.items() if v['n'] >= 100]
    if len(rows) < 3:
        return None, None
    chi = sum((v['draw'] * v['n'] - base * v['n']) ** 2 /
              (base * (1 - base) * v['n']) for _, v in rows)
    df = len(rows) - 1
    z = ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / ((2 / (9 * df)) ** 0.5)
    return chi, 0.5 * math.erfc(z / math.sqrt(2))


def main():
    per, allg = {}, []
    for code, name in LEAGUES.items():
        got = []
        for season in SEASONS:
            try:
                got += parse(get(f"{RAW}/{season}/{code}.json"))
            except Exception:
                continue
        if len(got) < 100:
            print(f"  {name}: only {len(got)} matches, skipped")
            continue
        per[name] = got
        allg += got
        print(f"  {name}: {len(got)} matches")
    if not allg:
        print("no data"); return 1

    print(f"\n  POOLED: {len(allg)} matches, mean {sum(a+b for a,b in allg)/len(allg):.2f} goals\n")
    print(f"  {'':<28}" + ''.join(f"{('U%.1f' % r):>8}" for r in RUNGS))
    pooled = totals_table(allg)
    print(f"  {'POOLED':<28}" + ''.join(f"{r['p']*100:7.1f}%" for r in pooled))
    for name in sorted(per, key=lambda k: -sum(a + b for a, b in per[k]) / len(per[k])):
        t = totals_table(per[name])
        print(f"  {name[:27]:<28}" + ''.join(f"{r['p']*100:7.1f}%" for r in t)
              + f"   n={len(per[name])}")

    print(f"\n  RESULT RATES -- the draw is the whole reason a Double Chance exists")
    print(f"  {'':<28}{'home':>7}{'draw':>7}{'away':>7}{'homeDC':>9}{'awayDC':>9}{'goals':>7}")
    rr = {name: result_rates(g) for name, g in per.items()}
    pr = result_rates(allg)
    print(f"  {'POOLED':<28}{pr['home']*100:6.1f}%{pr['draw']*100:6.1f}%"
          f"{pr['away']*100:6.1f}%{pr['home_dc']*100:8.1f}%{pr['away_dc']*100:8.1f}%"
          f"{pr['mean_goals']:7.2f}")
    for name in sorted(rr, key=lambda k: -rr[k]['draw']):
        v = rr[name]
        print(f"  {name[:27]:<28}{v['home']*100:6.1f}%{v['draw']*100:6.1f}%"
              f"{v['away']*100:6.1f}%{v['home_dc']*100:8.1f}%{v['away_dc']*100:8.1f}%"
              f"{v['mean_goals']:7.2f}")
    chi, pv = chi_disp(rr, pr['draw'])
    if pv is not None:
        print(f"\n  draw-rate dispersion across leagues: chi2={chi:.1f} p={pv:.4f}"
              f"  -> {'REAL spread' if pv < 0.05 else 'CONSISTENT WITH NOISE'}")

    with open(OUT, 'w') as fh:
        json.dump({'seasons': SEASONS, 'matches': len(allg),
                   'pooled_totals': pooled, 'pooled_result': pr,
                   'leagues': {k: {'totals': totals_table(v), 'result': rr[k]}
                               for k, v in per.items()}}, fh, indent=1)
    print(f"\nwrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    doc = {'matches': [
        {'score': {'ft': [2, 1]}}, {'score': {'ft': [0, 0]}},
        {'score': {}},                       # fixture not yet played
        {'team1': 'x', 'team2': 'y'},        # no score block at all
        {'score': {'ft': [1, 3]}}]}
    g = parse(doc)
    chk(g == [(2, 1), (0, 0), (1, 3)],
        "only played fixtures are counted -- an unplayed one read as 0-0 would "
        "make every under look safer, the same error shape as a rain-shortened "
        "MLB game counted as a low total")

    t = totals_table([(0, 0), (1, 0), (1, 1), (2, 1), (3, 2), (4, 3)])
    u25 = next(r for r in t if r['rung'] == 2.5)
    chk(u25['p'] == 0.5, "U2.5 counts totals strictly below 2.5, so 0,1,2 of six")
    u15 = next(r for r in t if r['rung'] == 1.5)
    chk(u15['p'] == round(2 / 6, 5), "and U1.5 is monotonically tighter")

    r = result_rates([(2, 1), (1, 1), (0, 2), (3, 0)])
    chk(r['home'] == 0.5 and r['draw'] == 0.25 and r['away'] == 0.25,
        "home / draw / away partition the outcomes")
    chk(abs(r['home_dc'] - 0.75) < 1e-9 and abs(r['away_dc'] - 0.5) < 1e-9,
        "a Double Chance is the side PLUS the draw, which is what makes it a "
        "different bet from the moneyline the draw can beat")
    chk(abs(r['home_dc'] + r['away_dc'] - 1 - r['draw']) < 1e-9,
        "and the two double chances overlap by exactly the draw rate")
    chk(r['mean_goals'] == 2.5, "mean goals is per match, not per team")

    lo, p, hi = wilson(50, 200)
    chk(lo < p < hi, "Wilson brackets the estimate")
    _, pv = chi_disp({'a': {'n': 300, 'draw': 0.25}, 'b': {'n': 300, 'draw': 0.25},
                      'c': {'n': 300, 'draw': 0.25}, 'd': {'n': 300, 'draw': 0.25}}, 0.25)
    chk(pv is not None and pv > 0.5,
        "four identical leagues read as noise, so the dispersion test is not "
        "manufacturing findings")
    _, pv2 = chi_disp({'a': {'n': 400, 'draw': 0.10}, 'b': {'n': 400, 'draw': 0.35},
                       'c': {'n': 400, 'draw': 0.12}, 'd': {'n': 400, 'draw': 0.33}}, 0.225)
    chk(pv2 is not None and pv2 < 0.01, "and a genuinely split field reads as real")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

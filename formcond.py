#!/usr/bin/env python3
"""formcond.py — does recent TEAM pace condition the league under rate?

    python3 formcond.py             # fetch, derive on train, verify on tail
    python3 formcond.py --selftest  # offline synthetic worlds

WHY. edge.py's first live scan (8/14) put Cincinnati–Orlando U5.5 at the
top of the board (+11.5 on the league base) while both clubs' last five
games ran 6-8 goals, and flagged Alavés–Getafe as a trap while both clubs
sit near the bottom of Spain's scoring. Both calls were adjudicated BY
EYE. This file measures the thing the eye was doing: how far does the
league's under rate move when the two teams' recent match totals say the
fixture is fast or slow?

THE FEATURE. For each match, each side's mean TOTAL goals over its last
five league games (>=3 required, strictly prior); pace = the two means
averaged; x = pace minus the league's TRAIN-era mean total. x rides in
goals, so +1.0 means "these clubs' recent games run a goal above league".

THE MODEL IS A DELTA TABLE, not a refit: per rung, per x-bin, the pooled
mean of (hit_under - league_train_base). Pooling across leagues is safe
exactly because the league base is subtracted first -- a slow league and a
fast league contribute deviations, not levels. Conditioned rate =
league base + delta, clipped away from 0/1.

THE BAR, same as every derivation here: deltas derive on TRAIN (matches
before the split date), the verdict is log loss on the UNTOUCHED tail vs
the league base alone, per rung; and 20 shuffles of the feature must not
reproduce the gain (the chinhist/defhist permutation rule -- the threshold
is arithmetic, not taste). Rungs that fail stay unconditioned in edge.py.

Sources are the same football-data.co.uk routes sococalib audited 8/13
(52,710 matches with closing odds); this file re-reads them for the two
columns sococalib deliberately drops (team names, dates).
"""
import csv, io, json, math, os, sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sococalib import BASE, SEASONS, DIVS, EXTRA, get

OUT = os.path.join(HERE, 'formcond.json')
SPLIT = '2025-07-01'          # tail = the season in progress + last completed
MIN_PRIOR = 3                 # matches per side before pace is quotable
LAST_N = 5
RUNGS = (2.5, 3.5, 4.5, 5.5)
BINS = ((None, -0.75), (-0.75, -0.25), (-0.25, 0.25), (0.25, 0.75), (0.75, None))
PERMS = 20
EPS = 0.02


def _date_iso(d):
    """football-data dates: dd/mm/yy or dd/mm/yyyy -> ISO, or None."""
    p = (d or '').strip().split('/')
    if len(p) != 3:
        return None
    dd, mm, yy = p
    if len(yy) == 2:
        yy = ('20' if int(yy) < 80 else '19') + yy
    try:
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except ValueError:
        return None


def parse_matches(text, kind):
    """[{date, home, away, tot}] -- the two columns sococalib drops, kept."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if kind == 'mmz':
            h, a = row.get('HomeTeam'), row.get('AwayTeam')
            hg, ag = row.get('FTHG'), row.get('FTAG')
        else:
            h, a = row.get('Home'), row.get('Away')
            hg, ag = row.get('HG'), row.get('AG')
        d = _date_iso(row.get('Date'))
        try:
            tot = int(float(hg)) + int(float(ag))
        except (TypeError, ValueError):
            continue
        if not (h and a and d):
            continue
        out.append({'date': d, 'home': h.strip(), 'away': a.strip(), 'tot': tot})
    out.sort(key=lambda r: r['date'])
    return out


def fetch_all(log=print):
    per = {}
    for div, name in DIVS.items():
        rows = []
        for ssn in SEASONS:
            try:
                rows += parse_matches(get(f"{BASE}/mmz4281/{ssn}/{div}.csv"), 'mmz')
            except Exception:
                continue
        if rows:
            rows.sort(key=lambda r: r['date'])
            per[name] = rows
            log(f"  {name}: {len(rows)}")
    for code, name in EXTRA.items():
        try:
            rows = parse_matches(get(f"{BASE}/new/{code}.csv"), 'new')
        except Exception as e:
            log(f"  {name}: {type(e).__name__}")
            continue
        if rows:
            per[name] = rows
            log(f"  {name}: {len(rows)}")
    return per


def walk(per):
    """One row per match with pace built from STRICTLY PRIOR games.

    The deque append happens after the snapshot -- the same leak boundary
    every walk in this repo draws, and the selftest pins it."""
    out = []
    for lg, rows in per.items():
        hist = defaultdict(lambda: deque(maxlen=LAST_N))
        for r in rows:
            h, a = hist[r['home']], hist[r['away']]
            if len(h) >= MIN_PRIOR and len(a) >= MIN_PRIOR:
                pace = (sum(h) / len(h) + sum(a) / len(a)) / 2.0
                out.append({'lg': lg, 'date': r['date'], 'tot': r['tot'],
                            'pace': pace})
            hist[r['home']].append(r['tot'])
            hist[r['away']].append(r['tot'])
    out.sort(key=lambda r: r['date'])
    return out


def _bin_of(x):
    for i, (lo, hi) in enumerate(BINS):
        if (lo is None or x >= lo) and (hi is None or x < hi):
            return i
    return len(BINS) - 1


def derive(rows, split=SPLIT):
    """Train-era league means and per-rung/per-bin deltas."""
    tr = [r for r in rows if r['date'] < split]
    means = {}
    for lg in {r['lg'] for r in tr}:
        sel = [r['tot'] for r in tr if r['lg'] == lg]
        if len(sel) >= 300:
            means[lg] = sum(sel) / float(len(sel))
    base = {}
    for lg in means:
        sel = [r for r in tr if r['lg'] == lg]
        base[lg] = {str(rg): sum(1 for r in sel if r['tot'] < rg) / float(len(sel))
                    for rg in RUNGS}
    deltas = {str(rg): [] for rg in RUNGS}
    counts = {str(rg): [] for rg in RUNGS}
    for rg in RUNGS:
        acc = [[0.0, 0] for _ in BINS]
        for r in tr:
            if r['lg'] not in means:
                continue
            b = _bin_of(r['pace'] - means[r['lg']])
            acc[b][0] += (1.0 if r['tot'] < rg else 0.0) - base[r['lg']][str(rg)]
            acc[b][1] += 1
        deltas[str(rg)] = [(s / n if n >= 200 else 0.0) for s, n in acc]
        counts[str(rg)] = [n for _, n in acc]
    return {'means': means, 'base': base, 'deltas': deltas, 'counts': counts,
            'n_train': len(tr)}


def conditioned(model, lg, rung, pace):
    """League base + the pace bin's measured delta, or None off-model."""
    m = model['means'].get(lg)
    b = model['base'].get(lg, {}).get(str(rung))
    d = model['deltas'].get(str(rung))
    if m is None or b is None or not d:
        return None
    p = b + d[_bin_of(pace - m)]
    return min(max(p, EPS), 1 - EPS)


def score(rows, model, split=SPLIT):
    """Per-rung log loss on the tail: league base alone vs conditioned."""
    te = [r for r in rows if r['date'] >= split and r['lg'] in model['means']]
    out = {}
    for rg in RUNGS:
        lb = lc = n = 0.0
        for r in te:
            y = 1.0 if r['tot'] < rg else 0.0
            pb = min(max(model['base'][r['lg']][str(rg)], EPS), 1 - EPS)
            pc = conditioned(model, r['lg'], rg, r['pace'])
            lb -= y * math.log(pb) + (1 - y) * math.log(1 - pb)
            lc -= y * math.log(pc) + (1 - y) * math.log(1 - pc)
            n += 1
        if n:
            out[str(rg)] = {'base': lb / n, 'cond': lc / n,
                            'gain': (lb - lc) / n, 'n': int(n)}
    return out


def permute(rows, seed):
    st = seed
    idx = list(range(len(rows)))
    for i in range(len(idx) - 1, 0, -1):
        st = (1103515245 * st + 12345) % (1 << 31)
        j = st % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    sh = [dict(r) for r in rows]
    for r, k in zip(sh, idx):
        r['pace'] = rows[k]['pace']
    return sh


def verdicts(rows, split=SPLIT, perms=PERMS, log=print):
    model = derive(rows, split)
    real = score(rows, model, split)
    nulls = {str(rg): [] for rg in RUNGS}
    for s in range(perms):
        sh = permute(rows, 1000 + 7 * s)
        msh = derive(sh, split)
        ssh = score(sh, msh, split)
        for rg in RUNGS:
            if str(rg) in ssh:
                nulls[str(rg)].append(ssh[str(rg)]['gain'])
    ship = {}
    for rg in RUNGS:
        k = str(rg)
        if k not in real:
            continue
        g = real[k]['gain']
        worst = max(nulls[k]) if nulls[k] else 0.0
        beaten = sum(1 for x in nulls[k] if x >= g)
        ok = g > 0 and beaten == 0
        ship[k] = {'gain': g, 'best_null': worst,
                   'p': (beaten + 1) / float(len(nulls[k]) + 1), 'ships': ok,
                   'n_test': real[k]['n']}
        log(f"  U{k}: tail gain {g:+.5f} (n={real[k]['n']}), best of "
            f"{len(nulls[k])} shuffles {worst:+.5f}, p={ship[k]['p']:.3f} "
            f"-> {'SHIPS' if ok else 'refused'}")
    return model, ship


def main():
    print("formcond: fetching per-match rows (same routes sococalib audited)")
    per = fetch_all()
    rows = walk(per)
    n_lg = len({r['lg'] for r in rows})
    print(f"\n  {len(rows)} matches with 3+ prior games both sides, "
          f"{n_lg} leagues\n")
    if len(rows) < 5000:
        # the pull_feeds rule: a dead pull must not dress itself as a result.
        # 8/14: every route URLError'd from the session container (the 8/13
        # sococalib numbers were built on the Actions runner) and the first
        # draft of this file wrote an EMPTY model over formcond.json.
        print("  REFUSING to write: fewer than 5000 rows means the fetch "
              "died, not that soccer got smaller. Run this on the Actions "
              "runner (same as socdiag/sococalib).")
        return 1
    model, ship = verdicts(rows)
    doc = {'split': SPLIT, 'last_n': LAST_N, 'min_prior': MIN_PRIOR,
           'bins': [list(b) for b in BINS], 'rungs': list(RUNGS),
           'model': model, 'ship': ship,
           'n_rows': len(rows), 'n_leagues': n_lg}
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=HERE, suffix='.tmp')
    with os.fdopen(fd, 'w') as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.replace(tmp, OUT)
    shipped = [k for k, v in ship.items() if v['ships']]
    print(f"\n  wrote formcond.json -- shipped rungs: {shipped or 'NONE'}")
    for k in shipped:
        d = model['deltas'][k]
        print(f"  U{k} deltas by pace bin (slow->fast): "
              + '  '.join(f"{x * 100:+.1f}" for x in d))
    return 0


# ---------------------------------------------------------------- synthetic
def _world(seed, cond, n_teams=20, n_seasons=8):
    st = seed
    def rnd():
        nonlocal st
        st = (1103515245 * st + 12345) % (1 << 31)
        return st / float(1 << 31)
    def pois(lam):
        # Knuth, deterministic via rnd()
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= rnd()
            if p <= L:
                return k - 1
    teams = [1.4 + 1.2 * rnd() for _ in range(n_teams)]   # per-team scoring level
    rows = []
    for s in range(n_seasons):
        for rd in range(30):
            date = f"{2018 + s}-{1 + rd // 3:02d}-{1 + rd % 28:02d}"
            order = list(range(n_teams))
            for i in range(len(order) - 1, 0, -1):
                j = int(rnd() * (i + 1))
                order[i], order[j] = order[j], order[i]
            for k in range(0, n_teams - 1, 2):
                a, b = order[k], order[k + 1]
                lam = (teams[a] + teams[b]) if cond else 2.7
                rows.append({'date': date, 'home': f'T{a}', 'away': f'T{b}',
                             'tot': pois(max(lam, 0.3))})
    rows.sort(key=lambda r: r['date'])
    return {'Synth League': rows}


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    csvtext = ("Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
               "01/08/25,Alpha,Beta,2,1\n"
               "bad,Alpha,Beta,x,y\n"
               "02/08/2025,Gamma,Delta,0,0\n")
    ms = parse_matches(csvtext, 'mmz')
    chk(len(ms) == 2 and ms[0]['tot'] == 3 and ms[0]['date'] == '2025-08-01'
        and ms[1]['date'] == '2025-08-02',
        "parser keeps team+date, converts both date shapes, drops junk")

    # ---- the walk is strictly prior
    per = {'L': [{'date': f'2025-01-{d:02d}', 'home': 'A', 'away': 'B',
                  'tot': t} for d, t in ((1, 2), (2, 4), (3, 6), (4, 8), (5, 10))]}
    w = walk(per)
    chk(len(w) == 2 and abs(w[0]['pace'] - 4.0) < 1e-9,
        "pace at match 4 is mean of the FIRST THREE (2,4,6), its own total excluded")
    chk(abs(w[1]['pace'] - 5.0) < 1e-9,
        "and at match 5 it is (2+4+6+8)/4 -- the walk never sees the future")

    chk(_bin_of(-1.0) == 0 and _bin_of(0.0) == 2 and _bin_of(2.0) == 4,
        "pace bins land slow/neutral/fast where they should")

    # ---- a world where team pace is REAL: conditioning must ship
    rows = walk(_world(7, cond=True))
    model, ship = verdicts(rows, split='2024-01-01', perms=6,
                           log=lambda s: None)
    shipped = [k for k, v in ship.items() if v['ships']]
    chk(len(shipped) >= 2,
        f"planted team-pace world ships conditioning on 2+ rungs ({shipped})")
    d35 = model['deltas'].get('3.5', [0] * 5)
    chk(d35[0] > d35[-1],
        f"and the delta runs the right way: slow bin {d35[0]:+.3f} raises the "
        f"under, fast bin {d35[-1]:+.3f} lowers it")

    # ---- a world where totals are iid: conditioning must refuse
    rows0 = walk(_world(7, cond=False))
    _, ship0 = verdicts(rows0, split='2024-01-01', perms=6,
                        log=lambda s: None)
    chk(not any(v['ships'] for v in ship0.values()),
        "an iid world ships NOTHING -- the permutation bar holds")

    # ---- conditioned() respects its own coverage
    chk(conditioned({'means': {}, 'base': {}, 'deltas': {}}, 'X', 3.5, 2.0) is None,
        "an unmodeled league conditions to None, never to a guess")
    m2 = {'means': {'L': 2.7}, 'base': {'L': {'3.5': 0.7}},
          'deltas': {'3.5': [0.1, 0.05, 0.0, -0.05, -0.1]}}
    chk(abs(conditioned(m2, 'L', 3.5, 2.7) - 0.7) < 1e-9
        and abs(conditioned(m2, 'L', 3.5, 4.0) - 0.6) < 1e-9,
        "neutral pace returns the base; +1.3 pace lands in the fast bin at base-10")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

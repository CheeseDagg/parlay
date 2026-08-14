#!/usr/bin/env python3
"""chinhist.py — does KNOCKDOWNS ABSORBED predict getting finished?

    python3 chinhist.py             # measure on the real 17,372-bout table
    python3 chinhist.py --selftest  # synthetic worlds, signal and null

WHY. The 8/14 field audit found fighter_bouts.csv carrying 17 per-fight
stats that no report reads, and named kd_abs the most promising: "knock-
downs absorbed is a better chin proxy than 'finished Nx in N losses'".
That is a HYPOTHESIS. cardread already prints a durability line built the
naive way -- how many of a fighter's losses came by knockout -- and the
naive way has an obvious defect: a fighter who has been dropped in six
fights and survived every time reads as bulletproof until the night he
does not.

The claim is testable and this file tests it, out of sample, against the
naive alternative, with a null control. Nothing ships on the strength of
its story.

THE TEST. Walk every fighter's career in order. Before each bout, from
STRICTLY PRIOR fights only:

    kdabs   = knockdowns absorbed per 15 minutes fought
    kolost  = share of prior bouts lost by KO/TKO      (the naive proxy)

Predict: does this fighter lose by KO/TKO in THIS bout? Fit on the early
years, score on the untouched tail. Two guards, both learned the hard way:

  * the f5hist lesson -- a synthetic NULL must read flat before a finding
    counts, so the same pipeline runs on permuted features and has to
    come back with nothing;
  * no leakage -- the feature window ends the day before the bout it
    predicts, and the fit never sees a test-era row.

WHAT COUNTS AS A WIN. kd_abs earns its place only by beating kolost on
the held-out tail: lower log loss AND a monotone rate ladder. Beating it
on the training years proves nothing -- 17,000 rows will fit anything.
"""
import csv, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BOUTS = os.environ.get('UFC_BOUTS') or os.path.join(
    HERE, '..', 'UFC-ODDS', 'Github', 'data', 'fighter_bouts.csv')

MIN_PRIOR = 3        # a rate off one fight is noise, not a chin
MIN_SECS = 300       # and off five minutes fought it is worse
SPLIT = '2019-01-01'  # fit strictly before, score strictly after


def load(path=BOUTS):
    rows = []
    with open(path, newline='', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    'f': r['fighter'], 'date': r['date'],
                    'secs': int(r['secs'] or 0),
                    'kd_abs': int(r['kd_abs'] or 0),
                    'kd': int(r['kd'] or 0),
                    'lost_ko': int(r['lost_by_ko'] or 0),
                    'div': r.get('division', ''),
                })
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda r: (r['f'], r['date']))
    return rows


def features(rows):
    """One row per bout that has enough prior career to say anything.

    The window is STRICTLY prior -- the bout being predicted contributes
    nothing to its own feature, which is the whole reason this is a walk
    and not a groupby.

    'mins' rides along because a RATE hides its own sample size: zero
    knockdowns in 38 minutes and zero in 240 are the same number and not
    the same fact, and the strata below measure how much that matters."""
    out = []
    by = defaultdict(list)
    for r in rows:
        by[r['f']].append(r)
    for f, career in by.items():
        n = kdabs = secs = kos = 0
        for r in career:
            if n >= MIN_PRIOR and secs >= MIN_SECS:
                out.append({
                    'f': f, 'date': r['date'], 'n': n,
                    'kdabs': kdabs / (secs / 900.0),
                    'kolost': kos / float(n),
                    'mins': secs / 60.0,
                    'y': r['lost_ko'],
                })
            n += 1
            kdabs += r['kd_abs']
            secs += r['secs']
            kos += r['lost_ko']
    out.sort(key=lambda r: r['date'])
    return out


# Exposure strata, measured 8/14. The kd_abs ladder is monotone inside
# EVERY one of them, so the feature is real at all sample sizes -- but the
# never-dropped bin is worth 14.1% at thin exposure and 8.7% at deep, a
# 5.4-point spread hiding inside one number. A fighter is placed on his
# OWN stratum's ladder, not the pooled one.
EXPOSURE = [(0.0, 60.0, 'thin'), (60.0, 150.0, 'mid'), (150.0, 1e9, 'deep')]


def stratum(mins):
    for lo, hi, name in EXPOSURE:
        if lo <= mins < hi:
            return name
    return EXPOSURE[-1][2]


# ---------------------------------------------------------------- fitting
def _logistic(xs, ys, iters=400, lr=0.5):
    """Two-parameter logistic by plain gradient ascent. Deliberately
    small: one feature, one intercept. Anything richer would be fitting
    the walk's own structure rather than the feature."""
    a = b = 0.0
    n = float(len(xs)) or 1.0
    mu = sum(xs) / n
    sd = (sum((x - mu) ** 2 for x in xs) / n) ** 0.5 or 1.0
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(xs, ys):
            z = (x - mu) / sd
            p = 1.0 / (1.0 + math.exp(-max(-30, min(30, a + b * z))))
            ga += (y - p)
            gb += (y - p) * z
        a += lr * ga / n
        b += lr * gb / n
    return a, b, mu, sd


def _apply(m, x):
    a, b, mu, sd = m
    return 1.0 / (1.0 + math.exp(-max(-30, min(30, a + b * (x - mu) / sd))))


def logloss(ps, ys):
    e = 1e-12
    return -sum(y * math.log(max(p, e)) + (1 - y) * math.log(max(1 - p, e))
                for p, y in zip(ps, ys)) / max(len(ys), 1)


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 1.0)
    p = k / float(n)
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def ladder(rows, key, cuts):
    """Rate of getting finished, by feature bin, with Wilson bands.
    A feature that works reads MONOTONE here; one that does not reads
    like noise no matter what its log loss says."""
    out = []
    for lo, hi in zip([None] + cuts, cuts + [None]):
        sel = [r for r in rows
               if (lo is None or r[key] >= lo) and (hi is None or r[key] < hi)]
        k = sum(r['y'] for r in sel)
        lab = (f"<{hi:g}" if lo is None else
               f">={lo:g}" if hi is None else f"{lo:g}-{hi:g}")
        out.append((lab, len(sel), k, (k / len(sel) if sel else 0.0),
                    wilson(k, len(sel))))
    return out


def evaluate(rows, split=SPLIT, verbose=True):
    tr = [r for r in rows if r['date'] < split]
    te = [r for r in rows if r['date'] >= split]
    if len(tr) < 200 or len(te) < 200:
        return None
    ys_te = [r['y'] for r in te]
    base = sum(r['y'] for r in tr) / float(len(tr))
    res = {'n_train': len(tr), 'n_test': len(te), 'base': base,
           'base_ll': logloss([base] * len(te), ys_te)}
    for key in ('kdabs', 'kolost'):
        m = _logistic([r[key] for r in tr], [r['y'] for r in tr])
        res[key] = logloss([_apply(m, r[key]) for r in te], ys_te)
        res[key + '_b'] = m[1]
    if verbose:
        print(f"  train {len(tr)} bouts (<{split}), test {len(te)} (untouched)")
        print(f"  base rate finished-by-KO {base:.3f}")
        print(f"  log loss  base {res['base_ll']:.5f}"
              f"   kd_abs {res['kdabs']:.5f} (b={res['kdabs_b']:+.3f})"
              f"   kolost {res['kolost']:.5f} (b={res['kolost_b']:+.3f})")
    return res


def _logistic2(rows, keys, iters=600, lr=0.5):
    """Same fit, two features. This exists because the single-feature
    comparison answers the wrong question: 'which proxy is better' is not
    'does the second one ADD anything'. A fighter dropped six times and
    never finished is a different animal from one never dropped at all,
    and only the joint fit can say whether that difference is real."""
    n = float(len(rows)) or 1.0
    st = {}
    for k in keys:
        mu = sum(r[k] for r in rows) / n
        sd = (sum((r[k] - mu) ** 2 for r in rows) / n) ** 0.5 or 1.0
        st[k] = (mu, sd)
    a, b = 0.0, {k: 0.0 for k in keys}
    for _ in range(iters):
        ga, gb = 0.0, {k: 0.0 for k in keys}
        for r in rows:
            z = {k: (r[k] - st[k][0]) / st[k][1] for k in keys}
            lin = a + sum(b[k] * z[k] for k in keys)
            p = 1.0 / (1.0 + math.exp(-max(-30, min(30, lin))))
            d = r['y'] - p
            ga += d
            for k in keys:
                gb[k] += d * z[k]
        a += lr * ga / n
        for k in keys:
            b[k] += lr * gb[k] / n
    return a, b, st, keys


def _apply2(m, r):
    a, b, st, keys = m
    lin = a + sum(b[k] * (r[k] - st[k][0]) / st[k][1] for k in keys)
    return 1.0 / (1.0 + math.exp(-max(-30, min(30, lin))))


def joint(rows, split=SPLIT):
    """Does kd_abs add anything ON TOP of the naive proxy, out of sample?"""
    tr = [r for r in rows if r['date'] < split]
    te = [r for r in rows if r['date'] >= split]
    if len(tr) < 200 or len(te) < 200:
        return None
    ys = [r['y'] for r in te]
    solo = _logistic2(tr, ['kolost'])
    both = _logistic2(tr, ['kolost', 'kdabs'])
    return {'solo': logloss([_apply2(solo, r) for r in te], ys),
            'both': logloss([_apply2(both, r) for r in te], ys),
            'b_kolost': both[1]['kolost'], 'b_kdabs': both[1]['kdabs'],
            'n_test': len(te)}


def _permute(rows, seed=7, keys=('kdabs',)):
    """Deterministic shuffle of the FEATURE only, outcomes left where they
    are. For the joint test only kdabs moves -- permuting both would test
    a different claim (does anything predict) than the one being made
    (does kd_abs add to kolost)."""
    st = seed
    idx = list(range(len(rows)))
    for i in range(len(idx) - 1, 0, -1):
        st = (1103515245 * st + 12345) % (1 << 31)
        j = st % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    sh = [dict(r) for r in rows]
    for r, k in zip(sh, idx):
        for key in keys:
            r[key] = rows[k][key]
    return sh


PERMS = 20   # p resolves to 1/(PERMS+1) = 0.048; more costs time, not truth


def perm_test(rows, real, perms=PERMS, split=SPLIT):
    """Is the joint gain bigger than shuffling kd_abs can produce by luck?

    Adding ANY second parameter to a logistic buys a little log loss even
    on noise -- the first null shuffle here gained 0.00007 doing exactly
    that. So the bar is not 'the null must not improve', which no honest
    extra parameter can clear; it is 'the real gain must beat EVERY null
    gain'. With 20 shuffles that is a permutation test at p <= 0.048, and
    the threshold is arithmetic instead of a number I chose after seeing
    the answer."""
    real_gain = real['solo'] - real['both']
    gains = []
    for s in range(perms):
        j = joint(_permute(rows, seed=101 + 7 * s), split=split)
        if j:
            gains.append(j['solo'] - j['both'])
    if not gains:
        return False, 1.0, 0.0
    beaten = sum(1 for g in gains if g >= real_gain)
    return (beaten == 0, (beaten + 1) / float(len(gains) + 1), max(gains))


def null_control(rows, seed=7, split=SPLIT):
    """The f5hist guard. Permute the feature across rows, keeping the
    outcome where it is, and re-run the identical pipeline. A real
    finding survives; a pipeline artefact shows up here too."""
    return evaluate(_permute(rows, seed, ('kdabs', 'kolost')), split,
                    verbose=False)


# ------------------------------------------------------------- synthetic
def _world(seed, strength):
    """A career table where kd_abs DOES carry chin (strength>0) or does
    not (strength=0). Proves the pipeline can find a planted effect and,
    at strength 0, that it reports nothing."""
    st = seed
    def rnd():
        nonlocal st
        st = (1103515245 * st + 12345) % (1 << 31)
        return st / float(1 << 31)
    rows = []
    for i in range(600):
        chin = rnd()                     # 0 = granite, 1 = glass
        y = 2000 + i % 24
        for b in range(10):
            secs = 300 + int(rnd() * 600)
            kd_abs = 1 if rnd() < 0.10 + 0.45 * chin else 0
            p = 0.10 + strength * chin
            rows.append({'f': f'F{i}', 'date': f"{y + b // 2}-06-01",
                         'secs': secs, 'kd_abs': kd_abs, 'kd': 0,
                         'lost_ko': 1 if rnd() < p else 0, 'div': 'x'})
    rows.sort(key=lambda r: (r['f'], r['date']))
    return rows


KDABS_CUTS = [0.01, 0.25, 0.5, 1.0]
KOLOST_CUTS = [0.01, 0.2, 0.4]
OUT = os.path.join(HERE, 'chinhist.json')


def persist(fx, res, jt, verdict, path=OUT):
    """Write the ladder the way every other *hist in this repo does, so a
    report can place a fighter on a MEASURED rate instead of a remembered
    one. Atomic, because a half-written table read as a real one would be
    the worst possible version of this file."""
    import json, tempfile
    doc = {
        'source': os.path.relpath(BOUTS, HERE),
        'n_bouts': len(fx), 'split': SPLIT,
        'min_prior': MIN_PRIOR, 'min_secs': MIN_SECS,
        'ladder_kdabs': [{'bin': lab, 'n': n, 'finished': k, 'rate': p,
                          'lo': ci[0], 'hi': ci[1]}
                         for lab, n, k, p, ci in ladder(fx, 'kdabs', KDABS_CUTS)],
        'ladder_kolost': [{'bin': lab, 'n': n, 'finished': k, 'rate': p,
                           'lo': ci[0], 'hi': ci[1]}
                          for lab, n, k, p, ci in ladder(fx, 'kolost', KOLOST_CUTS)],
        'cuts_kdabs': KDABS_CUTS, 'cuts_kolost': KOLOST_CUTS,
        'exposure': [{'name': nm, 'lo_min': lo, 'hi_min': (None if hi > 1e8 else hi)}
                     for lo, hi, nm in EXPOSURE],
        'ladder_by_exposure': {
            nm: [{'bin': lab, 'n': n, 'finished': k, 'rate': p,
                  'lo': ci[0], 'hi': ci[1]}
                 for lab, n, k, p, ci in ladder(
                     [r for r in fx if lo <= r.get('mins', 0.0) < hi],
                     'kdabs', KDABS_CUTS)]
            for lo, hi, nm in EXPOSURE},
        'out_of_sample': res, 'joint': jt, 'verdict': verdict,
    }
    fd, tmp = tempfile.mkstemp(dir=HERE, suffix='.tmp')
    with os.fdopen(fd, 'w') as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return doc


def career_stats(rows=None):
    """{fighter: {kdabs, kolost, n, mins}} over the WHOLE career -- the
    report's view, where every fight is history. Distinct from features(),
    which deliberately withholds each bout from its own feature because it
    is predicting that bout."""
    rows = load() if rows is None else rows
    agg = defaultdict(lambda: {'kd_abs': 0, 'kd': 0, 'secs': 0, 'n': 0, 'ko': 0})
    for r in rows:
        a = agg[r['f']]
        a['kd_abs'] += r['kd_abs']; a['kd'] += r['kd']
        a['secs'] += r['secs']; a['n'] += 1; a['ko'] += r['lost_ko']
    out = {}
    for f, a in agg.items():
        if a['secs'] < MIN_SECS:
            continue
        out[f] = {'kdabs': a['kd_abs'] / (a['secs'] / 900.0),
                  'kd': a['kd'] / (a['secs'] / 900.0),
                  'kolost': a['ko'] / float(a['n']),
                  'n': a['n'], 'mins': a['secs'] / 60.0,
                  'kd_abs_raw': a['kd_abs'], 'ko_losses': a['ko']}
    return out


def main():
    quick = '--quick' in sys.argv
    rows = load()
    print(f"chinhist: {len(rows)} bout-rows from {os.path.relpath(BOUTS, HERE)}")
    fx = features(rows)
    print(f"  {len(fx)} bouts with >={MIN_PRIOR} prior fights and "
          f">={MIN_SECS}s fought\n")

    print("  FINISHED-BY-KO RATE BY PRIOR KNOCKDOWNS ABSORBED PER 15 MIN")
    for lab, n, k, p, (lo, hi) in ladder(fx, 'kdabs', KDABS_CUTS):
        print(f"    kd_abs/15 {lab:>9}  n={n:5d}  finished {k:4d}  "
              f"{p * 100:5.1f}%  [{lo * 100:4.1f}, {hi * 100:4.1f}]")
    print("\n  ... AND BY THE NAIVE PROXY (share of prior bouts lost by KO)")
    for lab, n, k, p, (lo, hi) in ladder(fx, 'kolost', KOLOST_CUTS):
        print(f"    kolost    {lab:>9}  n={n:5d}  finished {k:4d}  "
              f"{p * 100:5.1f}%  [{lo * 100:4.1f}, {hi * 100:4.1f}]")

    print("\n  OUT OF SAMPLE")
    res = evaluate(fx)
    if not res:
        print("  too few rows either side of the split -- no verdict")
        return 1
    nul = null_control(fx)
    print(f"  null control (feature permuted): kd_abs {nul['kdabs']:.5f} "
          f"vs base {nul['base_ll']:.5f}  (must be flat)")

    jt = joint(fx)
    adds = False
    if jt:
        print(f"  joint fit: kolost alone {jt['solo']:.5f}  -> "
              f"+kd_abs {jt['both']:.5f}  (gain {jt['solo'] - jt['both']:+.5f}; "
              f"b_kolost {jt['b_kolost']:+.3f}, b_kdabs {jt['b_kdabs']:+.3f})")
        if quick:
            print("  permutation test SKIPPED (--quick) -- the verdict below "
                  "is provisional and must not be quoted as measured")
            adds = None
        else:
            adds, p, worst = perm_test(fx, jt)
            print(f"  permutation test, {PERMS} shuffles of kd_abs alone: "
                  f"best null gain {worst:+.5f}, p={p:.3f}")

    beats_base = res['kdabs'] < res['base_ll']
    beats_naive = res['kdabs'] < res['kolost']
    null_flat = nul['kdabs'] >= nul['base_ll'] - 1e-4
    if beats_base and beats_naive and null_flat:
        verdict = ("kd_abs EARNS ITS PLACE -- beats both the base rate and the "
                   "naive lost-by-KO proxy on the untouched tail, null flat.")
    elif beats_base and null_flat and adds:
        verdict = ("kd_abs is the WEAKER SOLO proxy but ADDS to the naive one "
                   "out of sample, and no shuffle of it reproduces the gain. "
                   "Ship BOTH -- being dropped and being finished are different "
                   "facts about a chin. IMPROVE.md's 'better proxy' was wrong; "
                   "'second proxy' is right.")
    elif beats_base and null_flat and adds is None:
        verdict = ("PROVISIONAL (--quick skipped the permutation test): kd_abs "
                   "beats the base rate with a flat null, but whether it ADDS "
                   "to the naive proxy is unmeasured in this run.")
    elif beats_base and null_flat:
        verdict = ("kd_abs carries real signal (beats base, null flat) but "
                   "neither beats NOR adds to the naive proxy out of sample. "
                   "Print it as a stat; do not blend it.")
    elif not null_flat:
        verdict = ("REFUSED -- the permuted null also beats the base rate, so "
                   "the gain is pipeline artefact, not chin. (f5hist made "
                   "exactly this mistake.)")
    else:
        verdict = ("REFUSED -- kd_abs does not beat the base rate out of "
                   "sample. Do not ship it as a factor.")
    print(f"\n  VERDICT: {verdict}")
    persist(fx, res, jt, verdict)
    print(f"  wrote {os.path.relpath(OUT, HERE)}"
          + ("  (PROVISIONAL -- rerun without --quick)" if quick else ""))
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    # ---- the walk must not leak: a bout never feeds its own feature.
    r = [{'f': 'A', 'date': f'20{10 + i}-01-01', 'secs': 900, 'kd_abs': i,
          'kd': 0, 'lost_ko': 0, 'div': 'x'} for i in range(6)]
    fx = features(r)
    chk(len(fx) == 3, f"6-fight career yields 3 predictable bouts, not 6 ({len(fx)})")
    chk(abs(fx[0]['kdabs'] - (0 + 1 + 2) / 3.0) < 1e-9,
        "the 4th bout's feature is the sum of the FIRST THREE, its own kd_abs excluded")
    chk(fx[-1]['date'] == '2015-01-01' and abs(fx[-1]['kdabs'] - 10 / 5.0) < 1e-9,
        "and the last bout sees five fights of history, never six")

    r2 = [{'f': 'B', 'date': '2011-01-01', 'secs': 60, 'kd_abs': 0, 'kd': 0,
           'lost_ko': 0, 'div': 'x'}] * 5
    chk(features(r2) == [], f"a career of one-minute fights never clears MIN_SECS")

    chk(wilson(0, 0) == (0.0, 1.0), "an empty bin is total ignorance, not 0%")
    lo, hi = wilson(50, 100)
    chk(lo < 0.5 < hi and hi - lo > 0.15, "a 50/100 bin carries a wide honest band")

    # ---- a planted effect must be FOUND ...
    sig = features(_world(11, 0.35))
    rs = evaluate(sig, split='2014-01-01', verbose=False)
    chk(rs and rs['kdabs'] < rs['base_ll'],
        f"planted chin effect is detected out of sample "
        f"({rs['kdabs']:.5f} < {rs['base_ll']:.5f})")
    chk(rs['kdabs_b'] > 0,
        "and its sign is right: more knockdowns absorbed -> more finishes")

    # ---- ... and an ABSENT one must not be.
    nul = features(_world(11, 0.0))
    rn = evaluate(nul, split='2014-01-01', verbose=False)
    chk(rn and rn['kdabs'] >= rn['base_ll'] - 2e-4,
        f"a world with NO chin effect reports none "
        f"({rn['kdabs']:.5f} vs {rn['base_ll']:.5f})")

    # ---- the permutation control must kill a real effect
    perm = null_control(sig, split='2014-01-01')
    chk(perm and perm['kdabs'] >= perm['base_ll'] - 2e-4,
        f"permuting the feature erases the planted effect "
        f"({perm['kdabs']:.5f} vs {perm['base_ll']:.5f})")

    # ---- the permutation test is the piece that decided the real verdict,
    # so it gets pinned on a world where kd_abs is planted ON TOP of a
    # kolost that already carries most of the signal.
    jt = joint(sig, split='2014-01-01')
    chk(jt and jt['both'] < jt['solo'],
        f"the joint fit finds the planted add-on ({jt['solo']:.5f} -> {jt['both']:.5f})")
    good, p, worst = perm_test(sig, jt, perms=6, split='2014-01-01')
    chk(good and p < 0.2 and worst < jt['solo'] - jt['both'],
        f"and no shuffle of kd_abs reproduces that gain (best null {worst:+.5f} "
        f"vs real {jt['solo'] - jt['both']:+.5f}, p={p:.3f})")
    fake = dict(jt); fake['both'] = fake['solo'] - 1e-9   # a gain of nothing
    good2, p2, _ = perm_test(sig, fake, perms=6, split='2014-01-01')
    chk(not good2 and p2 > 0.2,
        f"a gain of ~zero is NOT significant -- the test can say no (p={p2:.3f})")
    chk(_permute([{'kdabs': 1.0, 'kolost': 9.0, 'y': 1}], keys=('kdabs',))[0]['kolost'] == 9.0,
        "the joint permutation moves kd_abs ONLY -- kolost must stay put or "
        "the shuffle tests a different claim than the one being made")

    lad = ladder([{'kdabs': 0.0, 'y': 0}] * 10 + [{'kdabs': 2.0, 'y': 1}] * 10,
                 'kdabs', [1.0])
    chk(lad[0][3] == 0.0 and lad[1][3] == 1.0,
        "the ladder bins on the cut, low bin clean and high bin finished")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

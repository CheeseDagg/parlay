#!/usr/bin/env python3
"""defhist.py — do STRIKING DEFENCE and TAKEDOWN DEFENCE predict the winner?

    python3 defhist.py             # measure on the real 8,686-bout table
    python3 defhist.py --selftest  # synthetic worlds, signal and null

The chin pass (chinhist) settled one of the audit's 17 unread per-fight
stats and found the audit's own headline claim was wrong. These are the
next four: sig_l/sig_a and td_l/td_a, both sides. They make the two rates
every fight preview in the world quotes and no report here computes:

    strdef  = 1 - (opponent sig strikes LANDED / opponent sig ATTEMPTED)
    tddef   = 1 - (opponent takedowns LANDED / opponent takedowns TRIED)

THE DIFFERENCE FROM chinhist, AND IT MATTERS. A chin belongs to one man:
"does he get knocked out" is a fact about him. Winning is not -- it is a
fact about a MATCHUP, and a fighter's own 62% striking defence means
nothing without the number across from it. fighter_bouts.csv turns out to
be perfectly symmetric (8,686 bouts, each listed twice, once per corner),
so every feature here is a DIFFERENTIAL: my rate minus his. That also
makes the design antisymmetric -- p(A beats B) and p(B beats A) sum to
one by construction rather than by hope.

THE BASELINE THAT HAS TO BE BEATEN is prior win rate, differenced the
same way. "Better fighters win" is free; the question is whether these
rates say anything on top of it. Same guards as the chin pass: strictly-
prior windows, a chronological split with an untouched tail, synthetic
worlds with the effect planted and absent, and a permutation test whose
threshold is arithmetic instead of chosen after seeing the answer.

A rate needs volume to mean anything, so both carry attempt floors and
the report prints what the floors COST in coverage rather than hiding it.
"""
import csv, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from chinhist import (logistic2, apply2, permute, logloss, wilson,
                      BOUTS, SPLIT)

MIN_PRIOR = 3          # fights of history before a rate is quotable
MIN_SIG_FACED = 150    # significant strikes faced; below this strdef is noise
MIN_TD_FACED = 5       # takedown attempts faced; most fighters never reach 20
PERMS = 20


def load(path=BOUTS):
    rows = []
    with open(path, newline='', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    'f': r['fighter'], 'opp': r['opp'], 'date': r['date'],
                    'secs': int(r['secs'] or 0),
                    'sig_l': int(r['sig_l'] or 0), 'sig_a': int(r['sig_a'] or 0),
                    'sig_l_opp': int(r['sig_l_opp'] or 0),
                    'sig_a_opp': int(r['sig_a_opp'] or 0),
                    'td_l': int(r['td_l'] or 0), 'td_a': int(r['td_a'] or 0),
                    'td_l_opp': int(r['td_l_opp'] or 0),
                    'td_a_opp': int(r['td_a_opp'] or 0),
                    'ctrl': int(r['ctrl'] or 0),
                    'won': int(r['won'] or 0),
                })
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda r: (r['f'], r['date']))
    return rows


def priors(rows):
    """{(fighter, date): prior-career rates} from STRICTLY earlier fights.

    Everything here is a running total taken BEFORE the bout it is keyed
    to, which is why this is a walk. Rates whose denominator has not
    cleared its floor come back None rather than as a number with nothing
    behind it -- 0/1 takedowns defended is not 0% takedown defence."""
    out = {}
    by = defaultdict(list)
    for r in rows:
        by[r['f']].append(r)
    for f, career in by.items():
        n = w = 0
        sl_op = sa_op = sl = sa = 0
        tl_op = ta_op = tl = ta = 0
        secs = ctl = 0
        for r in career:
            if n >= MIN_PRIOR:
                out[(f, r['date'])] = {
                    'n': n, 'winpct': w / float(n),
                    'strdef': (1.0 - sl_op / float(sa_op)
                               if sa_op >= MIN_SIG_FACED else None),
                    'stracc': (sl / float(sa) if sa >= MIN_SIG_FACED else None),
                    'tddef': (1.0 - tl_op / float(ta_op)
                              if ta_op >= MIN_TD_FACED else None),
                    'tdacc': (tl / float(ta) if ta >= MIN_TD_FACED else None),
                    'absorb': (sl_op / (secs / 60.0)) if secs >= 300 else None,
                    'ctrlrate': (ctl / (secs / 60.0)) if secs >= 300 else None,
                    'sig_faced': sa_op, 'td_faced': ta_op, 'mins': secs / 60.0,
                }
            n += 1
            w += r['won']
            sl_op += r['sig_l_opp']; sa_op += r['sig_a_opp']
            sl += r['sig_l']; sa += r['sig_a']
            tl_op += r['td_l_opp']; ta_op += r['td_a_opp']
            tl += r['td_l']; ta += r['td_a']
            secs += r['secs']; ctl += r['ctrl']
    return out


KEYS = ('winpct', 'strdef', 'stracc', 'tddef', 'tdacc', 'absorb', 'ctrlrate')


def matchups(rows, pri=None):
    """One row per BOUT (not per corner), oriented to a deterministic side.

    Orienting alphabetically rather than by who won is the whole guard
    against the silliest possible leak: if the row were always written
    from the winner's view, every differential would point the same way
    and the fit would score 100% on nothing at all."""
    pri = priors(rows) if pri is None else pri
    seen, out, drop = set(), [], defaultdict(int)
    for r in rows:
        a, b = r['f'], r['opp']
        key = (min(a, b), max(a, b), r['date'])
        if key in seen:
            continue
        seen.add(key)
        first = key[0]
        pa, pb = pri.get((first, r['date'])), pri.get((key[1], r['date']))
        if not pa or not pb:
            drop['no prior career'] += 1
            continue
        # y from the row we actually have, mapped onto the oriented side
        won_first = r['won'] if r['f'] == first else 1 - r['won']
        if r['won'] == 0 and r['f'] != first:
            pass                       # handled by the mapping above
        m = {'date': r['date'], 'a': first, 'b': key[1], 'y': won_first,
             'na': pa['n'], 'nb': pb['n']}
        for k in KEYS:
            m['d_' + k] = (None if pa[k] is None or pb[k] is None
                           else pa[k] - pb[k])
        out.append(m)
    out.sort(key=lambda r: r['date'])
    return out, dict(drop)


def usable(mus, keys):
    return [m for m in mus if all(m.get('d_' + k) is not None for k in keys)]


def fit_score(mus, keys, split=SPLIT):
    """Fit on the early years, score on the untouched tail."""
    rows = usable(mus, keys)
    tr = [r for r in rows if r['date'] < split]
    te = [r for r in rows if r['date'] >= split]
    if len(tr) < 200 or len(te) < 200:
        return None
    ks = ['d_' + k for k in keys]
    ys = [r['y'] for r in te]
    base = sum(r['y'] for r in tr) / float(len(tr))
    m = logistic2(tr, ks)
    return {'ll': logloss([apply2(m, r) for r in te], ys),
            'base_ll': logloss([base] * len(te), ys),
            'b': dict(m[1]), 'n_train': len(tr), 'n_test': len(te),
            'base': base,
            'acc': sum(1 for r, y in zip(te, ys)
                       if (apply2(m, r) >= 0.5) == bool(y)) / float(len(te))}


def adds(mus, base_keys, extra, perms=PERMS, split=SPLIT):
    """Does `extra` add to `base_keys` on the untouched tail, by more than
    shuffling it can produce? Both fits run on the SAME usable rows, or
    the comparison would be measuring coverage instead of signal."""
    keys = list(base_keys) + [extra]
    rows = usable(mus, keys)
    a = fit_score(rows, base_keys, split)
    b = fit_score(rows, keys, split)
    if not a or not b:
        return None
    gain = a['ll'] - b['ll']
    nulls = []
    for s in range(perms):
        sh = permute(rows, seed=101 + 7 * s, keys=('d_' + extra,))
        nb = fit_score(sh, keys, split)
        if nb:
            nulls.append(a['ll'] - nb['ll'])
    beaten = sum(1 for g in nulls if g >= gain)
    return {'n': len(rows), 'solo': a['ll'], 'both': b['ll'], 'gain': gain,
            'p': (beaten + 1) / float(len(nulls) + 1),
            'worst_null': max(nulls) if nulls else 0.0,
            'b': b['b'].get('d_' + extra, 0.0), 'acc': b['acc'],
            'acc_solo': a['acc']}


def ladder(rows, key, cuts):
    """Win rate by differential bin, with Wilson bands. Written here
    rather than imported because the outcome is 'won', not 'finished',
    and a shared helper that means two different things is a trap."""
    out = []
    for lo, hi in zip([None] + cuts, cuts + [None]):
        sel = [r for r in rows
               if r.get(key) is not None
               and (lo is None or r[key] >= lo) and (hi is None or r[key] < hi)]
        k = sum(r['y'] for r in sel)
        lab = (f"<{hi:g}" if lo is None else
               f">={lo:g}" if hi is None else f"{lo:g}..{hi:g}")
        out.append((lab, len(sel), k, (k / len(sel) if sel else 0.0),
                    wilson(k, len(sel))))
    return out


# ------------------------------------------------------------- synthetic
def _world(seed, str_strength, td_strength, n_fighters=400):
    """Careers where striking/takedown defence carry a planted amount of
    winning, or none. The rates are BUILT from counted events, not stamped
    on, so the floors and the walk are exercised the way real data does."""
    st = seed
    def rnd():
        nonlocal st
        st = (1103515245 * st + 12345) % (1 << 31)
        return st / float(1 << 31)
    skill = [rnd() for _ in range(n_fighters)]
    rows = []
    for card in range(60):
        date = f"{2005 + card // 4}-{1 + (card % 4) * 3:02d}-01"
        order = list(range(n_fighters))
        for i in range(len(order) - 1, 0, -1):
            j = int(rnd() * (i + 1))
            order[i], order[j] = order[j], order[i]
        for k in range(0, n_fighters - 1, 2):
            a, b = order[k], order[k + 1]
            ea = str_strength * (skill[a] - skill[b]) + td_strength * (skill[a] - skill[b])
            pa = 1.0 / (1.0 + pow(2.718281828, -(4.0 * ea)))
            awin = 1 if rnd() < pa else 0
            for me, you, won in ((a, b, awin), (b, a, 1 - awin)):
                sa_op = 60 + int(rnd() * 60)
                sl_op = int(sa_op * (0.65 - 0.35 * skill[me]))
                ta_op = 1 + int(rnd() * 3)
                tl_op = sum(1 for _ in range(ta_op)
                            if rnd() < (0.8 - 0.6 * skill[me]))
                rows.append({
                    'f': f'F{me}', 'opp': f'F{you}', 'date': date, 'secs': 900,
                    'sig_l': sl_op, 'sig_a': sa_op,
                    'sig_l_opp': sl_op, 'sig_a_opp': sa_op,
                    'td_l': tl_op, 'td_a': ta_op,
                    'td_l_opp': tl_op, 'td_a_opp': ta_op,
                    'ctrl': 0, 'won': won})
    rows.sort(key=lambda r: (r['f'], r['date']))
    return rows


OUT = os.path.join(HERE, 'defhist.json')


def career_rates(rows=None):
    """{fighter: rates} over the WHOLE career -- the report's view, where
    every fight is history. Same floors as the walk, so a fighter whose
    denominator is too thin gets None here too and the card prints the
    absence instead of a number nobody measured."""
    rows = load() if rows is None else rows
    agg = defaultdict(lambda: defaultdict(int))
    for r in rows:
        a = agg[r['f']]
        for k in ('sig_l', 'sig_a', 'sig_l_opp', 'sig_a_opp',
                  'td_l', 'td_a', 'td_l_opp', 'td_a_opp', 'secs', 'ctrl'):
            a[k] += r[k]
        a['n'] += 1
    out = {}
    for f, a in agg.items():
        if a['secs'] < 300:
            continue
        mins = a['secs'] / 60.0
        out[f] = {
            'n': a['n'], 'mins': mins,
            'absorb': a['sig_l_opp'] / mins,
            'output': a['sig_l'] / mins,
            'stracc': (a['sig_l'] / float(a['sig_a'])
                       if a['sig_a'] >= MIN_SIG_FACED else None),
            'strdef': (1.0 - a['sig_l_opp'] / float(a['sig_a_opp'])
                       if a['sig_a_opp'] >= MIN_SIG_FACED else None),
            'tddef': (1.0 - a['td_l_opp'] / float(a['td_a_opp'])
                      if a['td_a_opp'] >= MIN_TD_FACED else None),
            'ctrlrate': a['ctrl'] / mins,
            'td_faced': a['td_a_opp'], 'sig_faced': a['sig_a_opp'],
        }
    return out


def shipped_model(mus, shipped, split=SPLIT):
    """The joint fit over prior win rate PLUS everything that earned a
    place, saved with its standardization so a report can turn a raw
    differential into PROBABILITY POINTS.

    This exists because a differential is not a finding until it has a
    size. '+7 points of striking accuracy' sounds decisive and is worth
    0.6 points of win probability; '-2.9 strikes absorbed per minute'
    sounds mild and is worth 8. Printing the rates without the exchange
    rate invites exactly the wrong reading."""
    keys = ['winpct'] + list(shipped)
    rows = usable(mus, keys)
    tr = [r for r in rows if r['date'] < split]
    if len(tr) < 200:
        return None
    a, b, st, ks = logistic2(tr, ['d_' + k for k in keys], symmetric=True)
    return {'keys': keys, 'intercept': a, 'coef': dict(b),
            'mean': {k: v[0] for k, v in st.items()},
            'sd': {k: v[1] for k, v in st.items()}, 'n_train': len(tr)}


def points(model, diffs):
    """Probability points a set of differentials is worth, versus an
    otherwise even matchup. Returns None without a model rather than a
    zero, because 'unmeasured' and 'no effect' are different answers."""
    if not model:
        return None
    import math
    def p(d):
        lin = model['intercept'] + sum(
            model['coef'].get('d_' + k, 0.0)
            * ((d.get(k, 0.0) - model['mean']['d_' + k]) / model['sd']['d_' + k])
            for k in model['keys'])
        return 1.0 / (1.0 + math.exp(-max(-30, min(30, lin))))
    return (p(diffs) - p({})) * 100.0


def persist(mus, solo, verdicts, path=OUT):
    """Atomic, like every other *hist here. Carries the REFUSALS too --
    a report that only remembers what worked will re-propose striking
    defence next month."""
    import json, tempfile
    doc = {
        'source': os.path.relpath(BOUTS, HERE), 'n_bouts': len(mus),
        'split': SPLIT, 'min_sig_faced': MIN_SIG_FACED,
        'min_td_faced': MIN_TD_FACED, 'perms': PERMS,
        'baseline': solo,
        'tested': {k: {'adds': ok, **{kk: vv for kk, vv in r.items()}}
                   for k, ok, r in verdicts},
        'shipped': [k for k, ok, _ in verdicts if ok],
        'refused': [k for k, ok, _ in verdicts if not ok],
        'shipped_model': shipped_model(mus, [k for k, ok, _ in verdicts if ok]),
        'ladders': {k: [{'bin': lab, 'n': n, 'won': w, 'rate': p,
                         'lo': ci[0], 'hi': ci[1]}
                        for lab, n, w, p, ci in ladder(mus, 'd_' + k, cuts)]
                    for k, cuts in (('strdef', [-0.06, -0.02, 0.02, 0.06]),
                                    ('tddef', [-0.3, -0.1, 0.1, 0.3]),
                                    ('stracc', [-0.06, -0.02, 0.02, 0.06]),
                                    ('absorb', [-1.5, -0.5, 0.5, 1.5]))},
    }
    fd, tmp = tempfile.mkstemp(dir=HERE, suffix='.tmp')
    with os.fdopen(fd, 'w') as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return doc


def main():
    rows = load()
    mus, drop = matchups(rows)
    print(f"defhist: {len(rows)} corner-rows -> {len(mus)} bouts with prior "
          f"career on BOTH sides ({drop.get('no prior career', 0)} dropped)")
    cov = {k: sum(1 for m in mus if m['d_' + k] is not None) for k in KEYS}
    print("  coverage after the attempt floors "
          f"(sig>={MIN_SIG_FACED}, td>={MIN_TD_FACED} faced, both corners):")
    for k in KEYS:
        print(f"    d_{k:<7} {cov[k]:5d} bouts  ({cov[k] * 100.0 / max(len(mus), 1):.0f}%)")

    print("\n  WIN RATE BY DIFFERENTIAL (positive = our side is better)")
    for k, cuts in (('strdef', [-0.06, -0.02, 0.02, 0.06]),
                    ('tddef', [-0.3, -0.1, 0.1, 0.3])):
        print(f"    d_{k}")
        for lab, n, w, p, (lo, hi) in ladder(mus, 'd_' + k, cuts):
            print(f"      {lab:>12}  n={n:5d}  won {w:5d}  {p * 100:5.1f}%  "
                  f"[{lo * 100:4.1f}, {hi * 100:4.1f}]")

    print("\n  OUT OF SAMPLE -- can each rate add to prior win rate?")
    solo = fit_score(mus, ['winpct'])
    if solo:
        print(f"    d_winpct alone: log loss {solo['ll']:.5f} vs base "
              f"{solo['base_ll']:.5f}, {solo['acc'] * 100:.1f}% on "
              f"{solo['n_test']} untouched bouts")
    verdicts = []
    for extra in ('strdef', 'tddef', 'stracc', 'absorb', 'ctrlrate'):
        r = adds(mus, ['winpct'], extra)
        if not r:
            print(f"    d_{extra}: too few usable bouts either side of the "
                  f"split -- no verdict, and none invented")
            continue
        ok = r['p'] <= 0.05 and r['gain'] > 0
        print(f"    +d_{extra:<7} n={r['n']:5d}  {r['solo']:.5f} -> "
              f"{r['both']:.5f}  gain {r['gain']:+.5f}  "
              f"(best null {r['worst_null']:+.5f}, p={r['p']:.3f})  "
              f"acc {r['acc_solo'] * 100:.1f} -> {r['acc'] * 100:.1f}%  "
              f"{'ADDS' if ok else 'no'}")
        verdicts.append((extra, ok, r))

    keep = [v for v in verdicts if v[1]]
    persist(mus, solo, verdicts)
    print()
    if keep:
        print("  VERDICT: " + ', '.join(f"d_{k}" for k, _, _ in keep)
              + " earn a place beside prior win rate -- each beat every one "
                "of 20 shuffles of itself on the untouched tail.")
        for k, _, r in keep:
            print(f"    d_{k}: coefficient {r['b']:+.3f}, "
                  f"accuracy {r['acc_solo'] * 100:.1f} -> {r['acc'] * 100:.1f}%")
    else:
        print("  VERDICT: REFUSED -- no rate adds to prior win rate out of "
              "sample once its own shuffles are the bar. Print them as "
              "context if you like; do not price off them.")
    ref = [k for k, ok, _ in verdicts if not ok]
    if ref:
        print("  REFUSED and recorded so it is not re-proposed: "
              + ', '.join('d_' + k for k in ref))
    print(f"  wrote {os.path.relpath(OUT, HERE)}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    # ---- the walk is strictly prior
    r = [{'f': 'A', 'opp': 'B', 'date': f'20{10 + i}-01-01', 'secs': 900,
          'sig_l': 10, 'sig_a': 100, 'sig_l_opp': i * 10, 'sig_a_opp': 100,
          'td_l': 0, 'td_a': 0, 'td_l_opp': 0, 'td_a_opp': 1, 'ctrl': 0,
          'won': 1} for i in range(6)]
    p = priors(r)
    chk(len(p) == 3, f"6 fights yield 3 quotable priors, not 6 ({len(p)})")
    got = p[('A', '2013-01-01')]['strdef']
    chk(abs(got - (1 - (0 + 10 + 20) / 300.0)) < 1e-9,
        "the 4th bout's strdef uses the FIRST THREE only, its own excluded")
    chk(p[('A', '2013-01-01')]['tddef'] is None,
        f"3 takedown attempts faced is under the {MIN_TD_FACED} floor -> None, "
        f"never a number")
    chk(p[('A', '2015-01-01')]['tddef'] is not None,
        f"and at {MIN_TD_FACED} faced the rate appears")

    # ---- orientation must not leak the winner
    two = [{'f': 'Zed', 'opp': 'Abe', 'date': '2013-01-01', 'secs': 900,
            'sig_l': 1, 'sig_a': 1, 'sig_l_opp': 1, 'sig_a_opp': 1,
            'td_l': 0, 'td_a': 0, 'td_l_opp': 0, 'td_a_opp': 0, 'ctrl': 0,
            'won': 1}]
    pri = {('Abe', '2013-01-01'): dict(n=5, winpct=0.2, strdef=0.5, stracc=0.5,
                                       tddef=0.5, tdacc=0.5, absorb=1.0,
                                       ctrlrate=1.0, sig_faced=999,
                                       td_faced=99, mins=99),
           ('Zed', '2013-01-01'): dict(n=5, winpct=0.8, strdef=0.6, stracc=0.5,
                                       tddef=0.5, tdacc=0.5, absorb=1.0,
                                       ctrlrate=1.0, sig_faced=999,
                                       td_faced=99, mins=99)}
    mus, _ = matchups(two, pri)
    chk(len(mus) == 1 and mus[0]['a'] == 'Abe' and mus[0]['y'] == 0,
        "the bout orients ALPHABETICALLY and y follows the orientation -- Zed "
        "won, so the Abe-side row is a loss")
    chk(abs(mus[0]['d_winpct'] - (0.2 - 0.8)) < 1e-9,
        "and the differential is oriented the same way, not by who won")
    chk(len(matchups(two + [dict(two[0], f='Abe', opp='Zed', won=0)], pri)[0]) == 1,
        "both corners of one bout collapse to ONE row, never two")

    # ---- a planted effect is found ...
    sig = _world(5, 1.0, 1.0)
    ms, _ = matchups(sig)
    fs = fit_score(ms, ['strdef'], split='2011-01-01')
    chk(fs and fs['ll'] < fs['base_ll'],
        f"planted defensive skill is detected out of sample "
        f"({fs['ll']:.5f} < {fs['base_ll']:.5f})")
    a = adds(ms, ['winpct'], 'strdef', perms=6, split='2011-01-01')
    chk(a and a['gain'] > 0 and a['p'] <= 0.2,
        f"and it ADDS to prior win rate, beating its own shuffles "
        f"(gain {a['gain']:+.5f}, p={a['p']:.3f})")

    # ---- ... and an absent one is not
    nul = _world(5, 0.0, 0.0)
    mn, _ = matchups(nul)
    an = adds(mn, ['winpct'], 'strdef', perms=6, split='2011-01-01')
    chk(an is None or an['p'] > 0.2,
        f"a world where defence does not decide fights reports nothing "
        f"(p={an['p']:.3f})" if an else "no verdict where there is nothing")

    # ---- the comparison must not be measuring coverage
    mixed = [dict(m) for m in ms[:400]]
    for m in mixed[:200]:
        m['d_strdef'] = None
    r1 = adds(mixed, ['winpct'], 'strdef', perms=2, split='2011-01-01')
    chk(r1 is None or r1['n'] == len(usable(mixed, ['winpct', 'strdef'])),
        "both fits run on the SAME usable rows -- a rate cannot win by being "
        "missing on the bouts it would have got wrong")

    lad = ladder([{'d_x': -1.0, 'y': 0}] * 10 + [{'d_x': 1.0, 'y': 1}] * 10
                 + [{'d_x': None, 'y': 1}] * 5, 'd_x', [0.0])
    chk(lad[0][1] == 10 and lad[1][1] == 10 and lad[0][3] == 0.0,
        "the ladder bins on the cut and drops None rows rather than binning them at 0")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

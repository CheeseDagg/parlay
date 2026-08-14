#!/usr/bin/env python3
"""cardread.py — the whole card: who wins each fight, and how, with receipts.

    python3 cardread.py            # full card read from live pin + Greco
    python3 cardread.py --selftest

"Tell me who wins every fight Saturday and how." Nobody can. What the data
CAN say, per bout: the market's cleaned win probability, and a method mix
built from how the likely winner actually wins AND how the likely loser
actually loses. This file says exactly that and nothing braver.

WHERE EVERY NUMBER COMES FROM:
  * win probability -- the pin's cross-book consensus (parsed_odds.json,
    cons1/cons2: 16 books de-vigged). Rule 23 stands: no override past
    five points, and this file overrides nothing at all;
  * method mix -- the winner's win-by split and the loser's lose-by split,
    EACH shrunk n/(n+8) toward the division's MEASURED finish mix
    (ufchist.json, 5,599 modern bouts), then averaged and renormalized.
    Averaging the two views is an ASSUMPTION (a knockout needs a thrower
    and a chin), stated here rather than hidden;
  * the main event uses the TITLE base (dec 44 / ko 38 / sub 18, n=241)
    -- the feed's title flag says False but the booking is a five-round
    title defence; the override is this line and the TITLE set below;
  * a fighter with no UFC record prices off the division base ALONE and
    is flagged BLIND -- rule 37: an honest fallback that looks worse
    beats an invented number that looks complete.

Greco's dataset is fetched live (reachable from this container, verified
8/13); ufcform.py's parsers are reused rather than re-written.
"""
import csv, io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ufcform

HERE = os.path.dirname(os.path.abspath(__file__))
UFCODDS = os.environ.get('UFCODDS') or os.path.join(HERE, '..', 'UFC-ODDS')
SHRINK = 8                     # fights.py's n/(n+8): one short career = half a vote
TITLE = {'islam makhachev|ian machado garry'}


def base_mix(division, title, hist):
    """Measured finish mix for the bout's context, normalized over dec/ko/sub."""
    row = hist['title'] if title else (hist.get('divisions') or {}).get(division)
    if not row:
        row = {'dec': 0.47, 'ko': 0.34, 'sub': 0.19}     # pooled modern shape
    s = row['dec'] + row['ko'] + row['sub']
    return {m: row[m] / s for m in ('dec', 'ko', 'sub')}


def shrunk(split, base):
    """A profile() split ({'dec':frac,...,'n':k} or None) shrunk toward base.
    None (no wins yet / never lost) is ALL base -- absence of evidence prices
    as the division, never as zero."""
    if not split or not split.get('n'):
        return dict(base)
    n = split['n']
    w = n / (n + float(SHRINK))
    out = {m: w * split.get(m, 0.0) + (1 - w) * base[m] for m in ('dec', 'ko', 'sub')}
    s = sum(out.values())
    return {m: v / s for m, v in out.items()}


def method_mix(winner_winby, loser_loseby, base):
    """How this particular win happens, if it happens: average of the
    winner's shrunk win-by and the loser's shrunk lose-by, renormalized."""
    a, b = shrunk(winner_winby, base), shrunk(loser_loseby, base)
    out = {m: (a[m] + b[m]) / 2 for m in ('dec', 'ko', 'sub')}
    s = sum(out.values())
    return {m: v / s for m, v in out.items()}


def load_card():
    """Bout order + divisions from the pin repo's card csv, prices from the pin."""
    pin = json.load(open(os.path.join(UFCODDS, 'Github', 'odds', 'parsed_odds.json')))
    rows = list(csv.DictReader(open(os.path.join(UFCODDS, 'Github', 'odds', 'upcoming.csv'))))
    bouts = []
    for r in rows:
        f1, f2 = r['R_fighter'], r['B_fighter']
        key = None
        for k, o in pin.items():
            names = {ufcform.norm(o.get('f1', '')), ufcform.norm(o.get('f2', ''))}
            if names == {ufcform.norm(f1), ufcform.norm(f2)}:
                key = k
                break
        if key is None:
            continue
        o = pin[key]
        # orient consensus to the csv's R/B order
        flip = ufcform.norm(o['f1']) != ufcform.norm(f1)
        p1 = o['cons2'] if flip else o['cons1']
        fd = next((b for b in o.get('books', []) if b[0] == 'FanDuel'), None)
        fd1 = (fd[2] if flip else fd[1]) if fd else None
        bouts.append({'f1': f1, 'f2': f2, 'wc': r['weight_class'],
                      'p1': p1, 'fd1': fd1,
                      'title': f"{ufcform.norm(f1)}|{ufcform.norm(f2)}" in TITLE})
    return bouts


def read_bout(bt, greco, hist):
    """Everything sayable about one bout, as a dict the printer formats."""
    base = base_mix(bt['wc'], bt['title'], hist)
    sides = {}
    for who in ('f1', 'f2'):
        rec, how = ufcform.record_of(greco, bt[who])
        sides[who] = {'name': bt[who], 'rec': rec,
                      'prof': ufcform.profile(rec) if rec else None,
                      'blind': rec is None}
    fav, dog = ('f1', 'f2') if bt['p1'] >= 0.5 else ('f2', 'f1')
    pf = bt['p1'] if fav == 'f1' else 1 - bt['p1']
    fv, dg = sides[fav], sides[dog]
    fmix = method_mix(fv['prof']['win_by'] if fv['prof'] else None,
                      dg['prof']['lose_by'] if dg['prof'] else None, base)
    dmix = method_mix(dg['prof']['win_by'] if dg['prof'] else None,
                      fv['prof']['lose_by'] if fv['prof'] else None, base)
    return {'fav': fv, 'dog': dg, 'p_fav': pf, 'fmix': fmix, 'dmix': dmix,
            'base': base, 'wc': bt['wc'], 'title': bt['title'],
            'fd1': bt['fd1'], 'f1': bt['f1'],
            'age_line': age_line(fv['name'], dg['name'], bt.get('ages') or {}),
            'ridx': bt.get('ridx') or {},
            'chin': bt.get('chin') or {}, 'chinlad': bt.get('chinlad'),
            'strk': bt.get('strk') or {}, 'strklad': bt.get('strklad')}


AGE_OLD = 38          # where "veteran" starts costing, per the blend's age block


def ages(card_date):
    """{norm_name: age_on_card} from the same DOB cache the model's age block
    uses. Age was available all along and was NOT printed until Ryan pointed
    out, 8/14, that Barboza is 40 and Wells is 40 on a ticket I had already
    'double-checked'. A factor the model uses and the report omits is a
    corner cut."""
    import datetime, sys
    sys.path.insert(0, os.path.join(UFCODDS, 'Github'))
    try:
        import ufc_blend_predict as B
        dobs = B.load_meta(B.META_CACHE)
    except Exception:
        return {}
    try:
        cd = datetime.date.fromisoformat(str(card_date)[:10])
    except Exception:
        cd = datetime.date.today()
    return {k: round((cd - v).days / 365.25, 1) for k, v in dobs.items()}


def age_line(a_name, b_name, tbl):
    """One line naming both ages, and the 38+ side if there is one."""
    import re
    def look(n):
        k = re.sub(r'[^a-z ]', '', n.lower()).strip()
        return tbl.get(k) or next((v for kk, v in tbl.items()
                                   if kk.split()[-1:] == k.split()[-1:]), None)
    x, y = look(a_name), look(b_name)
    if x is None or y is None:
        return None
    out = f"age {x} vs {y}"
    if y >= AGE_OLD:
        out += f"  << {b_name.split()[-1]} is {y:.0f}"
    if x >= AGE_OLD:
        out += f"  << OUR SIDE {a_name.split()[-1]} is {x:.0f}"
    return out


def ratings_idx():
    """Fighter rows from ufc_ratings.json, keyed by name.

    THE 8/14 AUDIT. 27 fields in this file were carried and read by NO
    report -- including sos_pct, which I hand-recomputed from scratch the
    same afternoon while it sat here. Only fields whose meaning was
    verified against the widget's own copy are used:
      sos_pct       percentile, strength of schedule
      ctrl_def_pct  percentile, control/grappling defence
      ranked_record [W, L] against ranked opponents
    cardio_rounds is deliberately NOT used as a quality signal: the widget
    says "Cardio needs round-3+ data", i.e. it is the SAMPLE SIZE behind
    the cardio rating. Turner's 3 means three deep rounds on record, not
    bad cardio -- exactly the misread that guessing would have produced."""
    try:
        d = json.load(open(os.path.join(UFCODDS, 'Github', 'output',
                                        'ufc_ratings.json')))
    except Exception:
        return {}
    return {f['name']: f for f in d.get('fighters', []) + d.get('prospects', [])}


def skill_line(name, idx):
    """SoS / control-defence / ranked record for one fighter, or None."""
    f = idx.get(name)
    if not f:
        return None
    bits = []
    if f.get('sos_pct') is not None:
        bits.append(f"SoS {f['sos_pct']}th")
    if f.get('ctrl_def_pct') is not None:
        bits.append(f"ctrl-def {f['ctrl_def_pct']}th")
    rr = f.get('ranked_record')
    bits.append(f"vs ranked {rr[0]}-{rr[1]}" if rr else "never faced a ranked opponent")
    return '  '.join(bits) if bits else None


def chin_idx():
    """Career knockdowns-absorbed rate per fighter, plus the MEASURED
    ladder those rates sit on (chinhist.json).

    The 8/14 audit called kd_abs 'a better chin proxy' than counting
    finishes in losses. chinhist measured that and the audit was WRONG:
    as a solo predictor kd_abs LOSES to the naive proxy out of sample
    (0.43403 vs 0.43295). What it does do is ADD to it -- joint log loss
    0.43193, and none of 20 shuffles of kd_abs got near that gain
    (best +0.00005 vs the real +0.00102, p=0.048). So both print, and
    neither is called the better one."""
    try:
        import chinhist
        tbl = chinhist.career_stats()
        lad = json.load(open(os.path.join(HERE, 'chinhist.json')))
    except Exception:
        return {}, None
    return tbl, lad


def _stratum(mins, lad):
    """Which exposure ladder this fighter's own sample earns."""
    for e in (lad or {}).get('exposure') or []:
        if mins >= e['lo_min'] and (e['hi_min'] is None or mins < e['hi_min']):
            return e['name']
    return None


def _chin_bin(rate, lad, mins=None):
    """Where a rate lands on the measured ladder.

    Conditioned on EXPOSURE when the fighter's own fight time is known,
    because a rate hides its sample size: 'never dropped' is worth 14.1%
    on under an hour of tape and 8.7% on 150+ minutes (chinhist, 8/14).
    Kaue Fernandes has 38 minutes; reading him off the pooled 12.5% would
    have flattered a chin nobody has tested."""
    if not lad:
        return None
    cuts = lad.get('cuts_kdabs') or []
    i = sum(1 for c in cuts if rate >= c)
    rows = None
    st = _stratum(mins, lad) if mins is not None else None
    if st:
        rows = (lad.get('ladder_by_exposure') or {}).get(st)
        # A stratum bin can be EMPTY (no thin-exposure fighter can post a
        # rate of 0.01-0.25 -- one knockdown in 40 minutes is 0.375). An
        # empty bin is no evidence, so fall back rather than print a 0%.
        if rows and i < len(rows) and not rows[i]['n']:
            rows, st = None, None
    if not rows:
        rows = lad.get('ladder_kdabs') or []
    if i >= len(rows):
        return None
    out = dict(rows[i])
    out['stratum'] = st
    return out


def chin_line(name, tbl, lad):
    """Both chin facts on one line, each with the number behind it."""
    f = tbl.get(name)
    if not f:
        return None
    out = (f"dropped {f['kdabs']:.2f}/15min "
           f"({f['kd_abs_raw']} KD absorbed in {f['mins']:.0f} min)")
    b = _chin_bin(f['kdabs'], lad, f.get('mins'))
    if b:
        st = f" @{b['stratum']} exposure" if b.get('stratum') else " (pooled)"
        out += (f" -> bin {b['bin']}{st}, {b['rate'] * 100:.0f}% of "
                f"{b['n']} such bouts ended in a KO loss")
    out += (f" | {f['ko_losses']} KO loss(es) in {f['n']} fights"
            if f['ko_losses'] else f" | never KO'd in {f['n']} fights")
    return out


def strike_idx():
    """Career striking/takedown rates, plus what defhist measured about them."""
    try:
        import defhist
        return defhist.career_rates(), json.load(
            open(os.path.join(HERE, 'defhist.json')))
    except Exception:
        return {}, None


def strike_points(a_name, b_name, tbl, lad):
    """What the shipped rates are WORTH, in probability points, for this
    matchup. Never an override -- rule 23 clamps any read to five points,
    and this is one input among the market's sixteen books."""
    x, y = tbl.get(a_name), tbl.get(b_name)
    if not x or not y or not lad:
        return None
    try:
        import defhist
    except Exception:
        return None
    m = lad.get('shipped_model')
    d = {}
    for k in (m or {}).get('keys', []):
        if k == 'winpct':
            continue
        if x.get(k) is None or y.get(k) is None:
            return None
        d[k] = x[k] - y[k]
    return defhist.points(m, d)


def strike_line(a_name, b_name, tbl, lad=None):
    """The two rates that EARNED a place, as a matchup differential.

    defhist tested four on 3,897 bouts with prior career on both sides,
    against prior win rate, on an untouched 2019+ tail:

      strikes ABSORBED per minute  ADDS (p=0.048, 57.2 -> 58.6% accuracy)
      striking ACCURACY            ADDS (p=0.048, 58.0 -> 58.5%)
      takedown defence %           did NOT clear the bar (p=0.095) -- its
                                   ladder is clean and monotone, one of 20
                                   shuffles beat it, so it is printed and
                                   NOT priced off
      striking defence %           REFUSED outright: the gain is NEGATIVE
                                   out of sample and the ladder is not
                                   monotone (42/47/54/47/54). This is the
                                   rate every preview quotes, so it is
                                   named here as measured-useless rather
                                   than quietly dropped.

    Absorbed-per-minute and defence% are the same fight seen two ways, and
    only the volume one works: slipping half of a barrage still means the
    other half landed."""
    x, y = tbl.get(a_name), tbl.get(b_name)
    if not x or not y:
        return None
    out = (f"absorbed/min {x['absorb']:.1f} vs {y['absorb']:.1f} "
           f"({x['absorb'] - y['absorb']:+.1f})")
    if x.get('stracc') is not None and y.get('stracc') is not None:
        out += (f" | accuracy {x['stracc'] * 100:.0f}% vs {y['stracc'] * 100:.0f}%"
                f" ({(x['stracc'] - y['stracc']) * 100:+.0f})")
    if x.get('tddef') is not None and y.get('tddef') is not None:
        out += (f" | TD-def {x['tddef'] * 100:.0f}% vs {y['tddef'] * 100:.0f}%"
                f" (not priced, p=0.095)")
    pts = strike_points(a_name, b_name, tbl, lad)
    if pts is not None:
        out += (f"\n    -> worth {pts:+.1f} pts to {a_name.split()[-1]} "
                f"vs an even matchup (clamp 5, rule 23)")
    return out


def durability(prof, name):
    lb = prof['lose_by'] if prof else None
    if not prof:
        return None
    if not lb:
        return f"{name} NEVER LOST in UFC"
    fin = round((lb.get('ko', 0) + lb.get('sub', 0)) * lb['n'])
    if fin == 0:
        return f"{name} never finished ({lb['n']} losses, all dec)"
    return f"{name} finished {fin}x in {lb['n']} losses"


def print_read(r):
    t = ' — TITLE (5rd, title base)' if r['title'] else ''
    fdtxt = f" FD {r['fd1']:+d}" if r['fd1'] is not None and r['fav']['name'] == r['f1'] \
        else (f" FD dog side" if r['fd1'] is None else '')
    print(f"\n{r['fav']['name']} over {r['dog']['name']}  "
          f"{r['p_fav']*100:.0f}%  ({r['wc']}{t})")
    fm, dm = r['fmix'], r['dmix']
    pf, pd_ = r['p_fav'], 1 - r['p_fav']
    print("  by: " + '  '.join(f"{m} {pf*fm[m]*100:.0f}%"
                               for m in sorted(fm, key=fm.get, reverse=True))
          + f"   (outright, of {pf*100:.0f}%)")
    print(f"  {r['dog']['name']} {pd_*100:.0f}%: "
          + '  '.join(f"{m} {pd_*dm[m]*100:.0f}%"
                      for m in sorted(dm, key=dm.get, reverse=True)))
    al = r.get('age_line')
    if al:
        print(f"  {al}")
    _st = strike_line(r['fav']['name'], r['dog']['name'], r.get('strk') or {},
                      r.get('strklad'))
    if _st:
        print(f"  {_st}")
    for _s in (r['fav'], r['dog']):
        _sk = skill_line(_s['name'], r.get('ridx') or {})
        if _sk:
            print(f"  {_s['name']}: {_sk}")
    for s in (r['fav'], r['dog']):
        if s['blind']:
            print(f"  !! {s['name']}: NO UFC RECORD -- method is the division "
                  f"base alone, priced BLIND")
        else:
            d = durability(s['prof'], s['name'])
            if d:
                print(f"  {d}")
            c = chin_line(s['name'], r.get('chin') or {}, r.get('chinlad'))
            if c:
                print(f"    {c}")


def main():
    hist = json.load(open(os.path.join(HERE, 'ufchist.json')))
    print("fetching Greco results...", flush=True)
    ev = ufcform.parse_events(ufcform.get(f"{ufcform.RAW}/ufc_event_details.csv"))
    greco = ufcform.parse_bouts(ufcform.get(f"{ufcform.RAW}/ufc_fight_results.csv"), ev)
    bouts = load_card()
    _ages, _ridx = ages('2026-08-15'), ratings_idx()
    _chin, _chinlad = chin_idx()
    _strk, _strklad = strike_idx()
    for _b in bouts:
        _b['ages'] = _ages
        _b['ridx'] = _ridx
        _b['chin'] = _chin
        _b['chinlad'] = _chinlad
        _b['strk'] = _strk
        _b['strklad'] = _strklad
    print(f"{len(bouts)} bouts on the pin; consensus of 16 books; method = "
          f"winner's win-by x loser's lose-by, shrunk to measured bases "
          f"(ufchist n=5599). NOT certainties -- the mix is the claim.")
    for bt in bouts:
        print_read(read_bout(bt, greco, hist))
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    base = {'dec': 0.42, 'ko': 0.40, 'sub': 0.18}
    s = shrunk({'dec': 0.0, 'ko': 0.78, 'sub': 0.22, 'n': 9}, base)
    chk(0.15 < s['dec'] < 0.25,
        f"0 decisions in 9 wins shrinks to ~{s['dec']*100:.0f}% dec, not 0% -- "
        "Abdul-Malik's whole point: 0-for-9 is not a 0% truth")
    chk(abs(sum(s.values()) - 1) < 1e-9, "shrunk mixes renormalize")
    chk(shrunk(None, base) == base,
        "no record -> the division base alone, never zeros")

    never_lost = method_mix({'dec': 0.35, 'ko': 0.18, 'sub': 0.47, 'n': 17},
                            None, base)
    chk(abs(sum(never_lost.values()) - 1) < 1e-9 and never_lost['sub'] > base['sub'],
        "an opponent with no losses contributes the base, and a sub-heavy "
        "winner still pulls the mix toward sub")
    a_only = shrunk({'dec': 0.35, 'ko': 0.18, 'sub': 0.47, 'n': 17}, base)
    chk(abs(never_lost['sub'] - (a_only['sub'] + base['sub']) / 2 /
            sum((a_only[m] + base[m]) / 2 for m in a_only)) < 1e-9,
        "the mix is exactly the stated average -- no hidden weighting")

    chk(base_mix('Lightweight', False,
                 {'divisions': {'Lightweight': {'dec': 0.4742, 'ko': 0.3373,
                                                'sub': 0.1861, 'other': 0.0024}},
                  'title': {}})['dec'] > 0.47,
        "a division's MEASURED mix is used and renormalized over the three")
    tb = base_mix('Welterweight', True,
                  {'divisions': {}, 'title': {'dec': 0.4357, 'ko': 0.3776,
                                              'sub': 0.1826, 'other': 0.0041}})
    chk(abs(tb['ko'] - 0.3776 / (0.4357 + 0.3776 + 0.1826)) < 1e-6,
        "a title bout prices off the five-round title base instead")

    greco = ufcform.parse_bouts(
        "EVENT,BOUT,OUTCOME,WEIGHTCLASS,METHOD\n"
        "E1,Al Pha vs. Be Ta,W/L,Middleweight,KO/TKO\n"
        "E1,Al Pha vs. Ce Ta,W/L,Middleweight,Submission\n"
        "E1,Al Pha vs. De Ta,L/W,Middleweight,Decision - Unanimous\n",
        {'E1': 2025})
    r = read_bout({'f1': 'Al Pha', 'f2': 'Zz Top', 'wc': 'Middleweight',
                   'p1': 0.7, 'fd1': -250, 'title': False},
                  greco, {'divisions': {'Middleweight': {'dec': 0.42, 'ko': 0.40,
                                                         'sub': 0.18}},
                          'title': {}})
    chk(r['fav']['name'] == 'Al Pha' and r['dog']['blind'],
        "an opponent absent from the dataset is flagged BLIND, not zeroed")
    chk(abs(sum(r['fmix'].values()) - 1) < 1e-9
        and abs(sum(r['dmix'].values()) - 1) < 1e-9,
        "both sides' mixes are proper distributions, so outright numbers "
        "sum to each side's win probability")
    tbl = {'edson barboza': 40.6, 'esteban ribovics': 30.3,
           'islam makhachev': 34.8, 'ian machado garry': 28.7}
    al = age_line('Esteban Ribovics', 'Edson Barboza', tbl)
    chk(al and 'Barboza is 41' in al,
        "a 40-year-old opponent is NAMED on the bout line -- Ryan had to "
        "point out Barboza's age on a ticket I had already double-checked")
    al2 = age_line('Islam Makhachev', 'Ian Machado Garry', tbl)
    chk(al2 and '<<' not in al2,
        "an ordinary age gap prints both ages and no flag")
    chk(age_line('Nobody Here', 'Ian Machado Garry', {}) is None,
        "no DOB -> no age line, never a guessed age")

    ridx = {'Kaue Fernandes': {'sos_pct': 2, 'ctrl_def_pct': 46,
                               'ranked_record': None, 'cardio_rounds': None},
            'Islam Makhachev': {'sos_pct': 98, 'ctrl_def_pct': 96,
                                'ranked_record': [11, 1]}}
    sl = skill_line('Kaue Fernandes', ridx)
    chk(sl and 'SoS 2th' in sl and 'never faced a ranked opponent' in sl,
        "the 8/14 audit fields print: a 2nd-percentile schedule and a fighter "
        "who has never met a ranked opponent are said out loud")
    sl2 = skill_line('Islam Makhachev', ridx)
    chk(sl2 and 'ctrl-def 96th' in sl2 and 'vs ranked 11-1' in sl2,
        "control defence and ranked record print for the other corner too")
    chk(skill_line('Nobody', ridx) is None,
        "a fighter absent from ratings prints nothing, never a guess")
    chk('cardio_rounds' not in skill_line('Kaue Fernandes', ridx),
        "cardio_rounds is NOT reported as quality -- it is the sample size "
        "behind the cardio rating (widget: 'Cardio needs round-3+ data')")

    # ---- CHIN. The 8/14 audit's headline guess ("kd_abs is a BETTER chin
    # proxy") was measured by chinhist and came back wrong -- it is the
    # weaker solo predictor and only earns a place as a SECOND one. So the
    # line must carry both facts, and must never rank them.
    _lad = {'cuts_kdabs': [0.01, 0.25, 0.5, 1.0],
            'ladder_kdabs': [{'bin': '<0.01', 'n': 4222, 'rate': 0.125},
                             {'bin': '0.01-0.25', 'n': 2245, 'rate': 0.159},
                             {'bin': '0.25-0.5', 'n': 2465, 'rate': 0.184},
                             {'bin': '0.5-1', 'n': 1260, 'rate': 0.237},
                             {'bin': '>=1', 'n': 362, 'rate': 0.243}]}
    _ct = {'Glass Joe': {'kdabs': 1.4, 'kd': 0.0, 'kolost': 0.6, 'n': 5,
                         'mins': 30.0, 'kd_abs_raw': 4, 'ko_losses': 3},
           'Granite Sam': {'kdabs': 0.0, 'kd': 0.5, 'kolost': 0.0, 'n': 9,
                           'mins': 120.0, 'kd_abs_raw': 0, 'ko_losses': 0},
           'Dropped Never Out': {'kdabs': 0.7, 'kd': 0.1, 'kolost': 0.0,
                                 'n': 8, 'mins': 90.0, 'kd_abs_raw': 6,
                                 'ko_losses': 0}}
    _lad['exposure'] = [{'name': 'thin', 'lo_min': 0.0, 'hi_min': 60.0},
                        {'name': 'mid', 'lo_min': 60.0, 'hi_min': 150.0},
                        {'name': 'deep', 'lo_min': 150.0, 'hi_min': None}]
    _lad['ladder_by_exposure'] = {
        'thin': [{'bin': '<0.01', 'n': 2319, 'rate': 0.141},
                 {'bin': '0.01-0.25', 'n': 0, 'rate': 0.0},
                 {'bin': '0.25-0.5', 'n': 863, 'rate': 0.169},
                 {'bin': '0.5-1', 'n': 685, 'rate': 0.222},
                 {'bin': '>=1', 'n': 323, 'rate': 0.235}],
        'mid': [{'bin': '<0.01', 'n': 1638, 'rate': 0.108},
                {'bin': '0.01-0.25', 'n': 1381, 'rate': 0.154},
                {'bin': '0.25-0.5', 'n': 960, 'rate': 0.176},
                {'bin': '0.5-1', 'n': 517, 'rate': 0.251},
                {'bin': '>=1', 'n': 39, 'rate': 0.308}],
        'deep': [{'bin': '<0.01', 'n': 265, 'rate': 0.087},
                 {'bin': '0.01-0.25', 'n': 864, 'rate': 0.167},
                 {'bin': '0.25-0.5', 'n': 642, 'rate': 0.217},
                 {'bin': '0.5-1', 'n': 58, 'rate': 0.276},
                 {'bin': '>=1', 'n': 0, 'rate': 0.0}]}
    _c = chin_line('Glass Joe', _ct, _lad)
    chk(_c and '1.40/15min' in _c and '>=1' in _c and '24%' in _c
        and '3 KO loss' in _c,
        f"a glass chin prints its rate, its measured bin AND its KO losses ({_c})")
    _c = chin_line('Granite Sam', _ct, _lad)
    chk(_c and '<0.01' in _c and "never KO'd in 9 fights" in _c,
        f"and a granite one prints the bottom bin ({_c})")

    # ---- EXPOSURE. 'Never dropped' is not one fact. THE KAUE CASE: 38
    # minutes of tape reads 14.1%, not the pooled 12.5%, and a 240-minute
    # career of the same reads 8.7%. Same rate, different evidence.
    _ct['Rookie Clean'] = {'kdabs': 0.0, 'kd': 0.0, 'kolost': 0.0, 'n': 4,
                           'mins': 38.0, 'kd_abs_raw': 0, 'ko_losses': 0}
    _ct['Iron Veteran'] = {'kdabs': 0.0, 'kd': 0.0, 'kolost': 0.0, 'n': 18,
                           'mins': 240.0, 'kd_abs_raw': 0, 'ko_losses': 0}
    _a = chin_line('Rookie Clean', _ct, _lad)
    _b = chin_line('Iron Veteran', _ct, _lad)
    chk('14%' in _a and '@thin' in _a, f"38 minutes of clean tape is 14%, not 12.5% ({_a})")
    chk('9%' in _b and '@deep' in _b, f"240 minutes of it is 9% ({_b})")
    chk(_a.split('(')[0].strip() == _b.split('(')[0].strip()
        and '14%' in _a and '9%' in _b,
        "the two print the SAME rate (0.00/15min) and DIFFERENT risk (14 vs 9) "
        "-- which is the whole point of conditioning on exposure")
    # An empty stratum bin is no evidence and must fall back, never print 0%.
    _e = _chin_bin(0.10, _lad, 20.0)
    chk(_e and _e['n'] == 2245 and _e.get('stratum') is None,
        f"a rate no thin fighter can post falls back to pooled, not to 0% ({_e})")
    # THE CASE THE NAIVE PROXY CANNOT SEE, and the reason both print.
    _c = chin_line('Dropped Never Out', _ct, _lad)
    chk(_c and '0.5-1' in _c and '25%' in _c and "never KO'd" in _c,
        f"a fighter dropped six times and never finished reads BULLETPROOF on "
        f"the naive proxy and 25% on the measured one -- both said ({_c})")
    chk(chin_line('Nobody', _ct, _lad) is None,
        "a fighter with no bout rows prints nothing, never a zero")
    chk('bin' not in (chin_line('Glass Joe', _ct, None) or 'bin'),
        "with no measured ladder the rate still prints, the bin does not")
    chk(_chin_bin(0.30, _lad)['bin'] == '0.25-0.5'
        and _chin_bin(0.0, _lad)['bin'] == '<0.01'
        and _chin_bin(99.0, _lad)['bin'] == '>=1',
        "bin lookup lands on the right rung at both ends and in the middle")

    # ---- STRIKING. defhist refused the rate everybody quotes and shipped
    # two nobody does, so the line must carry the refusal in words.
    _sk = {'Volume Guy': {'absorb': 5.2, 'output': 6.0, 'stracc': 0.38,
                          'strdef': 0.62, 'tddef': 0.70, 'n': 12, 'mins': 150.0},
           'Ghost': {'absorb': 2.1, 'output': 4.0, 'stracc': 0.52,
                     'strdef': 0.62, 'tddef': 0.40, 'n': 12, 'mins': 150.0}}
    _mod = {'shipped_model': {'keys': ['winpct', 'stracc', 'absorb'],
                              'intercept': 0.0,
                              'coef': {'d_winpct': 0.216, 'd_stracc': 0.035,
                                       'd_absorb': -0.146},
                              'mean': {'d_winpct': 0.0, 'd_stracc': 0.0,
                                       'd_absorb': 0.0},
                              'sd': {'d_winpct': 0.3, 'd_stracc': 0.1064,
                                     'd_absorb': 1.281}}}
    _l = strike_line('Volume Guy', 'Ghost', _sk)
    chk(_l and 'absorbed/min 5.2 vs 2.1' in _l and '+3.1' in _l,
        f"the feature that measured STRONGEST prints first, with its "
        f"differential ({_l})")
    chk('accuracy 38% vs 52% (-14)' in _l,
        "and striking accuracy, the other one that cleared the bar")
    chk('TD-def 70% vs 40% (not priced, p=0.095)' in _l,
        "takedown defence prints WITH the reason it is not priced -- a clean "
        "monotone ladder that one of 20 shuffles still beat")
    chk('62%' not in _l,
        "striking DEFENCE %, identical for both men here, is not printed at "
        "all: measured gain NEGATIVE out of sample, ladder non-monotone")
    chk(strike_line('Volume Guy', 'Nobody', _sk) is None,
        "one missing corner prints nothing -- a differential needs both sides")

    # ---- THE EXCHANGE RATE. A differential is not a finding until it has
    # a size, and the two shipped rates have wildly different ones.
    _p = strike_points('Volume Guy', 'Ghost', _sk, _mod)
    chk(_p is not None and _p < -6,
        f"absorbing 3.1 more per minute costs real points, not a shrug ({_p:+.1f})")
    _p2 = strike_points('Ghost', 'Volume Guy', _sk, _mod)
    chk(abs(_p + _p2) < 1e-9,
        "and the read is ANTISYMMETRIC -- flipping the corners flips the sign "
        "exactly, which a differential model owes you")
    _sk2 = {'A': dict(_sk['Ghost'], stracc=0.60), 'B': dict(_sk['Ghost'])}
    _pa = strike_points('A', 'B', _sk2, _mod)
    chk(_pa is not None and abs(_pa) < 1.0,
        f"8 points of striking accuracy is worth under a point of win "
        f"probability -- significant is not the same as big ({_pa:+.2f})")
    chk(strike_points('Volume Guy', 'Ghost', _sk, None) is None,
        "with no measured model the points are None, never a zero -- "
        "'unmeasured' and 'no effect' are different answers")
    _ln = strike_line('Volume Guy', 'Ghost', _sk, _mod)
    chk('worth' in _ln and 'clamp 5' in _ln,
        "and the printed line carries the size AND the rule-23 clamp")
    _thin = {'A': {'absorb': 3.0, 'output': 3.0, 'stracc': None, 'strdef': None,
                   'tddef': None, 'n': 4, 'mins': 40.0},
             'B': {'absorb': 4.0, 'output': 3.0, 'stracc': None, 'strdef': None,
                   'tddef': None, 'n': 4, 'mins': 40.0}}
    _l2 = strike_line('A', 'B', _thin)
    chk(_l2 and 'absorbed/min' in _l2 and 'accuracy' not in _l2,
        f"under the attempt floor the rate is ABSENT, never a number nobody "
        f"measured ({_l2})")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

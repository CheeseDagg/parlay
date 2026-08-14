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
            'ridx': bt.get('ridx') or {}}


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


def main():
    hist = json.load(open(os.path.join(HERE, 'ufchist.json')))
    print("fetching Greco results...", flush=True)
    ev = ufcform.parse_events(ufcform.get(f"{ufcform.RAW}/ufc_event_details.csv"))
    greco = ufcform.parse_bouts(ufcform.get(f"{ufcform.RAW}/ufc_fight_results.csv"), ev)
    bouts = load_card()
    _ages, _ridx = ages('2026-08-15'), ratings_idx()
    for _b in bouts:
        _b['ages'] = _ages
        _b['ridx'] = _ridx
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

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

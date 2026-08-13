"""fights.py — method-of-victory pricing that cannot repeat 8/11.

That night I overrode de-vigged fight prices by 10+ points four times, off
career tallies read from search snippets, and went 1-for-4. The market's
number beat mine on Kunneman, on the Hasan round-1 fade, and on the
Escarrega decision fade. This module is the mechanical form of the rules
written from that (RULES.md 23 and 27):

  * If a METHOD MARKET EXISTS, its de-vigged price IS the probability.
    from_quote() is the only sanctioned reading of it.
  * If no market exists, the fallback is the divisional base rate SHRUNK
    toward the fighter's career split — never the raw career tally. A 6-KO
    -in-8 record at flyweight is eight fights of signal, not a 75% truth.
  * Any hand override of a market number passes through clamp(), which caps
    it at five points. The 8/11 tally says my overrides past five points
    carry no information.

Self-contained on purpose: board.py's power de-vig is for the two-way board;
method props arrive as single quoted prices from the app, usually with no
opposing side to pair against.
"""
import sys

def dec(am):
    am = float(am)
    return 1 + (am / 100.0 if am > 0 else 100.0 / -am)

def from_quote(am, overround=0.02):
    """A single-sided method quote -> probability. The 2% haircut is the
    typical one-sided share of a method market's overround; without the
    opposing prices there is nothing better to anchor to, and pretending the
    raw implied is clean flatters every leg."""
    return (1.0 / dec(am)) / (1 + overround)

def clamp(market_p, my_p, cap=0.05):
    """RULES.md #23. Research adjusts a de-vigged price by five points at
    most. Beyond that, the 8/11 ledger says the market was right and I was
    loud."""
    lo, hi = market_p - cap, market_p + cap
    return max(lo, min(hi, my_p))

# Method-of-victory split OF WINS (ko, sub, dec) by division. Coarse UFC-era
# base rates: finish likelihood rises with weight, decisions dominate the
# small divisions. These are PRIORS for when no market exists — nothing here
# outranks a posted price.
PRIOR = {
    'HW':  (0.58, 0.12, 0.30),
    'LHW': (0.50, 0.14, 0.36),
    'MW':  (0.42, 0.16, 0.42),
    'WW':  (0.34, 0.17, 0.49),
    'LW':  (0.29, 0.18, 0.53),
    'FW':  (0.27, 0.17, 0.56),
    'BW':  (0.24, 0.18, 0.58),
    'FLW': (0.21, 0.19, 0.60),
    'W':   (0.14, 0.16, 0.70),   # women's rows pooled: decisions dominate
}

def method_split(division, career=None):
    """(p_ko, p_sub, p_dec) GIVEN a win. career=(ko, sub, dec) counts.

    Shrinkage weight n/(n+8): a debutant is all prior, eight fights is an
    even blend, twenty fights mostly speaks for itself. Eight is one career
    of the kind that reaches a Contender Series card — exactly the sample
    size that fooled me on 8/11, which is why it only ever gets half a vote.
    """
    pk, ps, pd = PRIOR[division]
    if not career or sum(career) == 0:
        return (pk, ps, pd)
    n = sum(career)
    w = n / (n + 8.0)
    ck, cs, cd = (c / n for c in career)
    out = (w * ck + (1 - w) * pk,
           w * cs + (1 - w) * ps,
           w * cd + (1 - w) * pd)
    s = sum(out)
    return tuple(x / s for x in out)

def p_method(win_p, division, career=None):
    """{'ko','sub','dec'} -> outright probability of winner-by-that-method,
    for when NO method market is posted. win_p is the de-vigged moneyline."""
    k, s, d = method_split(division, career)
    return {'ko': win_p * k, 'sub': win_p * s, 'dec': win_p * d}


def am_from_p(p):
    """Probability -> fair American odds, so a modelled method can be compared
    against the -350 floor in the units the app actually prints."""
    if p <= 0 or p >= 1:
        return None
    d = 1.0 / p
    return round(-100 / (d - 1)) if d < 2 else round(100 * (d - 1))

# ---- UFC 330 -- Sat 8/15/2026, Xfinity Mobile Arena, Philadelphia.
# Main card 8:00pm CT, main event ~10:30pm CT.
#
# career is WINS ONLY as (ko, sub, dec) and EVERY entry is sourced. A fighter
# whose breakdown could not be verified carries career=None and prices off the
# divisional prior alone -- which is the honest fallback and is visibly worse,
# rather than a number invented to fill the column (rule 37).
#
# Only four legs on this card clear the -350 floor, so those are the only ones
# the model needs to be right about. `price` is the board's FanDuel number.
CARD = {
    'Islam Makhachev': dict(
        div='WW', career=(5, 13, 10), price=-360, opp='Ian Machado Garry',
        note="28-1, WW title defence. Career splits were built at LIGHTWEIGHT; "
             "he has one welterweight fight (dec over Della Maddalena, UFC 322) "
             "and is priced here against the WW prior. Unbeaten since 2016, "
             "16-fight UFC win streak. Garry 17-1."),
    'Myktybek Orolbai': dict(
        div='WW', career=(7, 6, 3), price=-900, opp='Jeremiah Wells',
        note="16-2-1, three-fight win streak, 81% of wins end early."),
    'Mansur Abdul-Malik': dict(
        div='MW', career=(7, 2, 0), price=-650, opp='Dustin Stoltzfus',
        note="9-1-1. ZERO decisions in nine wins -- the shrinkage pulls his "
             "decision share back to ~20%, which is the whole point of the "
             "prior: 0-for-9 is not a 0% truth. Coming off the first loss of "
             "his career, a KO by Belgaroui in March."),
    'Esteban Ribovics': dict(
        div='LW', career=None, price=-590, opp='Edson Barboza',
        note="Win breakdown NOT VERIFIED -- prices off the bare LW prior. "
             "Board says -590; FanDuel was reported at -430 in fight-week "
             "previews, so CHECK THE APP before this leg counts as -350+. "
             "Barboza is 40 and has lost three straight; Ribovics was "
             "submitted by Gamrot last out but Barboza is a striker."),
}

def card_lines(card=None, floor=-350):
    """The model's read on every carded fighter, with rule 27's verdict.

    Prints each method's modelled probability and the fair price it implies,
    then says whether ANY single method clears the floor. It almost never
    does -- which is rule 27 stated in numbers rather than in prose."""
    card = card or CARD
    out = []
    for name, d in card.items():
        wp = from_quote(d['price'])
        pm = p_method(wp, d['div'], d['career'])
        best = max(pm.items(), key=lambda kv: kv[1])
        clears = [k for k, v in pm.items()
                  if am_from_p(v) is not None and am_from_p(v) <= floor]
        out.append(dict(name=name, opp=d['opp'], price=d['price'], win_p=wp,
                        method=pm, best=best, clears=clears,
                        sourced=d['career'] is not None, note=d['note']))
    return out

def print_card():
    print(f"\n  UFC 330 — Sat 8/15, Philadelphia. Floor -350; "
          f"legs below it are unbettable (rule 2).\n")
    for r in card_lines():
        src = "" if r['sourced'] else "   [career UNVERIFIED — prior only]"
        print(f"  {r['name']}  ({r['price']:+d}, {r['win_p']*100:.1f}%) "
              f"vs {r['opp']}{src}")
        for k in ('ko', 'sub', 'dec'):
            v = r['method'][k]
            print(f"      by {k:4} {v*100:5.1f}%   fair {am_from_p(v):+6d}")
        if r['clears']:
            print(f"      -> {', '.join(r['clears'])} clears the floor")
        else:
            print(f"      -> NO single method reaches -350. "
                  f"Rule 27: take the ML.")
        print(f"      {r['note']}\n")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, msg):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    p = from_quote(-425)
    chk(abs(p - 0.7937) < 0.001,
        f"the 8/11 Hasan-by-KO quote (-425) reads {p:.4f} -- the market's "
        "number, which was RIGHT (KO round 1)")
    chk(abs(from_quote(150) - 0.3922) < 0.001,
        "a plus quote de-vigs through the same single haircut")

    chk(abs(clamp(0.70, 0.50) - 0.65) < 1e-9 and abs(clamp(0.70, 0.90) - 0.75) < 1e-9,
        "a ten-plus-point override is held to five, both directions")
    chk(clamp(0.70, 0.72) == 0.72, "inside the cap, the estimate stands")

    chk(PRIOR['HW'][0] > PRIOR['MW'][0] > PRIOR['LW'][0] > PRIOR['FLW'][0],
        "KO share falls with weight class, monotone through the divisions")
    chk(all(abs(sum(v) - 1) < 1e-9 for v in PRIOR.values()),
        "every divisional split sums to 1")

    chk(method_split('FLW', (0, 0, 0)) == PRIOR['FLW'],
        "a debutant is all prior")
    k8 = method_split('FLW', (6, 1, 1))[0]
    chk(abs(k8 - 0.5 * (0.75 + 0.21)) < 1e-9,
        f"Hasan's actual 8-fight career (6 KO) blends to {k8:.2f} KO-given-win "
        "-- NOT the 0.75 raw tally I treated as truth, and NOT the 0.60 I "
        "flip-flopped to. Eight fights, half a vote.")
    k30 = method_split('FLW', (22, 4, 4))[0]
    chk(k30 > k8, "a thirty-fight career outranks the prior more than an "
                  "eight-fight one")

    pm = p_method(0.966, 'HW', (4, 1, 1))
    chk(abs(sum(pm.values()) - 0.966) < 1e-9,
        "method probabilities partition the win probability exactly")

    # ---- UFC 330. The card the model has to be current for.
    chk(abs(am_from_p(0.7778) - -350) <= 1,
        "am_from_p inverts the floor: 77.8% is -350")
    chk(am_from_p(0.5) == 100 and am_from_p(0.8) == -400,
        "and round-trips an even-money and a heavy price")

    rows = {r['name']: r for r in card_lines()}
    chk(len(rows) == 4,
        "every carded fighter that clears the -350 floor is modelled")
    chk(all(not r['clears'] for r in rows.values()),
        "NOT ONE single method on this card reaches -350 -- rule 27 in "
        "numbers: on a card this chalky the ML is the only bettable shape")

    mam = rows['Mansur Abdul-Malik']['method']
    chk(mam['dec'] > 0.15 * rows['Mansur Abdul-Malik']['win_p'],
        f"Abdul-Malik is 0-for-9 by decision and the model still gives him "
        f"{mam['dec']*100:.0f}% -- a zero tally is not a zero probability, "
        "which is the exact error that priced Escarrega's decision at nil")
    chk(rows['Mansur Abdul-Malik']['best'][0] == 'ko',
        "his 7-of-9 KO record still dominates the split, just not 78% of it")

    im = rows['Islam Makhachev']['method']
    chk(im['sub'] > im['ko'],
        "Makhachev's modelled path is the submission (13 of 28 wins), not the "
        "KO -- a fighter's own record outranks 'welterweights knock people out'")
    chk(not rows['Esteban Ribovics']['sourced'],
        "Ribovics carries no career split and is flagged, not filled in")
    chk(pm['ko'] < 0.667,
        f"Wint-by-KO off his real record prices {pm['ko']:.2f} -- the -200 "
        "round-1-KO leg (66.7% implied) was unbettable even BEFORE the "
        "round restriction")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


def form_notes():
    """Append ufcform (last five, wins-by/loses-by) and ufchist division
    rates to the card view. Both files are built on the Actions runner from
    the full UFC record; absent files say so rather than vanishing -- a card
    note that silently covers half the card reads as complete."""
    import json, os
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, 'ufcform.json')) as fh:
            uf = json.load(fh).get('teams', {})
    except Exception:
        print('  (ufcform.json unreadable -- no recent-fight table; touch '
              'experiments/UFCFORM.txt)')
        return
    print('\nRECENT FIGHTS (full record, newest first) --- how they win / lose')
    for fav, d in CARD.items():
        for name in (fav, d.get('opp')):
            if not name:
                continue
            row = uf.get(name)
            if not row:
                print(f'  {name:<24} no UFC record on file (debut or unmatched)')
                continue
            pr = row['profile']
            l5 = ' '.join(('W' if f['win'] else 'L') + '-' + f['method']
                          for f in row['last5'])
            wb = pr.get('win_by') or {}
            lb = pr.get('lose_by') or {}
            wtxt = (f"wins dec {wb.get('dec',0)*100:.0f}/ko {wb.get('ko',0)*100:.0f}"
                    f"/sub {wb.get('sub',0)*100:.0f}") if wb else 'no wins'
            ltxt = (f"loses dec {lb.get('dec',0)*100:.0f}/ko {lb.get('ko',0)*100:.0f}"
                    f"/sub {lb.get('sub',0)*100:.0f}") if lb else 'NEVER LOST'
            print(f'  {name:<24} {pr["record"]:<13} {l5:<22} {wtxt}; {ltxt}')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    rc = print_card()
    form_notes()
    sys.exit(rc)

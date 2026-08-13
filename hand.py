#!/usr/bin/env python3
"""hand.py — turn pasted FanDuel prices into de-vigged, gate-ready legs.

    python3 hand.py "Besiktas -6000 / Hradec Kralove +1600 to advance"
    python3 hand.py "Tromso -165 / draw +290 / CFR Cluj +430"
    python3 hand.py "Hearts v Benfica U6.5 -400 / O6.5 +320"
    python3 hand.py --file=hand.txt
    python3 hand.py --selftest

On 2026-08-13 FanDuel priced roughly forty UEFA qualifiers the feed is
structurally blind to (no catalog key exists). Ryan sent screenshots at 11:36
and the prices were hand-typed into a scratch dict, de-vigged ad hoc, and
priced into windows -- three hours after "make me a soccer parlay" and twenty
minutes before kickoff. This file is that scramble, done once, tested, and
kept.

One pasted line per market, three shapes:

  TWO-WAY    "A -6000 / B +1600 to advance"     -> mult de-vig (measured:
             1817 MLB games; also the shape of a to-advance market, which
             settles the aggregate and carries no draw)
  THREE-WAY  "A -165 / draw +290 / B +430"      -> power de-vig (measured:
             52710 matches), emitted as the favourite's Double Chance with
             the 0.80-of-fair-excess payout, tagged (derived)
  TOTAL      "A v B U6.5 -400 / O6.5 +320"      -> mult de-vig of the pair

REFUSALS ARE THE CONTRACT. A one-sided price cannot be de-vigged and is
refused, never guessed at. A vig sum outside the sane band is refused --
that is a typo'd paste, and a typo priced into a ticket is the worst output
this tool could produce. Every leg it does emit is (app-quoted): the DERIVED
gate still names synthesized DC payouts for confirmation, and nothing here
enters the board's feed files -- it writes handlegs.json for the solver of
the moment and prints the human table.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, 'handlegs.json')

VIG2 = (1.005, 1.14)          # sane two-way overround band
VIG3 = (1.02, 1.20)
DC_FACTOR = 0.80              # of fair excess -- calibrated on two real quotes


def dec(am):
    return 1 + (am / 100 if am > 0 else 100 / -am)


def am_str(p):
    return f"{p:+d}"


def _price(tok):
    m = re.fullmatch(r'[+-]\d{3,5}', tok.strip())
    return int(tok) if m else None


def parse_line(line):
    """One pasted market -> dict, or (None, why). Shapes documented above."""
    raw = line.strip()
    if not raw or raw.startswith('#'):
        return None, 'blank'
    is_adv = bool(re.search(r'to advance', raw, re.I))
    body = re.sub(r'to advance', '', raw, flags=re.I).strip()
    parts = [p.strip() for p in body.split('/')]

    tot = re.search(r'\b[UO](\d+(?:\.5)?)\b', body, re.I)
    if tot and len(parts) == 2:
        m1 = re.search(r'\bU(\d+(?:\.5)?)\s+([+-]\d+)', body, re.I)
        m2 = re.search(r'\bO(\d+(?:\.5)?)\s+([+-]\d+)', body, re.I)
        if not (m1 and m2):
            return None, 'total needs BOTH sides (U and O) -- one-sided cannot de-vig'
        if m1.group(1) != m2.group(1):
            return None, f'U{m1.group(1)} against O{m2.group(1)} is two different markets'
        mt = re.match(r'(.+?)\s+[UO]\d', parts[0], re.I)
        name = mt.group(1).strip() if mt else 'match'
        return {'kind': 'total', 'match': name, 'pt': float(m1.group(1)),
                'under': int(m1.group(2)), 'over': int(m2.group(2))}, None

    sides = []
    for p in parts:
        m = re.match(r'(.+?)\s+([+-]\d{3,5})$', p)
        if not m:
            return None, f'cannot read a name+price from {p!r}'
        sides.append((m.group(1).strip(), int(m.group(2))))
    if len(sides) == 2:
        return {'kind': 'adv' if is_adv else 'two', 'sides': sides}, None
    if len(sides) == 3:
        draw = [i for i, (n, _) in enumerate(sides) if n.lower() == 'draw']
        if len(draw) != 1:
            return None, 'three prices need exactly one named draw'
        return {'kind': 'three', 'sides': sides, 'draw_i': draw[0]}, None
    return None, f'{len(sides)} prices -- markets here are 2-way or 3-way'


def devig(mkt):
    """market dict -> legs [{lab, p, price, d, note}], or (None, why).
    Vig-band refusal lives HERE so no caller can skip it."""
    import board
    if mkt['kind'] in ('adv', 'two'):
        (na, pa), (nb, pb) = mkt['sides']
        s = 1 / dec(pa) + 1 / dec(pb)
        if not (VIG2[0] <= s <= VIG2[1]):
            return None, f'two-way vig sum {s:.3f} outside {VIG2} -- typo?'
        tag = ' to advance' if mkt['kind'] == 'adv' else ''
        return [{'lab': f'{na}{tag} (app-quoted)', 'p': board.devig(pa, pb),
                 'price': pa, 'd': dec(pa),
                 'note': 'aggregate, no draw' if mkt['kind'] == 'adv' else '2-way'},
                {'lab': f'{nb}{tag} (app-quoted)', 'p': board.devig(pb, pa),
                 'price': pb, 'd': dec(pb), 'note': ''}], None
    if mkt['kind'] == 'three':
        s = sum(1 / dec(p) for _, p in mkt['sides'])
        if not (VIG3[0] <= s <= VIG3[1]):
            return None, f'three-way vig sum {s:.3f} outside {VIG3} -- typo?'
        di = mkt['draw_i']
        outs = [(n, p) for i, (n, p) in enumerate(mkt['sides']) if i != di]
        fav = min(outs, key=lambda x: dec(x[1]))
        dog = max(outs, key=lambda x: dec(x[1]))
        p_dc = 1 - __import__('board').devig_n(dog[1], [fav[1], mkt['sides'][di][1]])
        d_dc = 1 + DC_FACTOR * (1 / p_dc - 1)
        am = round((d_dc - 1) * 100) if d_dc >= 2 else -round(100 / (d_dc - 1))
        return [{'lab': f'{fav[0]} DC (derived) (app-quoted)', 'p': p_dc,
                 'price': am, 'd': d_dc,
                 'note': f'90-min market -- BLIND to any first leg (rule 40)'}], None
    if mkt['kind'] == 'total':
        s = 1 / dec(mkt['under']) + 1 / dec(mkt['over'])
        if not (VIG2[0] <= s <= VIG2[1]):
            return None, f'total vig sum {s:.3f} outside {VIG2} -- typo?'
        import board
        return [{'lab': f"{mkt['match']} U{mkt['pt']} (app-quoted)",
                 'p': board.devig(mkt['under'], mkt['over']),
                 'price': mkt['under'], 'd': dec(mkt['under']), 'note': '2-way'}], None
    return None, f"unknown kind {mkt['kind']}"


def run(lines):
    legs, refused = [], []
    for ln in lines:
        mkt, why = parse_line(ln)
        if mkt is None:
            if why != 'blank':
                refused.append((ln.strip(), why))
            continue
        out, why = devig(mkt)
        if out is None:
            refused.append((ln.strip(), why))
        else:
            legs.extend(out)
    return legs, refused


def main():
    fl = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--file=')), None)
    lines = (open(fl).read().splitlines() if fl
             else [a for a in sys.argv[1:] if not a.startswith('--')])
    if not lines:
        print(__doc__.strip().splitlines()[2]); return 2
    legs, refused = run(lines)
    for o in legs:
        print(f"  {o['p']*100:5.1f}%  {am_str(o['price']):>7}  {o['lab']}"
              + (f"   [{o['note']}]" if o['note'] else ''))
    for ln, why in refused:
        print(f"  REFUSED: {ln!r} -- {why}")
    with open(OUT, 'w') as fh:
        json.dump({'legs': legs, 'refused': [list(r) for r in refused]}, fh, indent=1)
    print(f"\n  {len(legs)} legs, {len(refused)} refused. wrote {OUT}")
    return 0 if legs or not refused else 1


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    # fixtures are the 8/13 screenshots, so the tool is pinned to the day
    legs, ref = run(["Besiktas -6000 / Hradec Kralove +1600 to advance"])
    chk(not ref and abs(legs[0]['p'] - 0.944) < 0.003,
        "Besiktas -6000/+1600 de-vigs to 94.4% under MULT -- the measured "
        "method for a lopsided two-way. The 97.8% quoted on 8/13 was the "
        "pre-calibration power number: every to-advance leg that day was "
        "overstated about three points, and this fixture keeps the receipt")
    chk('to advance' in legs[0]['lab'] and 'aggregate' in legs[0]['note'],
        "a to-advance leg says it settles the aggregate and carries no draw")

    legs, ref = run(["Tromso -165 / draw +290 / CFR Cluj +430"])
    chk(not ref and len(legs) == 1 and 'Tromso DC' in legs[0]['lab'],
        "a 3-way collapses to the favourite's DC, never a raw side (rule 8)")
    chk(abs(legs[0]['p'] - 0.833) < 0.006,
        f"Tromso DC prices {legs[0]['p']*100:.1f}% under power -- the measured "
        "method for thin 3-ways, same as the board")
    chk('rule 40' in legs[0]['note'],
        "and the leg itself says a 90-minute market is blind to the first leg")

    legs, ref = run(["Hearts v Benfica U6.5 -400 / O6.5 +320"])
    chk(not ref and legs[0]['p'] > 0.75 and 'U6.5' in legs[0]['lab'],
        "a pasted total needs both sides and lands as the under")

    _, ref = run(["Rangers -144"])
    chk(ref and 'de-vig' not in ref[0][1] or ref,
        "a single price is refused -- one side cannot be de-vigged")
    _, ref = run(["A -6000 / B -6000"])
    chk(ref and 'vig sum' in ref[0][1],
        "two heavy favourites in one market is a typo'd paste, refused loudly")
    _, ref = run(["A -200 / B +170 / C +900"])
    chk(ref and 'draw' in ref[0][1],
        "three prices with no named draw refuse rather than guess which is which")
    _, ref = run(["X v Y U6.5 -400 / O5.5 +320"])
    chk(ref and 'different markets' in ref[0][1],
        "U6.5 against O5.5 is two ladders, not a pair")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

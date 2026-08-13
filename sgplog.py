#!/usr/bin/env python3
"""sgplog.py — collect FanDuel's SGP quotes against the naive product.

    python3 sgplog.py quote +116 "Union DC" -835 "U6.5 PU-SL" -4000
    python3 sgplog.py quote -450 "NYC DC" -500 "U6.5 Necaxa" -5000 --note="8/13 slip"
    python3 sgplog.py report
    python3 sgplog.py --selftest

FanDuel reprices correlated legs inside an SGP, and the one measured case so
far (8/13: DC + same-match under) came out 4% ABOVE the naive product -- the
book PAYING for the correlation instead of charging. One case is an
anecdote. This file turns every screenshot Ryan sends into a row: the legs,
their board prices, the naive product, the book's actual quote, and the
haircut (actual / naive, in decimal-excess terms).

After twenty-plus rows the report fits a haircut per pairing shape (DC+under,
ML+under, method+method...), and slips.py can stop assuming independence on
exactly the pairs the book does not price independently. Until then the
report prints n and refuses to average three anecdotes into a constant --
the DC payout factor earned its 0.80 from two real quotes and says so; this
earns its numbers the same way or not at all.
"""
import csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, 'sgplog.csv')
FIELDS = ['date', 'quote_am', 'legs', 'prices', 'naive_dec', 'quote_dec',
          'ratio_excess', 'shape', 'note']
MIN_FIT = 20


def dec(am):
    am = int(am)
    return 1 + (am / 100 if am > 0 else 100 / -am)


def shape_of(labels):
    """Coarse pairing shape, from the labels alone. 'other' is honest."""
    l = ' | '.join(x.lower() for x in labels)
    has = lambda *w: any(x in l for x in w)
    if has(' dc', 'double chance', 'and draw') and has('under', 'u'):
        return 'dc+under'
    if has('under') and not has(' dc', 'draw'):
        return 'unders'
    if has(' dc', 'and draw'):
        return 'dc+dc'
    if has('by ', 'ko', 'sub', 'decision', 'points'):
        return 'method-mix'
    return 'other'


def parse_quote(argv):
    """(quote_am, [(label, price_am)...], note) from the CLI shape."""
    args = [a for a in argv if not a.startswith('--')]
    note = next((a.split('=', 1)[1] for a in argv if a.startswith('--note=')), '')
    if len(args) < 3 or (len(args) - 1) % 2 != 0:
        return None, None, 'want: quote AM then label/price pairs'
    try:
        q = int(args[0])
    except ValueError:
        return None, None, f'quote {args[0]!r} is not an American price'
    pairs = []
    for lab, pr in zip(args[1::2], args[2::2]):
        try:
            pairs.append((lab, int(pr)))
        except ValueError:
            return None, None, f'price {pr!r} on {lab!r} is not American'
    return q, pairs, note


def row_from(q, pairs, note, date):
    naive = 1.0
    for _, pr in pairs:
        naive *= dec(pr)
    qd = dec(q)
    # excess ratio: how much of the naive PROFIT the quote keeps. 1.0 = priced
    # independent; >1 = the book PAYS for the correlation; <1 = it charges.
    ratio = (qd - 1) / (naive - 1) if naive > 1 else None
    return {'date': date, 'quote_am': q,
            'legs': ' | '.join(l for l, _ in pairs),
            'prices': ' | '.join(str(p) for _, p in pairs),
            'naive_dec': round(naive, 4), 'quote_dec': round(qd, 4),
            'ratio_excess': round(ratio, 4) if ratio else '',
            'shape': shape_of([l for l, _ in pairs]), 'note': note}


def report(rows):
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        if r.get('ratio_excess'):
            by[r['shape']].append(float(r['ratio_excess']))
    out = []
    for shp, v in sorted(by.items()):
        line = f"  {shp:<12} n={len(v):<3} mean ratio {sum(v)/len(v):.3f}"
        if len(v) < MIN_FIT:
            line += f"   NOT A CONSTANT YET -- {MIN_FIT - len(v)} more quotes before this number gets used"
        out.append(line)
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'quote':
        import datetime
        q, pairs, note = parse_quote(sys.argv[2:])
        if q is None:
            print(f"  refused: {note}"); return 1
        r = row_from(q, pairs, note, datetime.date.today().isoformat())
        new = not os.path.exists(LOG)
        with open(LOG, 'a', newline='') as fh:
            w = csv.DictWriter(fh, FIELDS)
            if new:
                w.writeheader()
            w.writerow(r)
        print(f"  logged: naive {r['naive_dec']} vs quoted {r['quote_dec']} "
              f"-> excess ratio {r['ratio_excess']} [{r['shape']}]")
        return 0
    rows = list(csv.DictReader(open(LOG))) if os.path.exists(LOG) else []
    print(f"{len(rows)} SGP quotes logged")
    for line in report(rows):
        print(line)
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    q, pairs, note = parse_quote(['+116', 'Union DC', '-835', 'U6.5', '-4000',
                                  '--note=slip'])
    chk(q == 116 and len(pairs) == 2 and note == 'slip',
        "the CLI shape parses: quote, then label/price pairs, note optional")
    _, _, why = parse_quote(['+116', 'Union DC'])
    chk('pairs' in why, "an odd argument list is refused, not guessed at")

    r = row_from(-104, [('a DC', -835), ('b U6.5', -4000)], '', '2026-08-13')
    naive = dec(-835) * dec(-4000)
    chk(abs(r['naive_dec'] - round(naive, 4)) < 1e-9,
        "the naive product multiplies the board prices")
    chk(abs(float(r['ratio_excess'])
            - (dec(-104) - 1) / (naive - 1)) < 1e-3,
        "the ratio is excess-over-excess -- the 8/13 case reads ~1.04, the "
        "book paying 4% ABOVE independent for DC+under")
    chk(r['shape'] == 'dc+under', "the pairing shape is read from the labels")

    rows = [{'shape': 'dc+under', 'ratio_excess': '1.04'}] * 3
    rep = report(rows)
    chk(any('NOT A CONSTANT YET' in l for l in rep),
        "three anecdotes refuse to become a constant -- the report says how "
        "many more quotes it needs before anything downstream may use it")
    rows20 = [{'shape': 'dc+under', 'ratio_excess': '1.04'}] * 20
    chk(not any('NOT A CONSTANT' in l for l in report(rows20)),
        "at twenty the caveat lifts")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

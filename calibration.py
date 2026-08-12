#!/usr/bin/env python3
"""calibration.py — score calibration.csv: me against the de-vigged market.

    python3 calibration.py            # the running scoreboard
    python3 calibration.py --selftest

Brier score = mean (p - outcome)^2, lower is better; a coin flip scores 0.25.
The column that matters is the DIFFERENCE: if my Brier is not beating the
market's after a real sample, rule 23's five-point clamp is not a leash, it
is a mercy, and the overrides should go to zero. Rules 23/27 were written
off this file's first eight rows (big overrides: 1-for-4). The file only
means anything if every quoted number keeps landing in it -- at placement,
scored at settle (rule 29).
"""
import csv, sys

def score(rows):
    """rows: [(market_p, my_p, won_bool)] -> dict of the numbers that matter."""
    n = len(rows)
    if not n:
        return {'n': 0}
    bm = sum((m - w) ** 2 for m, _, w in rows) / n
    by = sum((y - w) ** 2 for _, y, w in rows) / n
    big = [(m, y, w) for m, y, w in rows if abs(y - m) > 0.05]
    return {
        'n': n,
        'brier_market': bm,
        'brier_mine': by,
        'edge': bm - by,                       # positive = my numbers helping
        'overrides': len(big),
        'override_record': (sum(1 for m, y, w in big if (y > m) == bool(w)),
                            len(big)),         # "I moved it the right way"
    }

SETTLED = {'won': True, 'win': True, 'w': True,
           'lost': False, 'loss': False, 'l': False}

def load(path='calibration.csv', with_pending=False):
    """Settled rows only. A blank outcome is PENDING, not a loss.

    This read `outcome == 'won'` and called everything else False, so a row
    logged at placement -- which rule 31 requires, hours or days before it can
    settle -- scored as a loss the moment it was written. Logging the 18-leg
    slip on 8/12 moved the Brier from 0.338 to 0.708 without a single bet
    resolving, and every future open ticket would have pushed it further. A
    file whose whole job is to say whether my numbers beat the market cannot
    count unplayed games as losses; it also cannot silently drop a typo, so an
    unrecognised outcome is reported rather than skipped.
    """
    out, pending, bad = [], 0, []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            o = (r.get('outcome') or '').strip().lower()
            if not o:
                pending += 1
                continue
            if o not in SETTLED:
                bad.append(f"{r.get('date','?')} {r.get('leg','?')[:28]}: {o!r}")
                continue
            out.append((float(r['market_p']), float(r['my_p']), SETTLED[o]))
    return (out, pending, bad) if with_pending else out

def main():
    rows, pending, bad = load(with_pending=True)
    s = score(rows)
    if bad:
        print(f"!! {len(bad)} row(s) with an unreadable outcome — NOT scored:")
        for b in bad:
            print(f"   {b}")
    if not s['n']:
        print(f'calibration.csv has no settled rows yet ({pending} pending)')
        return 0
    print(f"rows            {s['n']} settled" + (f", {pending} pending" if pending else ""))
    print(f"Brier, market   {s['brier_market']:.4f}")
    print(f"Brier, mine     {s['brier_mine']:.4f}")
    print(f"edge            {s['edge']:+.4f}  "
          + ("(my numbers are helping)" if s['edge'] > 0 else
             "(the market is beating me -- the clamp stays)"))
    w, t = s['override_record']
    if t:
        print(f"overrides >5pts {t}, moved the right way {w} ({w}/{t})")
    return 0

def selftest():
    ok = [0, 0]
    def chk(c, msg):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    chk(score([]) == {'n': 0}, "an empty ledger says so instead of dividing by zero")
    # a perfect forecaster vs a coin-flip market
    s = score([(0.5, 1.0, True), (0.5, 0.0, False)])
    chk(s['brier_mine'] == 0.0 and s['brier_market'] == 0.25 and s['edge'] == 0.25,
        "perfect calls score 0, the coin-flip market scores 0.25, edge is the gap")
    # the 8/11 shape: a big override that was WRONG costs me vs the market
    s = score([(0.394, 0.53, False)])
    chk(s['brier_mine'] > s['brier_market'] and s['edge'] < 0,
        "a confident miss shows up as negative edge, not as a story")
    chk(s['overrides'] == 1 and s['override_record'] == (0, 1),
        "and it lands in the override tally as 0-for-1")
    s = score([(0.313, 0.494, True)])
    chk(s['override_record'] == (1, 1),
        "an override that moved TOWARD the truth counts for me")
    chk(score([(0.70, 0.72, True)])['overrides'] == 0,
        "inside five points is not an override")
    rows = load()
    chk(len(rows) >= 8 and all(0 <= m <= 1 and 0 <= y <= 1 for m, y, _ in rows),
        f"the seeded ledger parses ({len(rows)} rows, all probabilities sane)")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

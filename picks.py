#!/usr/bin/env python3
"""picks.py — the decision log. Rule 26 with teeth.

    python3 picks.py log "Dallas Wings ML" 0.81 "market number, no override"
    python3 picks.py check
    python3 picks.py --selftest

Rule 26 says state a number once and stop moving it. On 8/12 I broke it
inside three messages on a WNBA leg, one day after writing it down, and the
only thing that caught the flip was Ryan noticing. A rule whose sole
enforcement is the other person's memory is not enforced.

Logging a number for a leg already logged TODAY at a different number
prints the prior value, the delta, and what justified it — before the new
number goes anywhere near a slip. That is not a veto: the second number can
be right. It is a demand that the change be deliberate and visible, which
is exactly what was missing.

The bar comes from rule 23: a move beyond 5 points needs stated evidence,
and per rule 32 a move to zero (a veto) is the biggest move of all.
"""
import csv, os, sys

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'picks.csv')
FIELDS = ['date', 'leg', 'p', 'note']

def _today():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d')

def load(path=LOG):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))

def prior(rows, leg, date):
    """Every earlier number stated for this leg today, oldest first."""
    return [r for r in rows if r['leg'] == leg and r['date'] == date]

def verdict(old_p, new_p):
    """What the log says about a restatement. Thresholds are rule 23's."""
    d = new_p - old_p
    if abs(d) < 1e-9:
        return 'same', d
    if new_p == 0 or old_p == 0:
        return 'VETO', d          # rule 32: to/from zero is the largest move
    if abs(d) > 0.05:
        return 'FLIP', d          # past rule 23's clamp
    return 'nudge', d

def log(leg, p, note, path=LOG, date=None):
    date = date or _today()
    rows = load(path)
    # Every prior statement today, including ones this number happens to
    # match. Reverting to a number you already gave is not innocent -- it is
    # the SECOND half of a round trip, and printing only the differing entry
    # hides that the leg has been moved twice. The whole history or nothing.
    hist = prior(rows, leg, date)
    out = []
    if any(verdict(float(r['p']), p)[0] != 'same' for r in hist):
        for i, r in enumerate(hist, 1):
            v, d = verdict(float(r['p']), p)
            tag = 'same as this' if v == 'same' else f"{v} {d*100:+.0f} pts"
            out.append(f"  #{i} was {float(r['p'])*100:.0f}% [{tag}]"
                       f"   {r['note']}")
    new = not os.path.exists(path)
    with open(path, 'a', newline='') as fh:
        w = csv.DictWriter(fh, FIELDS)
        if new:
            w.writeheader()
        w.writerow({'date': date, 'leg': leg, 'p': f"{p:.4f}", 'note': note})
    return out

def flips(rows):
    """Every leg stated more than once on a day with a material change."""
    seen, out = {}, []
    for r in rows:
        k = (r['date'], r['leg'])
        if k in seen:
            v, d = verdict(float(seen[k]['p']), float(r['p']))
            if v in ('FLIP', 'VETO'):
                out.append((r['date'], r['leg'], float(seen[k]['p']),
                            float(r['p']), v))
        seen[k] = r
    return out

def main():
    a = sys.argv[1:]
    if a and a[0] == 'log':
        leg, p, note = a[1], float(a[2]), (a[3] if len(a) > 3 else '')
        for line in log(leg, p, note):
            print(line)
        print(f"logged {leg} @ {p*100:.0f}%")
        return 0
    rows = load()
    f = flips(rows)
    print(f"{len(rows)} picks logged, {len(f)} flip(s)")
    for date, leg, o, n, v in f:
        print(f"  {date}  {leg}: {o*100:.0f}% -> {n*100:.0f}%  [{v}]")
    return 0

def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(verdict(0.81, 0.81)[0] == 'same', "restating the same number is silent")
    chk(verdict(0.81, 0.79)[0] == 'nudge', "2 points inside rule 23's clamp is a nudge")
    chk(verdict(0.53, 0.42)[0] == 'FLIP',
        "the 8/11 Kunneman move, 53 -> 42, trips as a FLIP")
    chk(verdict(0.81, 0.0)[0] == 'VETO',
        "dropping the Wings leg registers as a VETO, not a nudge (rule 32)")
    chk(verdict(0.0, 0.81)[0] == 'VETO', "and un-dropping it is equally loud")
    v, d = verdict(0.81, 0.86)
    chk(v == 'nudge' and abs(d - 0.05) < 1e-9,
        "exactly 5 points is still inside the clamp, not past it")

    import tempfile
    p = os.path.join(tempfile.mkdtemp(), 'p.csv')
    chk(log("Dallas Wings ML", 0.81, "market", p, "2026-08-12") == [],
        "a first statement warns about nothing")
    w = log("Dallas Wings ML", 0.0, "starters out", p, "2026-08-12")
    chk(len(w) == 1 and 'VETO' in w[0],
        f"today's actual flip is caught at the moment of restatement ({w})")
    w2 = log("Dallas Wings ML", 0.81, "toronto 10-22, reverted", p, "2026-08-12")
    chk(len(w2) == 2,
        "the second flip cites BOTH prior numbers -- the whole history, so a "
        "third statement cannot pretend the first two did not happen")
    chk(log("Dallas Wings ML", 0.81, "next day", p, "2026-08-13") == [],
        "a new day starts clean -- lines move, that is not a flip")
    chk(len(flips(load(p))) == 2, "the ledger reports both flips after the fact")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

#!/usr/bin/env python3
"""research.py — the checks, before the answer.

    python3 research.py bar code
    python3 research.py log "WNBA has no totals ladder" feed board
    python3 research.py grade "WNBA has no totals ladder" wrong "read the markets list"
    python3 research.py misses
    python3 research.py --selftest

Ryan, 8/12: "we need to make some sort of rule so you thoroughly do your
research rather than slap an answer back in 2 seconds."

That is a real shape, not a mood. Every bad answer this week was fast, and
every one had a cheap check sitting next to it that went unrun:

  8/12  two broken pull_feeds ships inside one hour. Wrong endpoint first
        (pull_mlb, three functions up, uses the right one), then an
        unguarded None (fd_markets's own docstring says it returns None,
        and every other caller guards it). Both answers were already in
        the file being edited.
  8/12  recommended dropping a Wings -480 leg off Dallas's injury report
        without once looking at Toronto: 10-22, on the road, no Sykes
        since June 19.
  8/12  "thats all you found?" — shopped the board and stopped, with rule
        14 already on the wall saying the board is a floor, not a ceiling.
  8/10  quoted a live leg at 2.7% off Poisson instead of the empirical
        half-inning rate. The real number was near 7%.

Speed was never the failure. Answering before reading was. A fast answer
and a checked answer are different answers; when they differ, the checked
one ships. So: name the class of claim, run its checks, and say out loud
which ones you skipped. "I didn't check" is a complete sentence.
"""
import csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, 'research.csv')
FIELDS = ['date', 'claim', 'cls', 'checks', 'verdict', 'note',
          'outcome', 'catch']

# (name, required, what it actually means)
CHECKS = {
    'code': [
        ('docstring', True,
         "read the signature AND docstring of every function you call"),
        ('callers', True,
         "grep the other call sites — how do THEY guard the return value"),
        ('run', True,
         "execute it, or its selftest, against the input you think breaks"),
    ],
    'feed': [
        ('board', True, "the board / the feed itself"),
        ('offboard', True,
         "one source off the feed — rule 14, the feed is a floor and has "
         "missed Walsh -630, Plymouth -1100, McKenna, Hickey"),
        ('ladder', False,
         "the full alternate ladder, not just the main line — rule 19"),
    ],
    'matchup': [
        ('market', True,
         "the de-vigged market number FIRST, before any research — rule 23 "
         "caps you at ±5 points off it"),
        ('bothsides', True,
         "the same class of information on BOTH sides — rule 33"),
        ('baserate', True,
         "records, home/away, pace, and who is missing from each bench"),
        ('recency', False,
         "did the news break after the line last moved, or before — rule 36"),
    ],
    'live': [
        ('livepy', True,
         "python3 live.py, not hand arithmetic — rule 30, and rule 17's "
         "distribution, not Poisson"),
        ('state', True, "outs, inning, and which half — rule 18"),
    ],
}

def _today():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d')

def bar(cls):
    if cls not in CHECKS:
        raise KeyError(f"unknown class {cls!r}; have {sorted(CHECKS)}")
    return CHECKS[cls]

def audit(cls, done):
    """(verdict, missing_required, unrecognised).

    Unrecognised names come back rather than being swallowed. A typo that
    silently counts as a check is the same bug this file exists to stop.
    """
    names = {n for n, _, _ in bar(cls)}
    done = {d.strip().lower() for d in done if d.strip()}
    unknown = sorted(done - names)
    req = [n for n, r, _ in bar(cls) if r]
    missing = [n for n in req if n not in done]
    if not req:
        return 'SUPPORTED', [], unknown
    if len(missing) == len(req):
        return 'UNSUPPORTED', missing, unknown
    return ('THIN' if missing else 'SUPPORTED'), missing, unknown

def load(path=LOG):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))

def _write(rows, path=LOG):
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)

def log(claim, cls, done, note='', path=LOG, date=None):
    v, missing, unknown = audit(cls, done)
    rows = load(path)
    rows.append({'date': date or _today(), 'claim': claim, 'cls': cls,
                 'checks': '|'.join(sorted(done)), 'verdict': v,
                 'note': note, 'outcome': '', 'catch': ''})
    _write(rows, path)
    return v, missing, unknown

def grade(claim, outcome, catch='', path=LOG):
    """Mark the last statement of a claim right/wrong after the fact.

    `catch` is the check that would have caught it — the only field that
    ever changes behaviour, because it names tomorrow's checklist item.
    """
    rows = load(path)
    for r in reversed(rows):
        if r['claim'] == claim:
            r['outcome'], r['catch'] = outcome, catch
            _write(rows, path)
            return r
    return None

def misses(rows):
    """Claims that shipped under-checked, and claims that shipped wrong."""
    thin = [r for r in rows if r['verdict'] in ('THIN', 'UNSUPPORTED')]
    wrong = [r for r in rows if r['outcome'] == 'wrong']
    return thin, wrong

def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    cmd = a[0] if a else 'misses'

    if cmd == 'bar':
        if len(a) < 2:
            print(f"  classes: {', '.join(sorted(CHECKS))}")
            return 2
        print(f"\n  before you answer a {a[1].upper()} claim:\n")
        for n, r, why in bar(a[1]):
            print(f"    [{'required' if r else 'optional'}] {n:10} {why}")
        print("\n  skipped one? say which, and what it would have changed.\n")
        return 0

    if cmd == 'log':
        claim, cls, done = a[1], a[2], a[3:]
        v, missing, unknown = log(claim, cls, done)
        if unknown:
            print(f"  not a {cls} check (typo?): {', '.join(unknown)}")
        print(f"  [{v}] {claim}")
        if missing:
            print(f"  unrun: {', '.join(missing)}")
            print("  -> the answer must say so, in the answer.")
        return 1 if v == 'UNSUPPORTED' else 0

    if cmd == 'grade':
        r = grade(a[1], a[2], a[3] if len(a) > 3 else '')
        print(f"  {'graded ' + a[2] if r else 'no such claim'}: {a[1]}")
        return 0 if r else 1

    rows = load()
    thin, wrong = misses(rows)
    print(f"\n  {len(rows)} claims logged, {len(thin)} under-checked, "
          f"{len(wrong)} wrong")
    for r in thin:
        print(f"    [{r['verdict']:11}] {r['date']}  {r['claim'][:44]}")
    if wrong:
        print("\n  what would have caught them:")
        for r in wrong:
            print(f"    {r['catch'] or '(never recorded)'}  <- {r['claim'][:38]}")
    print()
    return 0

def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    # Today's two breaks, in order, both in the same file within one hour.
    chk(audit('code', [])[0] == 'UNSUPPORTED',
        "the 422: shipped an endpoint with zero checks run")
    chk(audit('code', ['run'])[0] == 'THIN',
        "the None: selftest passed, but the docstring went unread and the "
        "other callers ungrepped — a green selftest is one check, not three")
    chk(audit('code', ['docstring', 'callers', 'run'])[0] == 'SUPPORTED',
        "all three is what the fix finally got")
    v, missing, _ = audit('code', ['run'])
    chk(missing == ['docstring', 'callers'],
        f"and it names them rather than scoring a grade ({missing})")

    chk(audit('matchup', ['market', 'baserate'])[0] == 'THIN',
        "the Wings drop: Dallas's report read, Toronto never looked at")
    chk(audit('matchup', ['market', 'bothsides', 'baserate'])[0] == 'SUPPORTED',
        "Ryan's one-line question about Toronto was the whole missing check")
    chk(audit('matchup', ['bothsides', 'baserate'])[0] == 'THIN',
        "research without the de-vigged number first is backwards (rule 23)")

    chk(audit('feed', ['board'])[0] == 'THIN',
        "'thats all you found?' — the board is a floor, not the answer (14)")
    chk(audit('feed', ['board', 'offboard'])[0] == 'SUPPORTED',
        "one source off the feed clears it")

    chk(audit('live', [])[0] == 'UNSUPPORTED',
        "8/10's hand-rolled Poisson number cleared nothing")

    chk(audit('code', ['docstring', 'red'])[1:] == (['callers', 'run'], ['red']),
        "a typo'd check name is reported, never counted")
    try:
        audit('vibes', [])
        chk(False, "an unknown class raises")
    except KeyError:
        chk(True, "an unknown class raises instead of quietly passing")

    import tempfile
    p = os.path.join(tempfile.mkdtemp(), 'r.csv')
    v, missing, _ = log("alt totals live on the bulk endpoint", 'code', [],
                        "shipped it", p, "2026-08-12")
    chk(v == 'UNSUPPORTED' and len(load(p)) == 1, "an unchecked claim logs")
    grade("alt totals live on the bulk endpoint", 'wrong',
          "read pull_mlb's URL, three functions up", p)
    thin, wrong = misses(load(p))
    chk(len(thin) == 1 and len(wrong) == 1, "and grades wrong after the fact")
    chk(wrong[0]['catch'].startswith("read pull_mlb"),
        "carrying the check that would have caught it into tomorrow")
    log("WNBA ladders exist", 'feed', ['board', 'offboard'], '', p, "2026-08-12")
    chk(len(misses(load(p))[0]) == 1, "a supported claim is not a miss")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

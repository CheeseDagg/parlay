#!/usr/bin/env python3
"""placed.py — one command records a placed slip everywhere it must exist.

    python3 placed.py --name="W1 16-leg" --price=+116 --stake=100 legs.txt
    python3 placed.py --selftest

legs.txt, one leg per line, price required, model probability optional:
    PIT@MIA F5 Under 10.5   -5000   p=0.973
    Besiktas to advance     -6000   p=0.944
    Atlanta Dream ML        -520

Rules 29 and 31 said every placement writes slips.json and calibration.csv.
On 8/13 both were skipped for the one ticket that mattered: a 16-leg slip
placed in a rush at noon, and by evening no file in the repo knew its legs
-- the settle pass had nothing to grade and the calibration log lost the
day's quotes. The rule was fine; the chore was three files edited by hand
under time pressure. This makes it one command, and it REFUSES partial
records rather than storing something that looks complete:

  * every line must carry an American price -- a leg without a price
    cannot be checked against the app tomorrow;
  * model probabilities are optional per leg, but the slip's model_p is
    only computed when EVERY leg has one -- a product over half the legs
    would be a fabricated headline;
  * calibration.csv rows are written only for legs that carry p= -- the
    calibration file logs quotes, not guesses;
  * running it twice with the same name and date completes or no-ops,
    never duplicates.
"""
import csv, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SLIPS = os.path.join(HERE, 'slips.json')
CALIB = os.path.join(HERE, 'calibration.csv')
TICKETS = os.path.join(HERE, 'TICKETS.md')

# price accepts +0 as "HIDDEN BY THE APP": FanDuel SGP+ shows no per-leg
# prices, and 8/17's 25-legger could not be logged at all -- rules 29/31
# blocked by a regex. A hidden price is a fact about the app, not a reason
# the ledger goes empty; model p still rides in via p=.
LEG = re.compile(r'^(?P<lab>.*?)\s+(?P<price>[+-]\d{1,5})(?:\s+p=(?P<p>0?\.\d+))?\s*$')


def parse_legs(text):
    """(legs, why_refused). Every non-blank line must parse or nothing does."""
    legs = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        m = LEG.match(ln)
        if not m:
            return None, f"unparseable leg line: {ln!r} (need 'LABEL -PRICE [p=0.xx]')"
        p = float(m.group('p')) if m.group('p') else None
        if p is not None and not (0 < p < 1):
            return None, f"p={p} on {m.group('lab')!r} is not a probability"
        legs.append({'lab': m.group('lab').strip(),
                     'price': int(m.group('price')), 'p': p})
    if not legs:
        return None, "no legs parsed"
    return legs, None


def record(legs, name, price, stake, note, when, files=None):
    """Write the slip into slips.json, calibration.csv and TICKETS.md.
    Idempotent on (name, date): a re-run repairs, never duplicates."""
    fs = files or {'slips': SLIPS, 'calib': CALIB, 'tickets': TICKETS}
    date = when[:10]
    ps = [l['p'] for l in legs]
    model_p = None
    if all(p is not None for p in ps):
        model_p = 1.0
        for p in ps:
            model_p *= p
    d = json.load(open(fs['slips'])) if os.path.exists(fs['slips']) else {'slips': []}
    d.setdefault('slips', [])
    row = {'name': name, 'book': 'FanDuel', 'price': price,
           'stake': stake, 'placed': when,
           'model_p': round(model_p, 4) if model_p else None,
           'legs': [{'lab': l['lab'], 'price': l['price'],
                     **({'p': round(l['p'], 4)} if l['p'] else {})}
                    for l in legs],
           'note': note}
    hit = next((i for i, s in enumerate(d['slips'])
                if s.get('name') == name and str(s.get('placed', ''))[:10] == date),
               None)
    if hit is None:
        d['slips'].append(row)
    else:
        # REPAIR means repair. Until 8/15 a re-run silently kept the OLD
        # entry, so a correction run "succeeded" while the wrong numbers
        # stayed on disk -- caught live when slips C/D's EV correction
        # printed 'repaired' and changed nothing. Settlement flags someone
        # added by hand survive the rewrite.
        keep = {k: v for k, v in d['slips'][hit].items()
                if k in ('settled', 'result', 'outcome')}
        row.update(keep)
        d['slips'][hit] = row
    d['as_of'] = date
    json.dump(d, open(fs['slips'], 'w'), indent=1)
    got = set()
    if os.path.exists(fs['calib']):
        got = {(r[0], r[1]) for r in csv.reader(open(fs['calib'])) if r}
    nop = [l['lab'] for l in legs if l['p'] is None]
    with open(fs['calib'], 'a', newline='') as fh:
        w = csv.writer(fh)
        for l in legs:
            if l['p'] is not None and (date, l['lab']) not in got:
                w.writerow([date, l['lab'], round(l['p'], 4), round(l['p'], 4), 'open'])
    if nop:
        # 8/16: every leg of slips A-D bypassed the Brier ledger because the
        # placement calls omitted p= and this skip was SILENT. Rule 29 exists
        # so results grade the model; a quiet exemption defeats the ledger.
        print(f"  !! {len(nop)} leg(s) carry NO p= and are NOT in calibration: "
              + ', '.join(nop[:4]) + (' ...' if len(nop) > 4 else ''))
    # the idempotency key is name+price+DATE -- a repair run an hour later
    # must find the section, and the same window name next week must not
    head = f"## {name} — {price:+d} — placed {when}"
    key = f"## {name} — {price:+d} — placed {date}"
    md = open(fs['tickets']).read() if os.path.exists(fs['tickets']) else ''
    block = '\n'.join([f"\n{head}\n"]
                      + [f"- [ ] {l['lab']} — {l['price']:+d}"
                         + (f" (model {l['p']*100:.1f}%)" if l['p'] else '')
                         for l in legs]) + '\n'
    if key not in md:
        with open(fs['tickets'], 'a') as fh:
            fh.write(block)
    else:
        # same repair rule as slips.json: rewrite THIS section in place,
        # leaving ticked checkboxes alone if nothing else changed them
        import re as _re
        pat = _re.compile(_re.escape(key.split(' — placed ')[0])
                          + r'[^\n]*\n(?:- \[.\][^\n]*\n?)*')
        m2 = pat.search(md)
        if m2 and '- [x]' not in m2.group(0):
            md = md[:m2.start()] + block.lstrip('\n') + md[m2.end():]
            with open(fs['tickets'], 'w') as fh:
                fh.write(md)
    return {'n': len(legs), 'model_p': model_p, 'was_new': hit is None}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = {k: v for k, v in (a[2:].split('=', 1) for a in sys.argv[1:]
                             if a.startswith('--') and '=' in a)}
    if not args or 'name' not in opt or 'price' not in opt:
        print(__doc__.split('\n\n')[1]); return 2
    try:
        price = int(opt['price'])
    except ValueError:
        print(f"  refused: price {opt['price']!r} is not American"); return 1
    legs, why = parse_legs(open(args[0]).read())
    if legs is None:
        print(f"  refused: {why}"); return 1
    when = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    r = record(legs, opt['name'], price, int(opt.get('stake', 0)),
               opt.get('note', ''), when)
    mp = f"{r['model_p']*100:.1f}%" if r['model_p'] else 'NOT computed (legs missing p=)'
    print(f"  recorded {r['n']} legs -> slips.json + TICKETS.md"
          f" + calibration.csv; model {mp}"
          + ('' if r['was_new'] else '  (already existed -- repaired, not duplicated)'))
    return 0


def selftest():
    import tempfile
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    legs, why = parse_legs("A F5 Under 10.5  -5000  p=0.973\nB to advance  -6000  p=0.944\n")
    chk(legs and len(legs) == 2 and legs[0]['p'] == 0.973,
        "labelled lines with price and p parse")
    bad, why = parse_legs("A F5 Under 10.5  -5000\nnot a leg line\n")
    chk(bad is None and 'unparseable' in why,
        "ONE bad line refuses the WHOLE paste -- a slip with silently dropped "
        "legs is exactly the 8/13 failure again")
    bad, why = parse_legs("A  -500  p=1.2\n")
    chk(bad is None, "p outside (0,1) is refused")

    tmp = tempfile.mkdtemp()
    fs = {k: os.path.join(tmp, k) for k in ('slips', 'calib', 'tickets')}
    mixed, _ = parse_legs("A  -5000  p=0.973\nB  -6000\n")
    r = record(mixed, 'T1', 116, 100, '', '2026-08-13T17:15Z', fs)
    chk(r['model_p'] is None,
        "model_p over HALF the legs is refused -- no fabricated headline")
    d = json.load(open(fs['slips']))
    chk(len(d['slips']) == 1 and len(d['slips'][0]['legs']) == 2,
        "the slip lands in slips.json with every leg")
    rows = list(csv.reader(open(fs['calib'])))
    chk(len(rows) == 1 and rows[0][1] == 'A' and rows[0][4] == 'open',
        "calibration gets ONLY the leg that carried p=, marked open")
    chk('## T1 — +116' in open(fs['tickets']).read(),
        "TICKETS.md gets the checklist section")
    r2 = record(mixed, 'T1', 116, 100, '', '2026-08-13T18:00Z', fs)
    chk(not r2['was_new']
        and len(json.load(open(fs['slips']))['slips']) == 1
        and len(list(csv.reader(open(fs['calib'])))) == 1
        and open(fs['tickets']).read().count('## T1') == 1,
        "running it again duplicates NOTHING in any of the three files")
    full, _ = parse_legs("A  -5000  p=0.9\nB  -600  p=0.8\n")
    r3 = record(full, 'T2', -120, 50, '', '2026-08-13T19:00Z', fs)
    chk(abs(r3['model_p'] - 0.72) < 1e-9,
        "all legs carrying p= -> model_p is their product")
    # ---- REPAIR MEANS REPAIR (8/15, caught live): the slips C/D EV
    # correction printed 'repaired' while the old note stayed on disk,
    # because a (name,date) hit was a silent no-op.
    import tempfile as _tf; _t2 = _tf.mkdtemp()
    _d2 = {'slips': _t2+'/s.json', 'calib': _t2+'/c.csv', 'tickets': _t2+'/t.md'}
    _lg, _ = parse_legs("A Team ML -400\nB by KO/TKO +200")
    record(_lg, name='X', price=1000, stake=10, when='2026-08-15T19:00Z',
           note='WRONG 4.68', files=_d2)
    record(_lg, name='X', price=1000, stake=10, when='2026-08-15T19:00Z',
           note='CORRECTED 1.15', files=_d2)
    _s = json.load(open(_d2['slips']))
    chk(len(_s['slips']) == 1 and 'CORRECTED 1.15' in _s['slips'][0]['note'],
        "a re-run REPLACES the note in place -- no duplicate, no stale text")
    _s['slips'][0]['settled'] = 'won'
    json.dump(_s, open(_d2['slips'], 'w'))
    record(_lg, name='X', price=1000, stake=10, when='2026-08-15T19:00Z',
           note='third', files=_d2)
    chk(json.load(open(_d2['slips']))['slips'][0].get('settled') == 'won',
        "hand-added settlement flags survive the rewrite")

    _l, _w = parse_legs("Hidden SGP Leg +0 p=0.93")
    chk(_l and _l[0]['price'] == 0 and _l[0]['p'] == 0.93,
        "an SGP+ leg with the price HIDDEN logs at +0 with its model p -- "
        "the 8/17 25-legger was unloggable before this")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

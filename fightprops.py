#!/usr/bin/env python3
"""fightprops.py — a posted method market, de-vigged whole instead of guessed at.

    python3 fightprops.py quotes.txt
    python3 fightprops.py --selftest

quotes.txt, one outcome per line, straight from the app:
    Makhachev sub  -160
    Makhachev dec  +250
    Makhachev ko   +550
    Garry dec      +650
    Garry ko       +900
    Garry sub      +2500

fights.py's from_quote() prices a SINGLE method quote by assuming the
one-sided share of the overround is 2% -- an assumption, never measured,
because no full method market had ever been captured. When the app shows
the WHOLE ladder (two fighters x three methods), nothing needs assuming:
it is an N-way market and rule 30's measurement says N-way de-vigs POWER
(52,710 matches; board.devig_n). This file does that, and then uses the
full market to MEASURE what the one-sided haircut actually is, so the
next partial quote is priced off a measured number instead of the 2%.

What it prints, per full market:
  * each outcome's de-vigged probability -- under rule 27 these ARE the
    method probabilities; the model's mix (cardread) may differ by at
    most the five-point clamp;
  * the market's total overround;
  * each fighter's method-market win% (their three outcomes summed)
    beside the pin's moneyline consensus when the bout is found -- a
    method ladder that disagrees with its own moneyline is repriced
    information, and the drift is printed, not absorbed;
  * the measured one-sided haircut per line (implied/true - 1), with the
    mean to use in from_quote the next time only one price is visible.

Refusals: fewer than six outcomes (partial market -- each line falls back
to from_quote WITH the 2% assumption named out loud), unparseable lines,
duplicate outcomes, overround outside [2%, 40%].
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board
import fights

HERE = os.path.dirname(os.path.abspath(__file__))
UFCODDS = os.environ.get('UFCODDS') or os.path.join(HERE, '..', 'UFC-ODDS')
METHODS = {'dec': 'dec', 'decision': 'dec', 'points': 'dec',
           'ko': 'ko', 'tko': 'ko', 'ko/tko': 'ko',
           'sub': 'sub', 'submission': 'sub'}
LINE = re.compile(r'^(?P<who>.+?)\s+(?P<m>dec|decision|points|ko|tko|ko/tko|sub|submission)\s+(?P<am>[+-]\d{3,5})\s*$', re.I)


def parse(text):
    """([{who, m, am}], why_refused). One bad line refuses the paste."""
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        g = LINE.match(ln)
        if not g:
            return None, f"unparseable: {ln!r} (want 'Fighter method +/-price')"
        out.append({'who': g.group('who').strip(), 'm': METHODS[g.group('m').lower()],
                    'am': int(g.group('am'))})
    if not out:
        return None, 'no lines'
    seen = set()
    for o in out:
        k = (o['who'].lower(), o['m'])
        if k in seen:
            return None, f"duplicate outcome: {o['who']} {o['m']}"
        seen.add(k)
    return out, None


def imp(am):
    return 1.0 / fights.dec(am)


def full_market(quotes):
    """De-vig the six-outcome ladder; None if it is not a full ladder."""
    names = sorted({q['who'] for q in quotes})
    if len(names) != 2 or len(quotes) != 6:
        return None
    per = {n: [q for q in quotes if q['who'] == n] for n in names}
    if any(len(v) != 3 for v in per.values()):
        return None
    over = sum(imp(q['am']) for q in quotes) - 1.0
    if not (0.02 <= over <= 0.40):
        return None
    outs = []
    for q in quotes:
        others = [x['am'] for x in quotes if x is not q]
        p = board.devig_n(q['am'], others)
        outs.append({**q, 'p': p, 'haircut': imp(q['am']) / p - 1.0})
    return {'names': names, 'outs': outs, 'overround': over}


def pin_consensus(names):
    """Moneyline consensus for the bout from the UFC-ODDS pin, or None."""
    import json
    try:
        pin = json.load(open(os.path.join(UFCODDS, 'Github', 'odds', 'parsed_odds.json')))
    except Exception:
        return None
    ln = [n.lower() for n in names]
    for o in pin.values():
        fs = (str(o.get('f1', '')).lower(), str(o.get('f2', '')).lower())
        hit = [any(tok in f for f in fs) for tok in
               (ln[0].split()[-1], ln[1].split()[-1])]
        if all(hit):
            c = {o['f1']: o.get('cons1'), o['f2']: o.get('cons2')}
            return c
    return None


def report(quotes):
    fm = full_market(quotes)
    lines = []
    if fm is None:
        lines.append("NOT A FULL LADDER (need both fighters x dec/ko/sub, "
                     "6 outcomes, sane overround) -- single-sided fallback, "
                     "and every number below leans on the UNMEASURED 2% "
                     "one-sided assumption in fights.from_quote:")
        for q in quotes:
            lines.append(f"  {q['who']:<22} {q['m']:<4} {q['am']:+6d} -> "
                         f"{fights.from_quote(q['am'])*100:5.1f}%  (assumed)")
        return lines
    lines.append(f"full method ladder, overround {fm['overround']*100:.1f}%, "
                 f"de-vig POWER (N-way, rule 30):")
    for q in sorted(fm['outs'], key=lambda x: -x['p']):
        lines.append(f"  {q['who']:<22} {q['m']:<4} {q['am']:+6d} -> "
                     f"{q['p']*100:5.1f}%   (one-sided haircut "
                     f"{q['haircut']*100:+.1f}%)")
    hc = [q['haircut'] for q in fm['outs']]
    lines.append(f"  measured one-sided haircut: {min(hc)*100:.0f}% on the "
                 f"favourite outcome rising to {max(hc)*100:.0f}% on the "
                 f"longest -- PRICE-DEPENDENT under power, so a lone quote "
                 f"is priced off the haircut AT ITS PRICE LEVEL above, "
                 f"never the mean and never the old flat 2%")
    cons = pin_consensus(fm['names'])
    for n in fm['names']:
        mw = sum(q['p'] for q in fm['outs'] if q['who'] == n)
        line = f"  {n}: method-market win {mw*100:.1f}%"
        if cons:
            match = next((v for k, v in cons.items()
                          if n.split()[-1].lower() in k.lower()), None)
            if match:
                line += (f" vs moneyline consensus {match*100:.1f}% "
                         f"(drift {(mw-match)*100:+.1f})")
        lines.append(line)
    return lines


LOG = os.path.join(HERE, 'methodlog.csv')
LOG_FIELDS = ['date', 'f1', 'f2', 'who', 'm', 'am', 'p', 'result']
MIN_VERDICT = 30


def log_ladder(fm, when, path=LOG):
    """Persist a FULL ladder's de-vigged outcomes, idempotent per
    (date, bout, outcome). Partial markets are never logged -- a ledger of
    assumed numbers would calibrate the assumption, not the market."""
    import csv as _csv
    rows = list(_csv.DictReader(open(path))) if os.path.exists(path) else []
    key = {(r['date'], r['f1'], r['f2'], r['who'], r['m']) for r in rows}
    n = 0
    f1, f2 = fm['names']
    with open(path, 'a', newline='') as fh:
        w = _csv.DictWriter(fh, LOG_FIELDS)
        if not rows:
            w.writeheader()
        for q in fm['outs']:
            k = (when, f1, f2, q['who'], q['m'])
            if k in key:
                continue
            w.writerow({'date': when, 'f1': f1, 'f2': f2, 'who': q['who'],
                        'm': q['m'], 'am': q['am'], 'p': round(q['p'], 4),
                        'result': 'open'})
            n += 1
    return n


def settle(path=LOG, greco=None):
    """Grade open rows from Greco results: the fight's winner and method are
    public within a day of the card. -> (n_settled, calibration_lines)."""
    import csv as _csv
    import ufcform
    if not os.path.exists(path):
        return 0, ['no methodlog.csv yet']
    rows = list(_csv.DictReader(open(path)))
    if greco is None and any(r['result'] == 'open' for r in rows):
        ev = ufcform.parse_events(ufcform.get(f"{ufcform.RAW}/ufc_event_details.csv"))
        greco = ufcform.parse_bouts(ufcform.get(f"{ufcform.RAW}/ufc_fight_results.csv"), ev)
    n = 0
    for r in rows:
        if r['result'] != 'open':
            continue
        for bt in greco or []:
            names = {ufcform.norm(bt['a']), ufcform.norm(bt['b'])}
            if {ufcform.norm(r['f1']), ufcform.norm(r['f2'])} != names:
                continue
            winner = bt['a'] if bt['winner'] == 'a' else bt['b']
            hit = (ufcform.norm(winner) == ufcform.norm(r['who'])
                   and bt['method'] == r['m'])
            r['result'] = 'won' if hit else 'lost'
            n += 1
            break
    with open(path, 'w', newline='') as fh:
        w = _csv.DictWriter(fh, LOG_FIELDS)
        w.writeheader(); w.writerows(rows)
    done = [r for r in rows if r['result'] in ('won', 'lost')]
    lines = [f"{len(done)} settled, {sum(1 for r in rows if r['result'] == 'open')} open"]
    if len(done) < MIN_VERDICT:
        lines.append(f"NOT A VERDICT YET -- {MIN_VERDICT - len(done)} more settled "
                     "outcomes before the method market's calibration gets read")
    else:
        pred = sum(float(r['p']) for r in done) / len(done)
        act = sum(1 for r in done if r['result'] == 'won') / len(done)
        lines.append(f"method market calibration: predicted {pred*100:.1f}% "
                     f"actual {act*100:.1f}% over n={len(done)}")
    return n, lines


def main():
    import datetime
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--settle' in sys.argv:
        n, lines = settle()
        print(f"  settled {n} outcome(s)")
        for l in lines:
            print(f"  {l}")
        return 0
    src = args[0] if args else None
    text = open(src).read() if src and src != '-' else sys.stdin.read()
    quotes, why = parse(text)
    if quotes is None:
        print(f"  refused: {why}")
        return 1
    for ln in report(quotes):
        print(ln)
    fm = full_market(quotes)
    if fm and '--log' in sys.argv:
        n = log_ladder(fm, datetime.date.today().isoformat())
        print(f"  logged {n} outcome(s) -> methodlog.csv (settles itself "
              f"from Greco results after the card)")
    elif fm is None and '--log' in sys.argv:
        print("  NOT logged: only full ladders enter the ledger")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    q, why = parse("Makhachev sub -160\nMakhachev dec +250\nMakhachev tko +550\n"
                   "Garry decision +650\nGarry ko +900\nGarry sub +2500\n")
    chk(q is not None and len(q) == 6
        and sum(1 for x in q if x['m'] == 'dec') == 2,
        "the app's spellings fold: tko->ko, decision/points->dec")
    bad, why = parse("Makhachev sub -160\nnot a quote\n")
    chk(bad is None and 'unparseable' in why,
        "one bad line refuses the paste -- no silently dropped outcomes")
    dup, why = parse("A dec -200\nA decision +300\n")
    chk(dup is None and 'duplicate' in why,
        "the same outcome twice is refused, not averaged")

    fm = full_market(q)
    chk(fm is not None and abs(sum(x['p'] for x in fm['outs']) - 1) < 1e-9,
        "six outcomes de-vig POWER and sum to exactly 1")
    top = max(fm['outs'], key=lambda x: x['p'])
    chk(top['who'] == 'Makhachev' and top['m'] == 'sub',
        "the shortest price is the likeliest outcome after de-vig")
    chk(all(x['haircut'] > 0 for x in fm['outs']),
        "every implied price is above its true probability -- the haircut "
        "is measured per outcome, never assumed")
    chk(full_market(q[:5]) is None,
        "five outcomes is NOT a full ladder -- no whole-market claim")

    rep = report(q[:5])
    chk(any('2%' in l and 'assum' in l.lower() for l in rep),
        "the partial-market fallback names the 2% assumption out loud")
    rep6 = report(q)
    chk(any('measured one-sided haircut' in l and 'PRICE-DEPENDENT' in l
            for l in rep6),
        "a full ladder prints the MEASURED haircut and says it is price-"
        "dependent -- the first real ladder showed 11%% on the favourite "
        "outcome vs 73%% on the +3000, so neither a flat 2%% nor a mean "
        "may price a lone quote")
    chk(any('method-market win' in l for l in rep6),
        "each fighter's summed method win%% prints, for the moneyline "
        "drift check when the pin knows the bout")
    import tempfile, csv as _csv, ufcform
    tmp = os.path.join(tempfile.mkdtemp(), 'methodlog.csv')
    fm = full_market(q)
    n1 = log_ladder(fm, '2026-08-15', tmp)
    n2 = log_ladder(fm, '2026-08-15', tmp)
    chk(n1 == 6 and n2 == 0,
        "a ladder logs all six outcomes once -- re-running logs nothing")
    greco = ufcform.parse_bouts(
        "EVENT,BOUT,OUTCOME,WEIGHTCLASS,METHOD\n"
        "E1,Makhachev vs. Garry,W/L,Welterweight,Submission\n", {'E1': 2026})
    ns, lines = settle(tmp, greco)
    rows = list(_csv.DictReader(open(tmp)))
    won = [r for r in rows if r['result'] == 'won']
    chk(ns == 6 and len(won) == 1 and won[0]['who'] == 'Makhachev'
        and won[0]['m'] == 'sub',
        "the card settles the ledger by itself: winner-by-sub grades one "
        "row won and five lost, from the public result alone")
    chk(any('NOT A VERDICT YET' in l for l in lines),
        "six settled outcomes refuse to become a calibration verdict -- "
        "thirty before the method market gets read (sgplog's discipline)")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

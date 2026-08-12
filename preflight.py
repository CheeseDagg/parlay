#!/usr/bin/env python3
"""preflight.py — run every gate a slip must clear, in one command.

    python3 preflight.py "BAL@MIN F5 Under 10.5" "Dallas Wings" ...
    python3 preflight.py --selftest

The rules were never the problem this week. Every loss was a rule that
existed and did not fire: the -350 floor was typed by hand, the hot-game
veto sat unread in a stale slate, the overlap between two slips was
computed AFTER both were placed, and slips.json -- which has done
cross-slip kill analysis since 8/1 -- was fed nothing on either losing
night.

So this is one command, run before money moves, that checks what a machine
can check and says out loud what it cannot:

  FLOOR    every leg -350 or heavier                      (rule 2)
  PLUS     no plus-money legs                             (rule 3)
  SOCCER   no 3-way sides -- derived DC only              (rule 8)
  METHOD   flags single-method fight legs                 (rules 9, 27)
  HOT      no mid-rung total on a hot game                (rule 25)
  OVERLAP  shared legs with every open slip, and the      (rule 28)
           chance one event kills them all
  LOG      calibration.csv and slips.json entries pending (rules 29, 31)

FAIL blocks. WARN is a judgement call that must be spoken aloud, not
skipped in silence.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# These are matched against the app's OWN wording, so they have to be the
# app's wording. 'on points' was here and 'by points' was not -- and FanDuel
# writes the single-method market as "Islam Makhachev by Points". So on 8/12 a
# slip with TWO single-method main-event legs came back "2 method leg(s), all
# double-chance": the gate saw only the two double chances, whose labels happen
# to contain 'ko/tko', and never saw the legs rule 27 exists to catch.
METHOD_WORDS = ('by ko', 'by tko', 'ko/tko', 'by submission', 'by sub',
                'by decision', 'by points', 'on points', 'by dq',
                'inside the distance', 'goes the distance',
                'by unanimous', 'by split', 'by majority')

def gate_floor(legs, floor=350):
    bad = [l for l in legs if l['price'] > -floor]
    return ('FAIL' if bad else 'PASS',
            f"{len(bad)} leg(s) lighter than -{floor}: "
            + ', '.join(f"{l['lab']} {l['price']:+d}" for l in bad)
            if bad else f"all {len(legs)} legs -{floor} or heavier")

def gate_plus(legs):
    bad = [l for l in legs if l['price'] > 0]
    return ('FAIL' if bad else 'PASS',
            f"plus-money: {', '.join(l['lab'] for l in bad)}" if bad
            else "no plus-money legs")

def gate_soccer(legs):
    bad = [l for l in legs if l.get('fam') == 'SOC' and 'DC' not in l['lab']]
    return ('FAIL' if bad else 'PASS',
            f"raw 3-way soccer: {', '.join(l['lab'] for l in bad)}" if bad
            else "no raw 3-way soccer sides")

def gate_method(legs):
    m = [l for l in legs if any(w in l['lab'].lower() for w in METHOD_WORDS)]
    single = [l for l in m if ' or ' not in l['lab'].lower()]
    if not m:
        return 'PASS', "no method-of-victory legs"
    if single:
        return ('WARN', f"{len(single)} single-method leg(s) -- rule 27 wants "
                f"ML or a double chance: {', '.join(l['lab'] for l in single)}")
    return 'PASS', f"{len(m)} method leg(s), all double-chance"

def gate_hot(legs, hot):
    """A totals leg on a hot game must be that game's TOP rung."""
    bad = []
    for l in legs:
        if l.get('fam') in ('F5', 'FG') and l.get('grp') in hot:
            if not l.get('is_top_rung', False):
                bad.append(f"{l['lab']} ({hot[l['grp']]})")
    if not hot:
        return 'WARN', "no hot-game data -- is MLBTool's slate today's?"
    return ('FAIL' if bad else 'PASS',
            "mid-rung on a HOT game: " + '; '.join(bad) if bad
            else f"{len(hot)} hot game(s), no mid-rungs taken")

def gate_overlap(legs, open_slips):
    """open_slips: [(name, [labels], p)] already placed."""
    if not open_slips:
        return 'PASS', "no other open slips"
    out = []
    mine = {l['lab'] for l in legs}
    for name, labs, _ in open_slips:
        sh = mine & set(labs)
        if sh:
            out.append(f"{name}: {len(sh)} shared ({', '.join(sorted(sh))})")
    return ('WARN' if out else 'PASS',
            "; ".join(out) if out else "no legs shared with open slips")

def top_rungs(m):
    """{(game, family): deepest rung's label} over EVERY leg on the board.

    board.py files a game's full-game totals, its F5 totals AND its moneyline
    into ONE market key -- ('GT', g) -- because they are one process measured
    several ways. This used to read v[0] and take min() across that whole mixed
    list, which got both halves wrong: only the first family present (always FG)
    ever got an entry, so EVERY F5 leg on a hot game came back is_top_rung=False
    and the gate FAILed the correct top rung; and the label stored under that FG
    key was the min over F5+FG+ML together, so it was usually an F5 leg filed
    under FG. On 8/12 it blocked a clean ticket over COL@ARI F5 U11.5 and
    CHC@WSH F5 U11.5, both of which ARE their game's deepest F5 rung.

    It survived because the selftest only ever called gate_hot() with hand-built
    legs and an is_top_rung the test set itself -- the gate was covered, the
    thing that FEEDS the gate was not. Hence this function exists separately.
    """
    top = {}
    for v in m.values():
        for o in v:
            if o.get('fam') not in ('F5', 'FG'):
                continue
            k = (o.get('grp'), o['fam'])
            cur = top.get(k)
            if cur is None or o['price'] < cur['price']:
                top[k] = o
    return {k: o['lab'] for k, o in top.items()}

def run(legs, hot=None, open_slips=None):
    hot = hot or {}
    gates = [("FLOOR", gate_floor(legs)), ("PLUS", gate_plus(legs)),
             ("SOCCER", gate_soccer(legs)), ("METHOD", gate_method(legs)),
             ("HOT", gate_hot(legs, hot)),
             ("OVERLAP", gate_overlap(legs, open_slips or []))]
    return gates, any(v == 'FAIL' for _, (v, _) in gates)

def main():
    import board
    from board import build
    want = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not want:
        print(__doc__.strip().splitlines()[2])
        return 2
    m = build('FanDuel', min_price=0, cutoff=board._utcnow())
    idx = {o['lab']: o for v in m.values() for o in v}
    tops = top_rungs(m)
    legs, missing = [], []
    for w in want:
        o = idx.get(w)
        if not o:
            missing.append(w); continue
        o = dict(o)
        o['is_top_rung'] = tops.get((o.get('grp'), o.get('fam'))) == o['lab']
        legs.append(o)
    if missing:
        print(f"  not on the board (check spelling): {missing}")
    gates, failed = run(legs, board.hot_games('FanDuel'))
    print()
    for name, (v, msg) in gates:
        print(f"  [{v:4}] {name:8} {msg}")
    print(f"\n  {'BLOCKED' if failed else 'CLEAR'} -- {len(legs)} legs checked")
    print("  still yours: log to slips.json (31) and calibration.csv (29)")
    return 1 if failed else 0

def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    L = lambda lab, pr, **kw: dict(lab=lab, price=pr, **kw)

    chk(gate_floor([L('a', -400), L('b', -351)])[0] == 'PASS', "-351 clears the floor")
    chk(gate_floor([L('a', -400), L('b', -340)])[0] == 'FAIL',
        "-340 fails it -- 'it's only one leg' is rule 2's exact wording")
    chk(gate_plus([L('a', 134)])[0] == 'FAIL', "a +134 dog is blocked (rule 3)")

    chk(gate_soccer([L('PSV Eindhoven', -600, fam='SOC')])[0] == 'FAIL',
        "the leg shape that killed Slip A on the PSV draw is blocked by name")
    chk(gate_soccer([L('PSV DC (derived)', -300, fam='SOC')])[0] == 'PASS',
        "a derived Double Chance passes")

    chk(gate_method([L('Escarrega by KO/TKO', -400)])[0] == 'WARN',
        "yesterday's losing leg raises the rule-27 warning")
    chk(gate_method([L('Kunneman by Submission or on Points', 170)])[0] == 'PASS',
        "a double chance does not")
    chk(gate_method([L('Anthony Wint', -1400)])[0] == 'PASS', "a plain ML is fine")
    # ---- THE APP'S OWN WORDING, copied from the 8/12 UFC 330 bet slip.
    # This exact slip returned "all double-chance" while carrying two single
    # method legs, because the word list had 'on points' but not 'by points'.
    chk(gate_method([L('Islam Makhachev by Points', 135)])[0] == 'WARN',
        "FanDuel writes it 'by Points', and that is a single method leg")
    chk(gate_method([L('Ian Machado Garry by Points', 400)])[0] == 'WARN',
        "so is the other side of the same market")
    v, msg = gate_method([L('Kaue Fernandes by KO/TKO or on Points', 185),
                          L('Joel Alvarez by KO/TKO or Submission', -140),
                          L('Mansur Abdul Malik', -650),
                          L('Islam Makhachev by Points', 135)])
    chk(v == 'WARN' and 'by Points' in msg and 'Kaue' not in msg,
        f"and on the real slip it names ONLY the single-method leg, not the "
        f"two double chances sitting beside it ({msg})")

    hot = {'CHC@WSH': 'adj 10.82'}
    mid = [L('CHC@WSH F5 Under 9.5', -1200, fam='F5', grp='CHC@WSH', is_top_rung=False)]
    top = [L('CHC@WSH F5 Under 11.5', -4000, fam='F5', grp='CHC@WSH', is_top_rung=True)]
    chk(gate_hot(mid, hot)[0] == 'FAIL',
        "TUESDAY'S ACTUAL KILLER -- a mid rung on the hottest game -- is blocked")
    chk(gate_hot(top, hot)[0] == 'PASS', "the top rung on the same game passes")
    chk(gate_hot(mid, {})[0] == 'WARN',
        "no hot data is a WARN, never a silent PASS (the 4-day-stale slate)")

    slips = [("20-leg", ["Hasan by KO", "Wint ML"], 0.126)]
    v, msg = gate_overlap([L('Hasan by KO', -500), L('X', -400)], slips)
    chk(v == 'WARN' and 'Hasan by KO' in msg,
        "the 8/11 double-kill leg is named before the second slip goes in")
    chk(gate_overlap([L('X', -400)], slips)[0] == 'PASS', "disjoint slips pass")

    # ---- what FEEDS gate_hot. Every check above hands gate_hot an is_top_rung
    # the test set itself, so the lookup that computes it went uncovered and was
    # wrong from the day it shipped. This is board.py's real shape: one market
    # key per GAME carrying full-game totals, F5 totals and the moneyline.
    mixed = {('GT', 'COL@ARI'): [
        L('COL@ARI Under 14.5', -900, fam='FG', grp='COL@ARI'),
        L('COL@ARI Under 15.5', -1400, fam='FG', grp='COL@ARI'),
        L('COL@ARI F5 Under 10.5', -1600, fam='F5', grp='COL@ARI'),
        L('COL@ARI F5 Under 11.5', -3500, fam='F5', grp='COL@ARI'),
        L('Arizona Diamondbacks ML', -150, fam='ML', grp='COL@ARI')]}
    t = top_rungs(mixed)
    chk(t[('COL@ARI', 'F5')] == 'COL@ARI F5 Under 11.5',
        "the deepest F5 rung is found even though FG legs sit first in the list")
    chk(t[('COL@ARI', 'FG')] == 'COL@ARI Under 15.5',
        "and the FG top is the deepest FG rung -- NOT the -3500 F5 leg that "
        "min() over the mixed list used to file under FG")
    chk(('COL@ARI', 'ML') not in t, "moneylines are not a totals ladder")

    gates, failed = run(mid + [L('y', 120)], hot)
    chk(failed, "any FAIL blocks the whole preflight")
    gates, failed = run(top, hot)
    chk(not failed, "a clean ticket clears")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

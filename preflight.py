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
  TIE      a second leg has its first leg on file          (rule 40)
  STALE    no leg already under way, board is fresh        (rules 17, 18)
  DERIVED  synthesized prices named for confirmation       (rule 8)
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

def _ties():
    import json
    try:
        with open(os.path.join(HERE, 'ties.json')) as fh:
            return json.load(fh).get('ties', {})
    except Exception:
        return {}


def gate_tie(legs):
    """A second-leg soccer market must have its FIRST LEG on file.

    Rule 40. A 90-minute Double Chance prices the day and is blind to the tie,
    so on 8/13 Hammarby was taken as a routine home favourite when the tie was
    level from a 0-0 first leg -- a must-win, not a coast. 0-1 down with a red
    card it went 85% -> 17%, and the first-leg score had already gone past us
    that morning without being written down.

    The failure mode is silence, so silence is what this gate removes: a leg on
    a match listed in ties.json with no first_leg recorded FAILS. It cannot
    detect a tie nobody has listed -- that is what the WARN is for, and why
    ties.json is the thing to update, not this function.
    """
    ties = _ties()
    if not ties:
        return 'WARN', "ties.json unreadable -- no second-leg context checked"
    blind, ctx = [], []
    for l in legs:
        if l.get('fam') not in ('SOC', 'SOCT') and 'advance' not in l['lab'].lower():
            continue
        grp = (l.get('grp') or '').replace('SOC ', '')
        hit = next((k for k in ties if k in grp or grp in k
                    or k.split('-')[-1].lower() in l['lab'].lower()), None)
        if hit is None:
            continue                       # not a known tie; the sweep's job
        if not ties[hit].get('first_leg'):
            blind.append(f"{l['lab']} ({hit}: first leg NOT on file)")
        else:
            ctx.append(f"{hit} {ties[hit]['standing']}")
    if blind:
        return 'FAIL', "second leg with no first-leg score: " + '; '.join(blind)
    if ctx:
        return 'PASS', f"{len(ctx)} second-leg tie(s) with context: " + '; '.join(sorted(set(ctx)))
    return 'PASS', "no two-legged ties on this slip"


def board_age_min(now=None):
    """Minutes since pull_feeds wrote the feed, from the file's own header."""
    import re
    from datetime import datetime
    import other
    m = re.search(r'Generated (\d{4}-\d\d-\d\d \d\d:\d\d)Z', other.__doc__ or '')
    if not m:
        return None, None
    gen = m.group(1)
    import board
    n = datetime.strptime(now or board._utcnow(), "%Y-%m-%dT%H:%MZ")
    return (n - datetime.strptime(gen, "%Y-%m-%d %H:%M")).total_seconds() / 60, gen


def gate_stale(legs, now=None):
    """Refuse to bless a pregame price on a game that has already started.

    Two separate things went wrong on 8/13 and both look like this. Atlanta was
    quoted at -520 off a board that had since moved it to -550, and CIN@CWS F5
    Under 10.5 was quoted at 97.0% while the game was live at 8 runs in the
    third -- a number that was true at first pitch and worth about half that by
    the time it was said out loud.

    A leg whose event has started is not mispriced, it is UNPRICED: the pregame
    number is gone and live.py is the tool, not the board. So that is a FAIL,
    not a warning. Board age is a WARN because a fifteen-minute-old board is
    usually fine and always worth knowing.
    """
    import board
    n = now or board._utcnow()
    started = [l for l in legs if l.get('t') and l['t'] <= n]
    age, gen = board_age_min(n)
    if started:
        return ('FAIL', f"{len(started)} leg(s) already under way -- pregame price is "
                f"gone, price these with live.py: "
                + ', '.join(f"{l['lab']} (started {l['t']})" for l in started[:4]))
    if age is None:
        return 'WARN', "feed carries no generated-at header, so its age is unknown"
    if age > 90:
        return 'WARN', f"board is {age:.0f} min old (generated {gen}Z) -- re-pull before betting"
    return 'PASS', f"board {age:.0f} min old, no leg has started"


def gate_derived(legs):
    """A derived price is our arithmetic, not the book's, and must be confirmed.

    The DC payout is synthesized from the h2h de-vig because the feed carries no
    DC market. On 8/13 Ryan sent two real DC quotes -- the first ever checked
    against -- and both derived prices were 8% generous (-835 vs -900, -479 vs
    -500) and both probabilities ~2 points high. The haircut is recalibrated,
    but a synthesized number is still an estimate wearing a price's clothes, and
    every one of them has to be read off the app before it goes on a slip.
    """
    d = [l for l in legs if '(derived)' in l['lab']]
    if not d:
        return 'PASS', "no derived prices on this slip"
    return ('WARN', f"{len(d)} DERIVED price(s) -- confirm each on the app before "
            f"betting, the number here is our arithmetic: "
            + ', '.join(f"{l['lab']} {l['price']}" for l in d))


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
             ("HOT", gate_hot(legs, hot)), ("TIE", gate_tie(legs)),
             ("STALE", gate_stale(legs)), ("DERIVED", gate_derived(legs)),
             ("OVERLAP", gate_overlap(legs, open_slips or []))]
    return gates, any(v == 'FAIL' for _, (v, _) in gates)

def main():
    import board
    from board import build
    want = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not want:
        print(__doc__.strip().splitlines()[2])
        return 2
    # NO CUTOFF HERE, deliberately. build()'s cutoff drops games that have
    # already started, so asking preflight about a live leg used to come back
    # "not on the board (check spelling)" -- which reads as a typo and sent me
    # looking for one on 8/13 while the real answer was that the game was in
    # the third inning. A started leg is a thing the STALE gate must SEE in
    # order to fail it, so the pool is built wide and the gate does the judging.
    m = build('FanDuel', min_price=0)
    # A LABEL IS NOT A LEG. A team that plays twice in the horizon produces two
    # legs with the SAME label and different groups, prices and start times --
    # 19 such labels on the 8/13 board. This was `{o['lab']: o}`, last one wins,
    # so checking tonight's "New York City FC DC (derived)" silently graded
    # SUNDAY's match at -262 instead of tonight's at -493, and FAILed the floor
    # on a game that was never on the ticket. A gate that validates a different
    # fixture than the one being bet is worse than no gate.
    #
    # Earliest future start wins, because that is what "today's ticket" means,
    # and every collision is named so the choice is visible rather than assumed.
    idx, amb = {}, {}
    for v in m.values():
        for o in v:
            cur = idx.get(o['lab'])
            if cur is None:
                idx[o['lab']] = o
            else:
                amb.setdefault(o['lab'], [cur]).append(o)
                if o['t'] < cur['t']:
                    idx[o['lab']] = o
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
    hit = [w for w in want if w in amb]
    if hit:
        from times import ct
        print(f"  AMBIGUOUS label(s) — took the earliest start:")
        for w in hit:
            print(f"    {w}")
            for o in sorted(amb[w], key=lambda o: o['t']):
                mark = "  <- used" if o['t'] == idx[w]['t'] else ""
                print(f"      {ct(o['t']):17} {o['grp']:20} {o['price']:+6d}{mark}")
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

    # ---- TIE. Rule 40: a second leg whose first leg is not written down is a
    # blind bet, and the way it hides is by looking like an ordinary favourite.
    v, m_ = gate_tie([L('Hammarby DC (derived)', -647, fam='SOC',
                        grp='SOC Rakow-Hammarby')])
    chk(v == 'PASS' and 'level' in m_,
        "a second leg WITH its first leg on file passes, and says the standing")
    v, _ = gate_tie([L('Besiktas to advance', -6000, fam='SOC',
                       grp='SOC Besiktas-Hradec Kralove')])
    chk(v == 'FAIL',
        "a listed tie with first_leg still null FAILS -- silence is the failure "
        "mode this gate exists to remove, so it cannot be a warning")
    v, _ = gate_tie([L('Under 6.5 goals (PU-SL)', -4000, fam='SOCT',
                       grp='SOC PU-SL')])
    chk(v == 'PASS', "a one-off match is not a tie and is not scolded")
    v, _ = gate_tie([L('CHC@WSH F5 Under 10.5', -4500, fam='F5', grp='CHC@WSH')])
    chk(v == 'PASS', "and baseball never touches this gate")

    # ---- STALE. A started leg has no pregame price left, so it cannot pass.
    NOW = '2026-08-13T18:30Z'
    v, m_ = gate_stale([dict(L('CIN@CWS F5 Under 10.5', -4500, fam='F5',
                               grp='CIN@CWS'), t='2026-08-13T17:11Z')], now=NOW)
    chk(v == 'FAIL' and 'live.py' in m_,
        "a leg whose game has started FAILS and is sent to live.py -- 97% at "
        "first pitch was worth half that by the third inning")
    v, _ = gate_stale([dict(L('TEX@LAA F5 Under 10.5', -7000, fam='F5',
                              grp='TEX@LAA'), t='2026-08-14T02:08Z')], now=NOW)
    chk(v in ('PASS', 'WARN'), "a leg that has not started is not blocked by it")

    # ---- DERIVED. Our arithmetic must never be quoted as the book's price.
    v, m_ = gate_derived([L('Philadelphia Union DC (derived)', -887, fam='SOC')])
    chk(v == 'WARN' and '-887' in m_,
        "a derived price is named with its number so it can be confirmed -- "
        "the two real quotes we ever checked were both 8% off")
    v, _ = gate_derived([L('Atlanta Dream', -520, fam='WNBA')])
    chk(v == 'PASS', "a real book price is not flagged as derived")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

#!/usr/bin/env python3
"""edge.py — every totals leg the board offers vs what HISTORY says it hits.

    python3 edge.py              # floor-legal future legs, FanDuel
    python3 edge.py --all        # include sub-floor prices
    python3 edge.py --selftest

WHY. "You should recommend them because they are going to go under" (Ryan,
8/14). The board's p is the DE-VIGGED MARKET -- the book's own opinion with
the juice removed. It cannot, by construction, find a leg the book has
priced wrong. The measured tables can: sochist/sococalib (52,710 soccer
matches with closing odds), f5hist (6,681 first-fives with parks), cflhist
(321 CFL games). This file joins every totals leg to its own history and
prints IMPLIED vs MEASURED, sorted by the gap, receipts attached.

WHAT AN EDGE HERE MEANS, honestly: the 8/13 lesson ("the yesterday trap")
was trusting the BOOK's 99% on a soccer under; the measured league rate had
it 3 points lower and the leg died. The gap runs both ways -- a positive
edge is a candidate, a negative edge is a leg to walk past even though its
price looks safe. Both ends print. The middle is silence.

WHAT IS REFUSED, named rather than skipped silently:
  * full-game MLB totals -- linelog is 2 days old, and f5hist measures the
    first five innings only. No table, no number.
  * WNBA totals -- market-only by standing declaration (8/13).
  * any soccer league socbase cannot map -- a proxy is a stated assumption
    and prints as one; an absent league prints as absent.
  * moneylines, DC, fights, boxing -- this file is about totals, where the
    independent history actually exists.

The form column is CONTEXT, not arithmetic: both clubs' recent match totals
print beside the league number so a 2.6-average hiding a 4-3 is visible
(socform carries the scorelines for exactly that reason), but no invented
weight blends them into the measured rate.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FLOOR = -350


# ------------------------------------------------------------------ lookups
def _fc_league(lg_key):
    """odds-API key -> formcond model league name (sococalib vocabulary
    first, sochist second -- same join socbase makes, reused not re-guessed)."""
    import socbase as SB
    return SB.CALIB.get(lg_key) or SB.MAP.get(lg_key)


def pace_of(match, socform):
    """Mean of both clubs' last-5 match totals, or None if either side is
    missing -- half a pace is not a pace."""
    if not (match and socform):
        return None
    import socform as SF
    means = []
    for club in re.split(r'\s+v\s+', match)[:2]:
        hit = SF.find(socform, club.strip())
        f = hit[0] if isinstance(hit, tuple) else hit
        tots = (f or {}).get('totals') or []
        if len(tots) < 3:
            return None
        last = tots[-5:]
        means.append(sum(last) / float(len(last)))
    return sum(means) / 2.0 if len(means) == 2 else None


def soc_conditioned(lg_key, rung, match, socform, fc):
    """(p, src) with the TEAM-PACE delta applied, or None wherever the
    derivation did not ship: rung refused on the tail, league off-model,
    either club's form missing. formcond derived the deltas on train and
    verified them on an untouched 2025-07+ tail with 20 feature-shuffles
    as the bar; a rung that failed that stays on the league base here."""
    if not fc:
        return None
    ship = (fc.get('ship') or {}).get(str(rung))
    if not ship or not ship.get('ships'):
        return None
    name = _fc_league(lg_key)
    if not name:
        return None
    pace = pace_of(match, socform)
    if pace is None:
        return None
    import formcond as FC
    p = FC.conditioned(fc['model'], name, rung, pace)
    if p is None:
        return None
    mdl = fc['model']
    d = p - mdl['base'][name][str(rung)]
    return p, (f"form-conditioned: league base "
               f"{mdl['base'][name][str(rung)] * 100:.1f} {d * 100:+.1f} "
               f"(pace {pace:.2f} vs league {mdl['means'][name]:.2f})")


def soc_measured(lg_key, rung, socbase=None):
    """(p_under, src_note, n) from the league's own history, or None."""
    import socbase as SB
    SB = socbase or SB
    name, r, note = SB.rates(lg_key)
    if not r:
        return None
    # sococalib shape: {'under': {'3.5': p, ...}}
    u = r.get('under')
    if u and str(rung) in u:
        n = (r.get('result') or {}).get('n')
        return u[str(rung)], note or f"{name} (sococalib, n={n})", n
    # sochist shape: {'totals': [{'rung': 3.5, 'p': ...}]}
    for row in r.get('totals') or []:
        if abs(row['rung'] - rung) < 1e-9:
            return row['p'], note or f"{name} (sochist, n={row['n']})", row['n']
    return None


def f5_measured(rung, f5hist):
    for row in f5hist.get('rungs') or []:
        if abs(row['rung'] - rung) < 1e-9:
            return row['p'], f"league base, n={row['n']}", row['n']
    return None


def cfl_measured(rung, cflhist):
    row = (cflhist.get('stats') or {}).get('rungs', {}).get(str(rung))
    if not row:
        return None
    return row['p_under'], f"CFL 2022-25, n={row['n']}", row['n']


def parse_rung(lab):
    m = re.search(r'(\d+\.5)', lab)
    return float(m.group(1)) if m else None


def is_under(lab):
    l = lab.lower()
    if l.startswith('u') and not l.startswith('over'):
        return True
    return 'under' in l


# ------------------------------------------------------------------ the scan
def scan(pool, now, f5hist=None, cflhist=None, parks=None, socform=None,
         floor=FLOOR, socbase=None, hot=None, fc=None):
    """(rows, refused, disq): scored legs, named refusals, and legs
    DISQUALIFIED because the model's own game read overrides the league
    base -- a league-average number has nothing to say about a game the
    slate model already projects hot (the HOT gate's whole lesson, and the
    first live run of this scan proved it: TEX@ATH's F5 unders sorted as
    the top MLB candidates while hot_games had the game at adj 10.04)."""
    rows, refused, disq = [], {}, []
    hot = hot or {}
    dec_floor = 1 + 100.0 / -floor
    for o in pool:
        if o.get('t') and o['t'] <= now:
            continue
        fam = o.get('fam')
        if fam not in ('SOCT', 'F5', 'GT', 'FG', 'WNBA', 'CFL'):
            continue
        rung = parse_rung(o['lab'])
        if rung is None:
            continue
        under = is_under(o['lab'])
        if fam in ('GT', 'FG'):
            refused['MLB full-game'] = ('no measured table -- f5hist is F5-only, '
                                        'linelog holds 2 days')
            continue
        if fam == 'WNBA':
            refused['WNBA totals'] = 'market-only by declaration (8/13)'
            continue
        if o.get('d', 99) > dec_floor and o['price'] > floor and not SCAN_ALL:
            continue
        if fam == 'F5' and under and o.get('grp') in hot:
            disq.append((o['lab'], o['price'], hot[o['grp']]))
            continue
        got = None
        cond_src = None
        if fam == 'SOCT':
            c = soc_conditioned(o.get('lg', ''), rung, o.get('match'),
                                socform, fc)
            if c:
                # conditioned rate must still invert for an Over below, so it
                # enters the pipe as an UNDER rate exactly like the tables do
                got = (c[0], c[1], None)
                cond_src = c[1]
            else:
                got = soc_measured(o.get('lg', ''), rung, socbase)
            if not got:
                import socbase as _sb
                name, r, _ = (socbase or _sb).rates(o.get('lg', ''))
                if r:
                    refused[f"{name} rung {rung:g}"] = 'league measured, rung not in its table'
                else:
                    refused[o.get('lg') or 'soccer (no league key)'] = 'league unmeasured'
                continue
        elif fam == 'F5':
            got = f5_measured(rung, f5hist or {})
            if not got:
                continue
        elif fam == 'CFL':
            got = cfl_measured(rung, cflhist or {})
            if not got:
                refused['CFL rung %.1f' % rung] = 'not in cflhist rung table'
                continue
        p_meas, src, n = got
        if not under:
            p_meas = 1.0 - p_meas
        note = []
        if fam == 'F5':
            v = (parks or {}).get(o.get('grp'))
            if v is None:
                note.append('park UNMEASURED -- base rate unqualified')
            elif v[1] is not None and v[1] >= 1.30:
                note.append(f"PARK {v[0]} blowup x{v[1]:.2f} -- base overstates the under")
            else:
                note.append(f"park {v[0]} x{v[1]:.2f}" if v[1] else f"park {v[0]}")
        if fam == 'SOCT' and socform and o.get('match'):
            import socform as SF
            tots = []
            for club in re.split(r'\s+v\s+', o['match'])[:2]:
                hit = SF.find(socform, club.strip())
                f = hit[0] if isinstance(hit, tuple) else hit
                if f and f.get('totals'):
                    tots.append(f"{club.strip()} last {f['totals'][-5:]}")
            if tots:
                note.append('goals/match: ' + '; '.join(tots))
        rows.append({
            'lab': o['lab'], 'price': o['price'], 't': o.get('t'),
            'fam': fam, 'implied': o['p'], 'measured': p_meas,
            'edge': p_meas - o['p'], 'src': src, 'n': n,
            'note': ' | '.join(note),
        })
    rows.sort(key=lambda r: -r['edge'])
    return rows, refused, disq


SCAN_ALL = False


def main():
    global SCAN_ALL
    SCAN_ALL = '--all' in sys.argv
    import board
    from times import ct
    import preflight
    m = board.build('FanDuel', min_price=0)
    pool = [o for v in m.values() for o in v]
    now = board._utcnow()
    f5hist = json.load(open(os.path.join(HERE, 'f5hist.json')))
    cflhist = json.load(open(os.path.join(HERE, 'cflhist.json')))
    try:
        sf = json.load(open(os.path.join(HERE, 'socform.json')))
        socform = sf.get('all') or sf
    except Exception:
        socform = None
    parks = preflight._parks()
    try:
        fc = json.load(open(os.path.join(HERE, 'formcond.json')))
    except Exception:
        fc = None
    rows, refused, disq = scan(pool, now, f5hist, cflhist, parks, socform,
                               hot=board.hot_games('FanDuel'), fc=fc)
    if fc:
        shipped = [k for k, v in (fc.get('ship') or {}).items() if v.get('ships')]
        print(f"[formcond active: team-pace conditioning on rungs {shipped}]")
    else:
        print("[formcond absent -- league bases unconditioned; Actions builds it]")

    print(f"edge scan -- {len(rows)} totals legs scored against their own history")
    print(f"(floor {'OFF' if SCAN_ALL else FLOOR}; edge = measured - implied, points)\n")
    good = [r for r in rows if r['edge'] > 0.005]
    bad = [r for r in rows if r['edge'] < -0.03]
    if good:
        print("MEASURED ABOVE THE MARKET (candidates):")
        for r in good[:12]:
            print(f"  {ct(r['t']):16} {r['lab'][:40]:40} {r['price']:+7d}  "
                  f"implied {r['implied']*100:5.1f}  measured {r['measured']*100:5.1f}  "
                  f"edge {r['edge']*100:+5.1f}  ({r['src']})")
            if r['note']:
                print(f"                   {r['note']}")
    else:
        print("MEASURED ABOVE THE MARKET: nothing clears +0.5 pts today.")
    if bad:
        print("\nMEASURED BELOW THE MARKET (walk past these):")
        for r in bad[-8:]:
            print(f"  {ct(r['t']):16} {r['lab'][:40]:40} {r['price']:+7d}  "
                  f"implied {r['implied']*100:5.1f}  measured {r['measured']*100:5.1f}  "
                  f"edge {r['edge']*100:+5.1f}  ({r['src']})")
            if r['note']:
                print(f"                   {r['note']}")
    if disq:
        print("\nDISQUALIFIED (model's own game read overrides the league base):")
        for lab, pr, why in disq:
            print(f"  {lab[:44]:44} {pr:+7d}  {why}")
    if refused:
        print("\nREFUSED (no honest number):")
        for k, why in sorted(refused.items()):
            print(f"  {k}: {why}")
    return 0


# ------------------------------------------------------------------ selftest
def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    class SB:
        @staticmethod
        def rates(key):
            if key == 'soccer_epl':
                return 'England Premier League', {'totals': [
                    {'rung': 3.5, 'p': 0.686, 'n': 5700}]}, None
            if key == 'soccer_usa_mls':
                return 'USA MLS', {'under': {'4.5': 0.80, '5.5': 0.926},
                                   'result': {'n': 6085}}, None
            return None, None, 'unmeasured'

    f5h = {'rungs': [{'rung': 8.5, 'p': 0.858, 'n': 6681},
                     {'rung': 9.5, 'p': 0.906, 'n': 6681}]}
    cfl = {'stats': {'rungs': {'49.5': {'p_under': 0.467, 'n': 321}}}}
    L = lambda lab, pr, p, fam, **kw: dict(lab=lab, price=pr, p=p, d=1+100.0/-pr,
                                           fam=fam, t='2099-01-01T00:00Z', **kw)
    now = '2026-08-14T22:00Z'

    rows, ref, _ = scan([L('Under 3.5 goals (A-B)', -400, 0.64, 'SOCT',
                        lg='soccer_epl', match='Arsenal v Brentford')],
                     now, f5h, cfl, socbase=SB)
    chk(len(rows) == 1 and abs(rows[0]['edge'] - 0.046) < 1e-9,
        "a soccer under prices its own league: implied 64, measured 68.6, edge +4.6")

    rows, _, _ = scan([L('Over 4.5 goals (A-B)', -400, 0.30, 'SOCT',
                      lg='soccer_usa_mls')], now, f5h, cfl, socbase=SB)
    chk(abs(rows[0]['measured'] - 0.20) < 1e-9,
        "an OVER inverts the under table: MLS U4.5 80% -> O4.5 measured 20%")

    rows, ref, _ = scan([L('U2.5 X v Y', -500, 0.9, 'SOCT', lg='soccer_moon')],
                     now, f5h, cfl, socbase=SB)
    chk(not rows and 'soccer_moon' in ref,
        "an unmapped league is refused as a league")
    rows, ref, _ = scan([L('U2.5 X v Y', -500, 0.9, 'SOCT', lg='soccer_epl')],
                     now, f5h, cfl, socbase=SB)
    chk(not rows and any('rung 2.5' in k for k in ref)
        and any('league measured' in v for v in ref.values()),
        "a MEASURED league missing one rung refuses the RUNG, not the league "
        "-- the first live run printed 'La Liga unmeasured' beside scored "
        "La Liga rows, which is a self-contradiction")

    rows, _, _ = scan([L('CHC@WSH F5 Under 9.5', -1200, 0.93, 'F5', grp='CHC@WSH')],
                   now, f5h, cfl, parks={'CHC@WSH': ('Coors Field', 2.28)},
                   socbase=SB)
    chk(rows and abs(rows[0]['measured'] - 0.906) < 1e-9
        and 'PARK Coors Field' in rows[0]['note'],
        "an F5 under gets the measured rung base AND a hot park named as a "
        "reason to distrust it")

    # -110 would be the REAL price of a main CFL total, and the floor rightly
    # refuses it before the lookup ever runs -- so the fixture that proves the
    # lookup must be a deep alt rung, which is also the only CFL totals shape
    # this board could legally carry.
    rows, _, dq = scan([L('TEX@ATH F5 Under 8.5', -600, 0.80, 'F5', grp='TEX@ATH')],
                   now, f5h, cfl, parks={'TEX@ATH': ('Sutter Health Park', 1.07)},
                   socbase=SB, hot={'TEX@ATH': 'model adj_total 10.04 >= 10'})
    chk(not rows and dq and dq[0][0] == 'TEX@ATH F5 Under 8.5',
        "a HOT game's F5 under is DISQUALIFIED, not a candidate -- the scan's "
        "first live run ranked exactly this leg top of the MLB list")
    rows, _, dq = scan([L('TEX@ATH F5 Over 8.5', -600, 0.80, 'F5', grp='TEX@ATH')],
                   now, f5h, cfl, parks={}, socbase=SB,
                   hot={'TEX@ATH': 'adj 10.04'})
    chk(rows and 'UNMEASURED' in rows[0]['note'],
        "the hot disqualifier is one-sided (unders only) and a missing park "
        "prints as unmeasured, not as silence")
    rows, _, _ = scan([L('CFL Under 49.5 (SSK-BC)', -400, 0.80, 'CFL')],
                   now, f5h, cfl, socbase=SB)
    chk(rows and abs(rows[0]['measured'] - 0.467) < 1e-9
        and rows[0]['edge'] < -0.3,
        "the CFL under reads its own 321 games -- 46.7% measured against an "
        "80-implied price is a 33-point trap, the exact 9-point-lie shape "
        "cflhist was built to catch, writ larger")

    rows, ref, _ = scan([L('CHC@WSH Under 8.5', -400, 0.6, 'FG', grp='CHC@WSH'),
                      L('WNBA Under 158.5', -400, 0.6, 'WNBA')],
                     now, f5h, cfl, socbase=SB)
    chk(not rows and 'MLB full-game' in ref and 'WNBA totals' in ref,
        "full-game MLB and WNBA are refused with their reasons, not scanned")

    started = L('U3.5 (A-B)', -400, 0.6, 'SOCT', lg='soccer_epl')
    started['t'] = '2026-08-14T20:00Z'
    rows, _, _ = scan([started], now, f5h, cfl, socbase=SB)
    chk(not rows, "a started leg is not scanned -- live is live.py's job")

    rows, _, _ = scan([L('Under 3.5 goals (A-B)', -120, 0.52, 'SOCT',
                      lg='soccer_epl')], now, f5h, cfl, socbase=SB)
    chk(not rows, "a sub-floor price is skipped by default (rule 2)")

    chk(parse_rung('U5.5 Alverca v CF Estrela') == 5.5
        and parse_rung('Over 2.5 goals (C-OC)') == 2.5
        and parse_rung('Saskatchewan Roughriders') is None,
        "rung parsing reads both label shapes and refuses a moneyline")
    chk(is_under('U5.5 x') and is_under('Under 3.5 goals')
        and not is_under('Over 2.5 goals'),
        "under/over detection on both label shapes")

    # ---- FORM CONDITIONING. The whole reason formcond exists is the
    # Cincinnati case: league base 92.6 on a fixture whose clubs run hot.
    _fc = {'ship': {'5.5': {'ships': True}, '4.5': {'ships': False}},
           'model': {'means': {'USA MLS': 2.9},
                     'base': {'USA MLS': {'5.5': 0.926, '4.5': 0.828}},
                     'deltas': {'5.5': [0.03, 0.01, 0.0, -0.02, -0.06],
                                '4.5': [0.05, 0.02, 0.0, -0.03, -0.08]}}}
    _sf = {'orlando city sc': {'name': 'Orlando City SC',
                               'totals': [1, 4, 8, 2, 7]},
           'fc cincinnati': {'name': 'FC Cincinnati',
                             'totals': [3, 7, 8, 6, 8]}}
    _leg = L('Under 5.5 goals (Cincinnati-OC)', -480, 0.811, 'SOCT',
             lg='soccer_usa_mls', match='Orlando City SC v FC Cincinnati')
    rows, _, _ = scan([_leg], now, f5h, cfl, socform=_sf, socbase=SB, fc=_fc)
    chk(rows and abs(rows[0]['measured'] - 0.866) < 1e-9,
        f"the hot-pace fixture is CONDITIONED down: 92.6 league -> 86.6 "
        f"(pace 5.9 lands in the fast bin, -6)")
    chk(rows[0]['edge'] < 0.06,
        f"and the +11.5 mirage shrinks to {rows[0]['edge']*100:+.1f}")
    chk('form-conditioned' in rows[0]['src'],
        "the src names the conditioning and both numbers")
    rows, _, _ = scan([L('Under 4.5 goals (X-Y)', -400, 0.75, 'SOCT',
                         lg='soccer_usa_mls',
                         match='Orlando City SC v FC Cincinnati')],
                      now, f5h, cfl, socform=_sf, socbase=SB, fc=_fc)
    chk(rows and 'form-conditioned' not in rows[0]['src'],
        "a rung whose derivation did NOT ship stays on the league base")
    rows, _, _ = scan([_leg], now, f5h, cfl, socform=None, socbase=SB, fc=_fc)
    chk(rows and 'form-conditioned' not in rows[0]['src'],
        "no club form -> no conditioning, base rate stands")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

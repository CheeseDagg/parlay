#!/usr/bin/env python3
"""socsignals.py — the six-signal card for one soccer fixture.

    python3 socsignals.py soccer_colombia_primera_a "Atletico Nacional" "Junior"
    python3 socsignals.py --selftest

Ryan asked for a clean look at six signals: Recent Form, Head to Head,
Home/Away Splits, Opponent Rank, Injury Impact, Starter.

THE POINT OF THIS FILE IS THAT IT SAYS WHICH ONES IT CANNOT ANSWER. A card
with four real rows and two blanks is worth more than six rows where two are
invented, and the failure mode being designed against is specific and already
happened once: a league that looked covered because the surrounding rows were
full. Every signal here returns either a measured value or an explicit
UNAVAILABLE carrying the REASON, and nothing in between.

WHAT EACH SIGNAL COSTS, AND WHY TWO ARE DARK.
  Home/Away Splits  MEASURED   the grid is indexed by home and away already
  Head to Head      MEASURED   every cell of the grid IS a head-to-head
  Opponent Rank     DERIVED    points per game over the whole grid, ranked
  Recent Form       DARK       a results matrix carries NO DATES, so "last
                               five" cannot be ordered. socform has dates but
                               not these leagues. Confirmed, not assumed:
                               srcprobe round 7 checked both wikis and found
                               the only dated tables are managerial changes.
  Injury Impact     DARK       not in any results table on any source we
  Starter           DARK       reach; these live in team news, per fixture

A dark signal is a boundary, not a bug, and it is printed as one.
"""
import datetime as _dt
import json, os, sys, unicodedata

# A form row is only "recent" if it is actually recent. Colombia's dated rows
# stop on 2026-05-12 (the Apertura; the Finalización publishes no dates), and
# presenting that in September as "Recent Form" would be a signal that is not
# merely missing but WRONG -- last spring's team wearing this week's label.
# Anything older than this is dark, and says how old it is.
FORM_MAX_AGE_DAYS = 45

HERE = os.path.dirname(os.path.abspath(__file__))
UNAVAILABLE = '—'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return ' '.join(s.replace('.', ' ').replace('-', ' ').split())


def match_team(pool, name):
    """Loose join, but NEVER a guess between two candidates.

    Returns (key, None) on a clean hit, (None, reason) otherwise. Two clubs
    matching one query is refused rather than resolved by order -- the
    'River Plate' lesson: last file parsed won, and the wrong club's numbers
    reached a live ticket wearing an 'exact match' label."""
    n = norm(name)
    if not n:
        return None, 'no name given'
    exact = [k for k in pool if norm(k) == n]
    if len(exact) == 1:
        return exact[0], None
    part = [k for k in pool if n in norm(k) or norm(k) in n]
    if len(part) == 1:
        return part[0], None
    if len(part) > 1:
        return None, f'AMBIGUOUS: {name!r} matches {sorted(part)[:4]}'
    return None, f'no club matching {name!r} in this league'


def ranks(splits):
    """Whole-season points per game, home + away, ranked. The grid has every
    result, so this is the real table, not a recent-form proxy."""
    tot = {}
    for side in ('home', 'away'):
        for team, v in (splits.get(side) or {}).items():
            d = tot.setdefault(team, {'p': 0, 'pts': 0, 'gf': 0, 'ga': 0})
            d['p'] += v['p']
            d['pts'] += v['w'] * 3 + v['d']
            d['gf'] += v['gf']
            d['ga'] += v['ga']
    for d in tot.values():
        d['ppg'] = round(d['pts'] / d['p'], 3) if d['p'] else 0.0
    order = sorted(tot, key=lambda t: (-tot[t]['ppg'], -(tot[t]['gf'] - tot[t]['ga'])))
    for i, t in enumerate(order, 1):
        tot[t]['rank'] = i
    return tot, len(order)


def card(league_key, home, away, socbase=None):
    """{signal: {'value': str, 'measured': bool, 'why': str|None}}"""
    if socbase is None:
        import socbase as _sb
        socbase = _sb
    out = {}
    name, rates, note = socbase.rates(league_key)
    if not name:
        return {'_league': {'value': UNAVAILABLE, 'measured': False,
                            'why': note or 'league not measured'}}
    out['_league'] = {'value': name, 'measured': True, 'why': note}
    res = rates['result']
    out['League base'] = {
        'value': (f"home {res['home']:.1%} · draw {res['draw']:.1%} · "
                  f"away {res['away']:.1%} · {res['mean_goals']} goals (n={res['n']})"),
        'measured': True, 'why': None}
    und = rates.get('under') or {}
    if und:
        out['Under ladder'] = {
            'value': ' · '.join(f"U{k} {v:.1%}" for k, v in sorted(und.items(), key=lambda x: float(x[0]))),
            'measured': True, 'why': None}

    splits = getattr(socbase, 'extra_splits', lambda _n: None)(name)
    if not splits:
        for s in ('Home/Away Splits', 'Head to Head', 'Opponent Rank'):
            out[s] = {'value': UNAVAILABLE, 'measured': False,
                      'why': 'no per-match grid for this league (socextra covers it only '
                             'where Wikipedia publishes a results matrix)'}
    else:
        hk, hwhy = match_team(splits['home'], home)
        ak, awhy = match_team(splits['away'], away)
        if hk and ak:
            h, a = splits['home'][hk], splits['away'][ak]
            out['Home/Away Splits'] = {
                'value': (f"{hk} at home {h['w']}-{h['d']}-{h['l']} ({h['gf']}gf {h['ga']}ga, {h['ppg']} ppg)  |  "
                          f"{ak} away {a['w']}-{a['d']}-{a['l']} ({a['gf']}gf {a['ga']}ga, {a['ppg']} ppg)"),
                'measured': True, 'why': None}
            met = splits['h2h'].get('|'.join(sorted((hk, ak))))
            out['Head to Head'] = ({
                'value': '; '.join(f"{m['home']} {m['hg']}-{m['ag']} {m['away']}" for m in met),
                'measured': True, 'why': None} if met else {
                'value': UNAVAILABLE, 'measured': False,
                'why': 'these two have not met in the grid this season'})
            tot, n = ranks(splits)
            out['Opponent Rank'] = {
                'value': (f"{hk} #{tot[hk]['rank']}/{n} ({tot[hk]['ppg']} ppg)  |  "
                          f"{ak} #{tot[ak]['rank']}/{n} ({tot[ak]['ppg']} ppg)"),
                'measured': True, 'why': None}
        else:
            why = hwhy or awhy
            for s in ('Home/Away Splits', 'Head to Head', 'Opponent Rank'):
                out[s] = {'value': UNAVAILABLE, 'measured': False, 'why': why}

    out['Recent Form'] = _recent_form(name, home, away)
    for s in ('Injury Impact', 'Starter'):
        out[s] = {'value': UNAVAILABLE, 'measured': False,
                  'why': 'lives in per-fixture team news, not in any results table; '
                         'needs a lineup source or a manual read'}
    return out


def _form_store(league):
    try:
        with open(os.path.join(HERE, 'socextra.json')) as fh:
            return (json.load(fh).get(league) or {}).get('form') or {}
    except Exception:
        return {}


def _recent_form(league, home, away, today=None):
    """Measured only when the newest result is inside FORM_MAX_AGE_DAYS."""
    f = _form_store(league)
    if not f:
        return {'value': UNAVAILABLE, 'measured': False,
                'why': 'no dated results for this league. The results matrix socextra '
                       'reads has every score and NO dates, so "last five" cannot be '
                       'ordered; the Spanish round-by-round tables that do carry dates '
                       'were not found for this competition.'}
    today = today or _dt.date.today()
    parts, ages = [], []
    for side, team in (('home', home), ('away', away)):
        k, why = match_team(f, team)
        if not k:
            return {'value': UNAVAILABLE, 'measured': False, 'why': why}
        v = f[k]
        try:
            age = (today - _dt.date.fromisoformat(v['newest'])).days
        except Exception:
            return {'value': UNAVAILABLE, 'measured': False,
                    'why': f'{k}: unreadable date on the newest result'}
        ages.append((k, v['newest'], age))
        parts.append(f"{k} {v['form']} ({v['gf']}gf {v['ga']}ga, last {v['newest']})")
    worst = max(ages, key=lambda x: x[2])
    if worst[2] > FORM_MAX_AGE_DAYS:
        return {'value': UNAVAILABLE, 'measured': False,
                'why': (f'STALE: the newest dated result for {worst[0]} is {worst[1]}, '
                        f'{worst[2]} days old (limit {FORM_MAX_AGE_DAYS}). This league '
                        f'publishes dates for only part of the season, and last '
                        f'season-half\'s form under a "recent" label is worse than none.')}
    return {'value': '  |  '.join(parts), 'measured': True,
            'why': None if worst[2] <= 14 else f'newest result is {worst[2]} days old'}


ORDER = ['League base', 'Under ladder', 'Home/Away Splits', 'Head to Head',
         'Opponent Rank', 'Recent Form', 'Injury Impact', 'Starter']


def render(c, home, away):
    lines = []
    lg = c.get('_league', {})
    lines.append(f"{home} v {away}   [{lg.get('value')}]")
    if lg.get('why'):
        lines.append(f"  ! {lg['why']}")
    if not lg.get('measured'):
        return '\n'.join(lines)
    for k in ORDER:
        v = c.get(k)
        if not v:
            continue
        mark = ' ' if v['measured'] else '·'
        lines.append(f"  {mark} {k:18} {v['value']}")
        if not v['measured'] and v['why']:
            lines.append(f"      why: {v['why']}")
    live = sum(1 for k in ORDER if c.get(k, {}).get('measured'))
    lines.append(f"  -- {live}/{len(ORDER)} signals measured; the rest print their reason")
    return '\n'.join(lines)


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    class FakeSB:
        def __init__(self, splits, rates=True):
            self._s, self._r = splits, rates

        def rates(self, key):
            if not self._r:
                return None, None, 'not in socbase.MAP'
            return ('Fake League',
                    {'result': {'home': .5, 'draw': .25, 'away': .25,
                                'mean_goals': 2.5, 'n': 100},
                     'under': {'2.5': .5, '3.5': .75}}, None)

        def extra_splits(self, name):
            return self._s

    sp = {'home': {'Alpha FC': {'p': 5, 'w': 4, 'd': 1, 'l': 0, 'gf': 10, 'ga': 2, 'ppg': 2.6},
                   'Beta FC':  {'p': 5, 'w': 1, 'd': 1, 'l': 3, 'gf': 4, 'ga': 8, 'ppg': 0.8}},
          'away': {'Beta FC':  {'p': 5, 'w': 0, 'd': 2, 'l': 3, 'gf': 2, 'ga': 9, 'ppg': 0.4},
                   'Alpha FC': {'p': 5, 'w': 3, 'd': 0, 'l': 2, 'gf': 8, 'ga': 6, 'ppg': 1.8}},
          'h2h': {'Alpha FC|Beta FC': [{'home': 'Alpha FC', 'away': 'Beta FC', 'hg': 3, 'ag': 0}]}}

    c = card('k', 'Alpha FC', 'Beta FC', socbase=FakeSB(sp))
    chk(c['Home/Away Splits']['measured'], 'home/away split is measured from the grid')
    chk(c['Head to Head']['measured'] and '3-0' in c['Head to Head']['value'],
        'head to head reads the actual grid result')
    chk(c['Opponent Rank']['measured'] and '#1' in c['Opponent Rank']['value'],
        'opponent rank derives a table from the whole grid')

    chk(c['Recent Form']['measured'] is False, 'Recent Form is NOT reported as measured')
    chk('dates' in c['Recent Form']['why'].lower(),
        'Recent Form states WHY it is dark (names the missing dates)')
    chk(all(not c[s]['measured'] and c[s]['why'] for s in ('Injury Impact', 'Starter')),
        'Injury and Starter are dark WITH a reason, never blank')

    import datetime as _d
    store = {'Alpha FC': {'form': 'WWDLW', 'n': 5, 'gf': 9, 'ga': 4, 'newest': '2026-09-20'},
             'Beta FC':  {'form': 'LLDWL', 'n': 5, 'gf': 3, 'ga': 8, 'newest': '2026-09-18'},
             'Stale FC': {'form': 'WWWWW', 'n': 5, 'gf': 12, 'ga': 1, 'newest': '2026-05-12'}}
    globals()['_form_store'] = lambda _lg: store
    today = _d.date(2026, 9, 30)
    fresh = _recent_form('L', 'Alpha FC', 'Beta FC', today=today)
    chk(fresh['measured'] and 'WWDLW' in fresh['value'], 'fresh dated form IS measured')
    stale = _recent_form('L', 'Alpha FC', 'Stale FC', today=today)
    chk(not stale['measured'], 'form whose newest result is 4 months old is NOT measured')
    chk('STALE' in stale['why'] and '2026-05-12' in stale['why'] and '141 days' in stale['why'],
        'the stale reason names the date and the age')
    chk(not _recent_form('L', 'Alpha FC', 'Ghost FC', today=today)['measured'],
        'a club with no form row darkens Recent Form')
    globals()['_form_store'] = lambda _lg: {}
    chk('NO dates' in _recent_form('L', 'A', 'B', today=today)['why'].replace('NO dates', 'NO dates')
        or 'no dates' in _recent_form('L', 'A', 'B', today=today)['why'].lower(),
        'a league with no dated source says so')

    c2 = card('k', 'Alpha', 'Nobody FC', socbase=FakeSB(sp))
    chk(not c2['Head to Head']['measured'] and 'no club matching' in c2['Head to Head']['why'],
        'an unmatched club darkens the grid signals with a named reason')

    sp2 = {'home': {'Deportivo A': {'p': 1, 'w': 1, 'd': 0, 'l': 0, 'gf': 1, 'ga': 0, 'ppg': 3.0},
                    'Deportivo B': {'p': 1, 'w': 0, 'd': 0, 'l': 1, 'gf': 0, 'ga': 1, 'ppg': 0.0}},
           'away': {'Deportivo B': {'p': 1, 'w': 0, 'd': 0, 'l': 1, 'gf': 0, 'ga': 1, 'ppg': 0.0}},
           'h2h': {}}
    c3 = card('k', 'Deportivo', 'Deportivo B', socbase=FakeSB(sp2))
    chk('AMBIGUOUS' in (c3['Home/Away Splits']['why'] or ''),
        'two clubs matching one name is REFUSED, not resolved by order')

    c4 = card('k', 'A', 'B', socbase=FakeSB(None))
    chk(not c4['Home/Away Splits']['measured'] and 'no per-match grid' in c4['Home/Away Splits']['why'],
        'a league with rates but no grid darkens only the grid signals')

    c5 = card('k', 'A', 'B', socbase=FakeSB(sp, rates=False))
    chk(list(c5) == ['_league'] and not c5['_league']['measured'],
        'an unmeasured league returns one honest row, not a card of blanks')

    t, n = ranks(sp)
    chk(t['Alpha FC']['rank'] == 1 and n == 2, 'rank orders by ppg across home and away')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


def main():
    if len(sys.argv) < 4:
        print(__doc__.strip().splitlines()[2])
        return 2
    key, home, away = sys.argv[1], sys.argv[2], sys.argv[3]
    print(render(card(key, home, away), home, away))
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

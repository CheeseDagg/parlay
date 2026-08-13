#!/usr/bin/env python3
"""mlbform.py — recent form for today's MLB slate: starters and F5 environment.

    python3 mlbform.py                 # today's slate -> mlbform.json
    python3 mlbform.py --date=2026-08-13
    python3 mlbform.py --selftest

Ryan vetoed Aaron Nola with "aaron nola is a gopher baller" and questioned
Drohan/Sasaki the same way, and the only honest answer available was "I have
no batted-ball data in this container." Meanwhile CIN@CWS put up 12 by the
fifth behind two starters whose recent form nothing in the toolchain had
looked at. Form was the stated requirement and there was no form anywhere.

statsapi has all of it, free:

  STARTERS  probable pitchers for the slate, then each one's last five
            starts -- innings, home runs, runs. HR/9 over that block is the
            measured version of "gopher baller"; runs-per-start through the
            block is the measured version of "getting hit".
  TEAMS     each club's last ten completed games, runs scored and allowed
            through five innings only, because that is the window the legs
            settle in. Full-game form flatters teams with loud bullpens.

WHAT A SMALL SAMPLE IS ALLOWED TO SAY. Five starts is ~25-30 innings; a
HR/9 computed on fewer than six total innings is noise wearing a decimal
point, so it is reported as None rather than a number. Ten games of team F5
runs has a wide band and is reported as context, never as a veto. The FORM
gate that reads this file WARNs -- it never blocks -- because recent form is
a reason to look harder, not a measurement of tonight.
"""
import json, os, sys, urllib.request
from datetime import date, datetime, timedelta

API = "https://statsapi.mlb.com/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'mlbform.json')

# HR/9 bands. League-average starter sits near 1.1-1.3; 1.8 over five starts
# is genuinely elevated and 2.4 is serving batting practice.
HR9_WARN = 1.8


def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default


def get(url, timeout=45):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


# ---------------------------------------------------------------- pure parts
def ip_outs(ip):
    """statsapi innings: '5.2' means 5 innings and TWO OUTS, not 5.2 innings.
    Reading it as a decimal understates every denominator by up to 22%."""
    s = str(ip).strip()
    if not s:
        return 0
    if '.' in s:
        a, b = s.split('.')
        return int(a) * 3 + int(b)
    return int(s) * 3


def parse_gamelog(doc, n=5):
    """Last n STARTS from a pitching game log -- relief outings are excluded,
    because one mop-up inning would dilute exactly the signal being asked for."""
    rows = []
    for grp in doc.get('stats', []):
        for s in grp.get('splits', []):
            st = s.get('stat', {})
            if int(st.get('gamesStarted', 0) or 0) < 1:
                continue
            rows.append({'date': s.get('date', ''),
                         'outs': ip_outs(st.get('inningsPitched', '0')),
                         'hr': int(st.get('homeRuns', 0) or 0),
                         'r': int(st.get('runs', st.get('earnedRuns', 0)) or 0)})
    rows.sort(key=lambda r: r['date'])
    return rows[-n:]


def hr9(starts):
    """HR per 9 innings across the block, or None below six total innings --
    a rate on eighteen outs is noise wearing a decimal point."""
    outs = sum(s['outs'] for s in starts)
    if outs < 18:
        return None
    return round(sum(s['hr'] for s in starts) * 27 / outs, 2)


def r_per_start(starts):
    if not starts:
        return None
    return round(sum(s['r'] for s in starts) / len(starts), 2)


def game_f5_split(linescore, side):
    """(mine, theirs) runs through five for one side, or None if unusable.
    Same edge rules as f5hist: an unplayed home fifth is a real zero, any
    other missing half is missing data."""
    inns = linescore.get('innings') or []
    if len(inns) < 5:
        return None
    mine = theirs = 0
    for inn in inns[:5]:
        for sd in ('away', 'home'):
            r = (inn.get(sd) or {}).get('runs')
            if r is None:
                if sd == 'home' and inn.get('num') == 5:
                    r = 0
                else:
                    return None
            if sd == side:
                mine += int(r)
            else:
                theirs += int(r)
    return mine, theirs


def team_form(rows):
    """rows: [(date, mine, theirs)] -> averages over the last ten."""
    rows = sorted(rows)[-10:]
    if not rows:
        return None
    return {'n': len(rows),
            'f5_for': round(sum(m for _, m, _ in rows) / len(rows), 2),
            'f5_ag': round(sum(t for _, _, t in rows) / len(rows), 2)}


# ---------------------------------------------------------------- network
def team_f5_form(team_id, end):
    start = (datetime.strptime(end, '%Y-%m-%d') - timedelta(days=25)).strftime('%Y-%m-%d')
    d = get(f"{API}/schedule?sportId=1&teamId={team_id}&startDate={start}"
            f"&endDate={end}&hydrate=linescore")
    rows = []
    for day in d.get('dates', []):
        for g in day.get('games', []):
            if g.get('status', {}).get('abstractGameState') != 'Final':
                continue
            side = ('home' if (g.get('teams', {}).get('home', {})
                               .get('team', {}).get('id') == team_id) else 'away')
            sp = game_f5_split(g.get('linescore') or {}, side)
            if sp:
                rows.append((day.get('date', ''), sp[0], sp[1]))
    return team_form(rows)


def starter(pp, season):
    if not pp:
        return {'name': None, 'hr9_5': None, 'r_start': None,
                'note': 'NO PROBABLE LISTED'}
    starts = parse_gamelog(get(f"{API}/people/{pp['id']}/stats"
                               f"?stats=gameLog&group=pitching&season={season}"))
    return {'name': pp.get('fullName'), 'hr9_5': hr9(starts),
            'r_start': r_per_start(starts), 'starts': len(starts)}


def main():
    today = flag('date', date.today().isoformat())
    season = today[:4]
    abbr = {t['id']: t.get('abbreviation', '?')
            for t in get(f"{API}/teams?sportId=1").get('teams', [])}
    yday = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    sched = get(f"{API}/schedule?sportId=1&date={today}&hydrate=probablePitcher")
    games = {}
    for day in sched.get('dates', []):
        for g in day.get('games', []):
            ta = g['teams']['away']['team']; th = g['teams']['home']['team']
            key = f"{abbr.get(ta['id'], '?')}@{abbr.get(th['id'], '?')}"
            asp = starter(g['teams']['away'].get('probablePitcher'), season)
            hsp = starter(g['teams']['home'].get('probablePitcher'), season)
            af = team_f5_form(ta['id'], yday)
            hf = team_f5_form(th['id'], yday)
            env = None
            if af and hf:
                env = round((af['f5_for'] + hf['f5_ag']) / 2
                            + (hf['f5_for'] + af['f5_ag']) / 2, 2)
            games[key] = {'away_sp': asp, 'home_sp': hsp,
                          'away_form': af, 'home_form': hf, 'f5_env': env}
    print(f"MLB form for {today} -- {len(games)} games\n")
    print(f"  {'game':<10} {'away starter':<22}{'hr9':>5} {'home starter':<22}{'hr9':>5} {'F5 env':>7}")
    for k, v in games.items():
        a, h = v['away_sp'], v['home_sp']
        fa = '  -- ' if a['hr9_5'] is None else f"{a['hr9_5']:5.2f}"
        fh = '  -- ' if h['hr9_5'] is None else f"{h['hr9_5']:5.2f}"
        gop = '  << GOPHER' if any(x['hr9_5'] and x['hr9_5'] >= HR9_WARN
                                   for x in (a, h)) else ''
        print(f"  {k:<10} {str(a['name'])[:21]:<22}{fa} {str(h['name'])[:21]:<22}{fh} "
              f"{v['f5_env'] if v['f5_env'] is not None else '--':>7}{gop}")
    with open(OUT, 'w') as fh_:
        json.dump({'date': today, 'hr9_warn': HR9_WARN, 'games': games}, fh_, indent=1)
    print(f"\nwrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    chk(ip_outs('5.2') == 17 and ip_outs('6') == 18 and ip_outs('0.1') == 1,
        "statsapi '5.2' is five innings and TWO OUTS -- read as a decimal it "
        "understates every rate's denominator")

    doc = {'stats': [{'splits': [
        {'date': '2026-08-01', 'stat': {'gamesStarted': 1, 'inningsPitched': '6.0', 'homeRuns': 2, 'runs': 3}},
        {'date': '2026-08-06', 'stat': {'gamesStarted': 0, 'inningsPitched': '1.0', 'homeRuns': 0, 'runs': 0}},
        {'date': '2026-07-27', 'stat': {'gamesStarted': 1, 'inningsPitched': '5.1', 'homeRuns': 1, 'runs': 2}},
        {'date': '2026-08-11', 'stat': {'gamesStarted': 1, 'inningsPitched': '4.2', 'homeRuns': 3, 'runs': 5}},
    ]}]}
    st = parse_gamelog(doc, n=5)
    chk(len(st) == 3 and st[0]['date'] == '2026-07-27' and st[-1]['hr'] == 3,
        "relief outings are excluded and starts come back oldest-first -- one "
        "mop-up inning would dilute exactly the signal being asked about")
    chk(hr9(st) == round(6 * 27 / 48, 2),
        "HR/9 uses outs: 6.0 + 5.1 + 4.2 innings is 18+16+14 = 48 outs")
    chk(hr9([{'outs': 12, 'hr': 4, 'r': 9}]) is None,
        "a rate on fewer than six innings is refused, not reported")
    chk(r_per_start(st) == round(10 / 3, 2), "runs per start over the block")

    ls = {'innings': [
        {'num': 1, 'away': {'runs': 1}, 'home': {'runs': 0}},
        {'num': 2, 'away': {'runs': 0}, 'home': {'runs': 2}},
        {'num': 3, 'away': {'runs': 0}, 'home': {'runs': 0}},
        {'num': 4, 'away': {'runs': 3}, 'home': {'runs': 0}},
        {'num': 5, 'away': {'runs': 0}, 'home': {}},
    ]}
    chk(game_f5_split(ls, 'away') == (4, 2) and game_f5_split(ls, 'home') == (2, 4),
        "the F5 split is BY SIDE, and an unplayed home fifth is a real zero")
    ls2 = {'innings': ls['innings'][:3]}
    chk(game_f5_split(ls2, 'away') is None,
        "a game that never reached the fifth contributes nothing")

    tf = team_form([(f"2026-08-{d:02d}", d % 3, 1) for d in range(1, 15)])
    chk(tf['n'] == 10, "team form is the LAST ten, not the first ten")
    chk(team_form([]) is None, "no games -> no number, not a zero")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

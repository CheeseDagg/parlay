#!/usr/bin/env python3
"""
socph2h.py -- PLAYER head-to-head records: who scores against whom.

Ryan asked for player props in head-to-head five times. The first four answers
were explanations of why it could not be done, which is not an answer. The fifth
question was "you can't look at box scores?" and that was the right question.

EVERY SOURCE I PROBED WAS INDEXED BY PLAYER, and they are all dead ends. Kept
here so nobody re-walks them -- which is exactly what I did, three runner round
trips rediscovering findings already written in socplayers.py:

  fbref                     403 to the runner
  sofascore                 403
  fotmob                    404
  understat player pages    served with NO embedded JSON at all: 19KB, right
                            title, zero data blocks, and core.js contains no
                            reference to /main/, getPlayer*, ajax or $.post
  understat /main/ routes    12 of 13 are 404; getPlayerMatches is real and
                            answers {"success":true,"matches":[]} for every
                            parameter shape tried -- a live route serving nothing
  ESPN site.api summary     403 to the runner
  openfootball              scorers for ONE season only (0 goal events in every
                            file 2019-20..2024-25), and one season is two
                            meetings per pair

A BOX SCORE IS INDEXED BY MATCH. Walk the fixtures, read who scored in each, and
the player histories fall out of the pile. One such archive has been on
raw.githubusercontent.com the whole time -- a host reachable from the dev
container, so this needs no runner at all:

  vaastav/Fantasy-Premier-League  data/<season>/gws/merged_gw.csv

Every player, every fixture: goals_scored, opponent_team, was_home,
kickoff_time, minutes, starts. ~11,500 appearances a season, and seven seasons
carry both that file and the teams.csv needed to read it. A pair meets twice a
season, so seven seasons is up to fourteen meetings.

It also carries minutes and starts, which nothing else did. That makes the
denominator a real appearance record instead of the club's fixture list, so the
sentence says "scored in 5 of HIS 6" and means it. openfootball can only ever
say "of the club's last 6", because a goal feed knows who scored and not who
played.

Premier League only. That is a real limit, stated rather than hidden, and it is
also the biggest player-prop market by a wide margin.
"""
import datetime as dt, gzip, json, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'socph2h.json')
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MIN_MEET = 3          # meetings before a head-to-head record is a record
MIN_HITS = 2          # scored in at least this many of them


def http(url, post=None, referer=None, timeout=40):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'}
    if referer:
        h['Referer'] = referer
    if post is not None:
        h['X-Requested-With'] = 'XMLHttpRequest'
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    b = urllib.request.urlopen(urllib.request.Request(url, data=post, headers=h),
                               timeout=timeout).read()
    if b[:2] == b'\x1f\x8b':
        b = gzip.decompress(b)
    return b.decode('utf-8', 'replace')


# THE FPL PER-MATCH ARCHIVE. Ryan asked why I could not look at box scores, and
# he was right that the axis was wrong. Everything I had probed was indexed BY
# PLAYER -- fbref player pages, understat's getPlayerMatches, sofascore, fotmob,
# all rejected and all already written down in socplayers.py. ESPN's summary API
# 403s the runner too. A box score is indexed BY MATCH, and one has been sitting
# on raw.githubusercontent.com the whole time, which is a host this container can
# reach without a runner at all:
#
#   vaastav/Fantasy-Premier-League  data/<season>/gws/merged_gw.csv
#
# Every player, every fixture, with goals_scored, opponent_team, was_home,
# kickoff_time, minutes and starts. 29,757 rows for 2025-26 alone, and EIGHT
# seasons carry both that file and the teams.csv needed to read it -- 2019-20
# through 2026-27. A pair meets twice a season, so eight seasons is up to sixteen
# meetings: head-to-head with something actually in it.
#
# It also carries `starts` and `minutes`, which no other source did. That makes
# the denominator a genuine appearance record rather than the club's fixture
# list, so the sentence can say "his", and it opens the one signal Ryan named
# that nothing could answer before: scored as a STARTER.
#
# Premier League only. That is a real limit and it is stated rather than hidden;
# it is also the biggest prop market by a distance.
FPL = ('https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/'
       'master/data/{season}/{path}')
# 2019-20 AND EARLIER ARE EXCLUDED ON PURPOSE. Those files have no `team`
# column and no `starts`, and their `name` is written "Aaron_Cresswell_376"
# rather than "Aaron Cresswell" -- so a player would not join to himself across
# the boundary and one real record would become two thin ones. Ingesting half of
# it silently dropped 22,560 rows and reported them only as "unmapped"; naming
# the reason is better than a number nobody can act on. Seven seasons is up to
# fourteen meetings per pair, which is more than the floor needs.
FPL_SEASONS = ['2026-27', '2025-26', '2024-25', '2023-24',
               '2022-23', '2021-22', '2020-21']
FPL_LEAGUE = 'England Premier League'


def fpl_csv(season, path, fetch=None):
    fetch = fetch or (lambda u: http(u))
    import csv, io
    txt = fetch(FPL.format(season=season, path=path))
    return list(csv.DictReader(io.StringIO(txt)))


def fpl_season(season, fetch=None):
    """[(date, own_team, opponent, goals, venue, started, minutes)] for a season.

    THE OPPONENT IS A NUMERIC ID AND THE IDS ARE PER-SEASON. FPL numbers the
    twenty clubs alphabetically within each season, so 20 is Wolves in 2025-26
    and something else the year Wolves were not in the division. Mapping with one
    global table would file records against the wrong club in every season but
    one -- the exact failure the club-matching work in socplayers kept producing.
    So teams.csv is read per season, and a season without one is skipped rather
    than guessed (2016-17 through 2018-19 have no teams.csv).
    """
    teams = {r['id']: r['name'] for r in fpl_csv(season, 'teams.csv', fetch)
             if r.get('id') and r.get('name')}
    if len(teams) < 10:
        return [], f'{season}: teams.csv carried {len(teams)} clubs -- refusing to map'
    out, unmapped = [], 0
    for r in fpl_csv(season, 'gws/merged_gw.csv', fetch):
        opp = teams.get((r.get('opponent_team') or '').strip())
        own, ko = (r.get('team') or '').strip(), (r.get('kickoff_time') or '')[:10]
        if not (opp and own and ko):
            unmapped += 1
            continue
        try:
            goals, mins = int(r.get('goals_scored') or 0), int(r.get('minutes') or 0)
            started = (r.get('starts') or '0').strip() in ('1', 'True', 'true')
        except (TypeError, ValueError):
            unmapped += 1
            continue
        # A player who did not come on was not in the match. Counting him would
        # put zeroes in a denominator that is supposed to mean appearances.
        if mins <= 0:
            continue
        out.append((ko, own, opp, goals, 'home' if (r.get('was_home') or '').strip()
                    in ('True', 'true', '1') else 'away', started, mins,
                    (r.get('name') or '').strip()))
    out.sort()
    note = f'{season}: {len(out)} appearances, {len(teams)} clubs'
    if unmapped:
        note += f', {unmapped} rows unmapped'
    return out, note


def mirror_check(rows):
    """Does every fixture appear from BOTH clubs' sides?

    The opponent is a per-season numeric id, and a wrong mapping is the one
    error that would silently file every record against the wrong club. This
    catches it without comparing club NAMES across sources -- which is where
    this kind of check has gone wrong every previous time.

    The archive lists one row per player per match, so a fixture appears once
    for each side. If (date, A, B) exists then (date, B, A) must too. Under a
    broken mapping A's opponent and B's opponent disagree and the mirrors stop
    lining up, which shows as a mismatch rate rather than as a strange row
    somebody happens to notice.

    Returns (matched, orphaned) fixture counts.
    """
    fixtures = {(d, own, opp) for d, own, opp, _g, _v, _s, _m, _n in rows}
    matched = sum(1 for d, a, b in fixtures if (d, b, a) in fixtures)
    return matched, len(fixtures) - matched


def h2h_from_fpl(rows, min_meet=MIN_MEET, min_hits=MIN_HITS):
    """Player head-to-head out of the per-match archive.

    KEYED ON THE PLAYER, NOT ON PLAYER-AND-CLUB. "scored in 4 of his 6 against
    Wolves" is a fact about him and them; splitting it by the shirt he wore
    would turn one real record into two thin ones every time somebody
    transferred. The club shown beside his name is the one from his LATEST
    appearance, so the row says where he is now.

    The denominator is his own appearances -- rows where he actually played,
    filtered upstream on minutes. That is what this archive adds over every
    other source tried: openfootball knows who scored and not who played, so
    socplayers has to say "of the club's last 6". Here it can say "his".
    """
    by_player = defaultdict(list)
    for date, own, opp, goals, venue, started, _mins, name in rows:
        if name:
            by_player[name].append((date, own, opp, goals, venue, started))
    out = []
    for name, apps in by_player.items():
        apps.sort()
        club = apps[-1][1]
        by_opp = defaultdict(list)
        for date, _own, opp, goals, venue, started in apps:
            by_opp[opp].append((date, goals, venue, started))
        for opp, met in by_opp.items():
            if len(met) < min_meet:
                continue
            met.sort()
            hits = sum(1 for _d, g, _v, _s in met if g)
            goals = sum(g for _d, g, _v, _s in met)
            if hits < min_hits or hits / len(met) < 0.5:
                continue
            text = (f'scored in all {len(met)} of his meetings with {opp}'
                    if hits == len(met) else
                    f'scored in {hits} of his {len(met)} against {opp}')
            if goals > hits:
                text += f' — {goals} goals'
            starts = sum(1 for _d, _g, _v, st in met if st)
            row = {'player': name, 'team': club, 'league': FPL_LEAGUE,
                   'category': 'Head-to-head', 'split': 'h2h', 'opp': opp,
                   'text': text, 'hits': hits, 'n': len(met), 'goals': goals,
                   'starts': starts,
                   'span': f'{met[0][0][:7]} to {met[-1][0][:7]}',
                   'source': 'FPL per-match appearances',
                   'evidence': [{'date': d, 'opp': opp, 'goals': g, 'venue': v}
                                for d, g, v, _s in met if g][::-1][:6]}
            out.append(row)
    out.sort(key=lambda r: (-(r['hits'] / r['n']), -r['goals'], -r['n']))
    return out


def build_fpl(seasons=None, fetch=None):
    rows, report = [], []
    for season in (seasons or FPL_SEASONS):
        try:
            got, note = fpl_season(season, fetch=fetch)
        except Exception as e:
            report.append(f'  {season}: FAILED {type(e).__name__}')
            continue
        report.append('  ' + note)
        rows.extend(got)
    if not rows:
        return {'h2h': [], 'report': report + ['  no seasons read -- nothing built']}
    matched, orphaned = mirror_check(rows)
    rate = matched / (matched + orphaned) if (matched + orphaned) else 0
    report.append(f'  mirror check: {matched} fixtures seen from both sides, '
                  f'{orphaned} from one only ({rate:.1%} paired)')
    # A wrong opponent mapping shows up here and nowhere else until it is on the
    # page. Below 90% paired, something is wrong with the ids and publishing the
    # records would mean publishing misattributions.
    if rate < 0.90:
        return {'h2h': [], 'report': report +
                ['  REFUSING to build: too many fixtures appear from one side only, '
                 'which is what a wrong opponent-id mapping looks like']}
    h2h = h2h_from_fpl(rows)
    # ONLY PLAYERS WHO ARE STILL IN THE LEAGUE. Seven seasons of history means
    # the strongest records belong to players who left years ago: the first run
    # led with Diogo Jota, Sadio Mane and Emmanuel Dennis, none of whom can
    # appear on a teamsheet this weekend. A record nobody can bet is not a
    # signal, and in Jota's case it is worse than useless.
    current = (seasons or FPL_SEASONS)[0]
    active = {n for d, _o, _p, _g, _v, _s, _m, n in rows
              if n and d[:4] >= current[:4]}
    if not active:
        report.append(f'  {current} has no appearances yet -- keeping every record '
                      f'rather than emptying the list, so some name players who '
                      f'have left')
    else:
        before = len(h2h)
        h2h = [r for r in h2h if r['player'] in active]
        report.append(f'  {before - len(h2h)} records dropped: the player has not '
                      f'appeared in {current} ({len(active)} players active)')
    report.append(f'  {len(h2h)} head-to-head records from {len(rows)} appearances')
    return {'h2h': h2h, 'report': report}


def probe():
    res = build_fpl()
    for line in res['report']:
        print(line)
    print()
    for r in res['h2h'][:20]:
        print(f"  {r['player'][:24]:24} {r['text'][:58]:58} {r['span']}")
    return 0


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    TEAMS = 'id,name\n' + '\n'.join(f'{i},Club{i}' for i in range(1, 21))

    def gw(rows):
        cols = ['name', 'team', 'opponent_team', 'was_home', 'kickoff_time',
                'goals_scored', 'minutes', 'starts']
        out = [','.join(cols)]
        for r in rows:
            out.append(','.join(str(r.get(c, '')) for c in cols))
        return '\n'.join(out)

    ROWS = [
        {'name': 'A Striker', 'team': 'Club1', 'opponent_team': 20, 'was_home': 'True',
         'kickoff_time': '2025-08-16T14:00:00Z', 'goals_scored': 2, 'minutes': 90, 'starts': 1},
        {'name': 'B Sub', 'team': 'Club1', 'opponent_team': 20, 'was_home': 'True',
         'kickoff_time': '2025-08-16T14:00:00Z', 'goals_scored': 0, 'minutes': 0, 'starts': 0},
        {'name': 'C Keeper', 'team': 'Club20', 'opponent_team': 1, 'was_home': 'False',
         'kickoff_time': '2025-08-16T14:00:00Z', 'goals_scored': 0, 'minutes': 90, 'starts': 1},
    ]

    def fetch(url):
        return TEAMS if url.endswith('teams.csv') else gw(ROWS)

    got, note = fpl_season('2025-26', fetch=fetch)
    chk(len(got) == 2, f'a player with zero minutes was not in the match: {note}')
    chk(got[0][2] == 'Club20' or got[1][2] == 'Club20',
        'the numeric opponent id is mapped through THAT season\'s teams.csv')
    chk(all(r[1] != r[2] for r in got),
        'nobody is recorded as playing against his own club')
    thin, tnote = fpl_season('2025-26',
                             fetch=lambda u: ('id,name\n1,Only' if u.endswith('teams.csv')
                                              else gw(ROWS)))
    chk(thin == [] and 'refusing to map' in tnote,
        'a teams.csv too small to be a division is refused, not partially applied')

    # THE MIRROR CHECK is the only thing standing between a wrong per-season id
    # map and a page full of records filed against the wrong clubs.
    good = [('2025-08-16', 'A', 'B', 0, 'home', True, 90, 'p'),
            ('2025-08-16', 'B', 'A', 0, 'away', True, 90, 'q')]
    chk(mirror_check(good) == (2, 0), 'a fixture seen from both sides is paired')
    chk(mirror_check(good[:1]) == (0, 1),
        'a fixture seen from one side only is counted as orphaned')

    # h2h: keyed on the PLAYER across a transfer, club shown is the latest.
    apps = []
    for i, (d, own, opp, g) in enumerate([
            ('2023-09-01', 'Old', 'Rival', 1), ('2024-02-01', 'Old', 'Rival', 2),
            ('2024-09-01', 'New', 'Rival', 1), ('2025-02-01', 'New', 'Rival', 0),
            ('2025-09-01', 'New', 'Other', 1), ('2026-02-01', 'New', 'Other', 1)]):
        apps.append((d, own, opp, g, 'home', True, 90, 'Mover'))
    h = h2h_from_fpl(apps)
    riv = [r for r in h if r['opp'] == 'Rival']
    chk(len(riv) == 1 and riv[0]['n'] == 4,
        'a transfer does not split one head-to-head record into two thin ones')
    chk(riv[0]['team'] == 'New',
        'the club beside his name is the one from his LATEST appearance')
    chk(riv[0]['text'] == 'scored in 3 of his 4 against Rival — 4 goals',
        f"the denominator is HIS appearances, not the club's: {riv[0]['text']!r}")
    chk(riv[0]['span'] == '2023-09 to 2025-02',
        'the span crosses seasons, which is the whole reason this source was used')
    chk(not [r for r in h if r['opp'] == 'Other'],
        'two meetings is not a head-to-head record even when he scored in both')

    # build_fpl: the mirror gate, and the active-player filter.
    def seasons_fetch(rows_by_season):
        def f(url):
            season = url.split('/data/')[1].split('/')[0]
            if url.endswith('teams.csv'):
                return TEAMS
            return gw(rows_by_season.get(season, []))
        return f

    BROKEN = [{'name': 'X', 'team': 'Club1', 'opponent_team': 20, 'was_home': 'True',
               'kickoff_time': '2025-08-16T14:00:00Z', 'goals_scored': 1,
               'minutes': 90, 'starts': 1}]
    b = build_fpl(seasons=['2025-26'], fetch=seasons_fetch({'2025-26': BROKEN}))
    chk(b['h2h'] == [] and any('REFUSING' in l for l in b['report']),
        'fixtures that appear from one side only stop the build -- that is what a '
        'wrong opponent-id map looks like')

    PAIR = []
    for d in ('2024-09-01', '2025-02-01', '2025-09-01'):
        PAIR += [{'name': 'Live Guy', 'team': 'Club1', 'opponent_team': 20,
                  'was_home': 'True', 'kickoff_time': d + 'T14:00:00Z',
                  'goals_scored': 1, 'minutes': 90, 'starts': 1},
                 {'name': 'Gone Guy', 'team': 'Club20', 'opponent_team': 1,
                  'was_home': 'False', 'kickoff_time': d + 'T14:00:00Z',
                  'goals_scored': 1, 'minutes': 90, 'starts': 1}]
    NOW = [{'name': 'Live Guy', 'team': 'Club1', 'opponent_team': 5,
            'was_home': 'True', 'kickoff_time': '2026-08-16T14:00:00Z',
            'goals_scored': 0, 'minutes': 90, 'starts': 1},
           {'name': 'Someone', 'team': 'Club5', 'opponent_team': 1,
            'was_home': 'False', 'kickoff_time': '2026-08-16T14:00:00Z',
            'goals_scored': 0, 'minutes': 90, 'starts': 1}]
    b2 = build_fpl(seasons=['2026-27', '2025-26'],
                   fetch=seasons_fetch({'2026-27': NOW, '2025-26': PAIR}))
    names = {r['player'] for r in b2['h2h']}
    chk('Live Guy' in names,
        'a player who appears in the current season keeps his record')
    chk('Gone Guy' not in names,
        'a player who has left the league does NOT -- the first run led with '
        'records belonging to players who cannot be on a teamsheet')
    chk(any('has not appeared in 2026-27' in l for l in b2['report']),
        'and the drop is reported rather than being a silent shrink')
    b3 = build_fpl(seasons=['2026-27', '2025-26'],
                   fetch=seasons_fetch({'2026-27': [], '2025-26': PAIR}))
    chk(b3['h2h'] and any('no appearances yet' in l for l in b3['report']),
        'an empty current season keeps every record and says so, rather than '
        'emptying the list in August')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


def main():
    res = build_fpl()
    print('socph2h')
    for line in res['report']:
        print(line)
    json.dump({'h2h': res['h2h']}, open(OUT, 'w'), ensure_ascii=False,
              separators=(',', ':'))
    print(f"\nwrote {OUT} -- {len(res['h2h'])} player head-to-head records")
    for r in res['h2h'][:16]:
        print(f"  {r['player'][:24]:24} {r['text'][:58]:58} {r['span']}")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv
             else probe() if '--probe' in sys.argv else main())

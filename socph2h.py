#!/usr/bin/env python3
"""
socph2h.py -- PLAYER head-to-head records, the thing socplayers could not do.

WHY THIS FILE EXISTS. socplayers builds player splits from openfootball's
per-match goal feed, and that feed carries scorers for ONE season only -- a
sweep of 2019-20 through 2024-25 across all four leagues found 0 scorer blocks
in every file, and only 2025-26 has them. Inside one season two clubs meet
exactly twice, which is below any honest head-to-head floor, so the head-to-head
list had nothing in it and said so. Ryan asked for player props in head-to-head
five times and got that explanation five times, which is not an answer.

understat is the source that answers it. Its PLAYER pages carry a matchesData
block: every match that player has appeared in, across every season understat
covers, with goals, date, both team names and which side he was on. That is
exactly a head-to-head record, and it spans seasons rather than one.

    https://understat.com/player/{id}   ->  var matchesData = JSON.parse('...')

The season-totals POST route already used by socplayers supplies the player ids,
so nothing new has to be discovered to enumerate them.

COST CONTROL. One page per player, and a league has ~450 of them. Fetching all
of them four times over is both slow and rude, so only players who could carry a
prop are fetched: ranked by goals this season, capped per league. The cap is
reported so a thin run is visible rather than looking like a quiet source.
"""
import datetime as dt, gzip, json, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'socph2h.json')
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
POST = 'https://understat.com/main/getPlayersStats/'
PLAYER = 'https://understat.com/player/{pid}'
LEAGUES = {'EPL': 'England Premier League', 'La_liga': 'Spain La Liga',
           'Bundesliga': 'Germany Bundesliga', 'Serie_A': 'Italy Serie A'}
SEASON = '2026'

PER_LEAGUE = 45       # players fetched per league, by goals scored this season
MIN_MEET = 3          # meetings before a head-to-head record is a record
MIN_HITS = 2          # scored in at least this many of them
SLEEP = 0.4           # between player pages


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


def season_players(league, season=SEASON):
    body = urllib.parse.urlencode({'league': league, 'season': season}).encode()
    d = json.loads(http(POST, post=body,
                        referer=f'https://understat.com/league/{league}/{season}'))
    return (d.get('response') or {}).get('players') or d.get('players') or []


def embedded(html, name):
    """Pull one `var <name> = JSON.parse('...')` block out of an understat page.

    understat hex-escapes the payload (\\x7B for '{'), so the captured string is
    decoded as a unicode-escape before it is valid JSON. Returning None rather
    than raising keeps one reshaped page from taking the whole run down -- the
    caller counts the misses.
    """
    m = re.search(name + r"\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)*)'\)", html)
    if not m:
        return None
    try:
        return json.loads(m.group(1).encode().decode('unicode_escape'))
    except Exception:
        return None


def player_matches(pid, fetch=None):
    """[(date, own_team, opponent, goals, venue)] oldest first, all seasons."""
    fetch = fetch or (lambda u: http(u, referer='https://understat.com/'))
    data = embedded(fetch(PLAYER.format(pid=pid)), 'matchesData')
    if not data:
        return None
    out = []
    for r in data:
        try:
            h, a = r.get('h_team'), r.get('a_team')
            date = (r.get('date') or '')[:10]
            goals = int(r.get('goals') or 0)
            # understat marks the side the player was on. Fall back to nothing
            # rather than guessing: a wrong side inverts the opponent and files
            # the record against the wrong club.
            side = r.get('h_a') or r.get('side')
            if not (h and a and date and side in ('h', 'a')):
                continue
            own, opp = (h, a) if side == 'h' else (a, h)
            out.append((date, own, opp, goals, 'home' if side == 'h' else 'away'))
        except (TypeError, ValueError):
            continue
    out.sort()
    return out


def h2h_signals(name, team, rows, min_meet=MIN_MEET, min_hits=MIN_HITS):
    """'scored in 4 of his 6 against X' -- and here the denominator is HIS.

    This is the one place a player denominator is honest. openfootball knows who
    scored and not who played, so socplayers has to say "of the club's last 6".
    understat's matchesData is an APPEARANCE record: every row is a match he was
    actually in. So the sentence can say "his", and the count means what it says.
    """
    by_opp = defaultdict(list)
    for date, _own, opp, goals, venue in rows:
        by_opp[opp].append((date, goals, venue))
    out = []
    for opp, met in by_opp.items():
        if len(met) < min_meet:
            continue
        hits = sum(1 for _d, g, _v in met if g)
        goals = sum(g for _d, g, _v in met)
        if hits < min_hits or hits / len(met) < 0.5:
            continue
        met.sort()
        span = f'{met[0][0][:7]} to {met[-1][0][:7]}'
        text = (f'scored in all {len(met)} of his meetings with {opp}'
                if hits == len(met) else
                f'scored in {hits} of his {len(met)} against {opp}')
        if goals > hits:
            text += f' — {goals} goals'
        out.append({'player': name, 'team': team, 'category': 'Head-to-head',
                    'split': 'h2h', 'opp': opp, 'text': text,
                    'hits': hits, 'n': len(met), 'goals': goals, 'span': span,
                    'source': 'understat per-match appearances',
                    'evidence': [{'date': d, 'opp': opp, 'goals': g, 'venue': v}
                                 for d, g, v in met if g][::-1][:6]})
    out.sort(key=lambda r: (-(r['hits'] / r['n']), -r['goals'], -r['n']))
    return out


def build(season=SEASON, per_league=PER_LEAGUE, sleep=SLEEP,
          list_fetch=None, page_fetch=None):
    list_fetch = list_fetch or (lambda lg: season_players(lg, season))
    report, rows, misses = [], [], 0
    for slug, label in LEAGUES.items():
        try:
            players = list_fetch(slug)
        except Exception as e:
            report.append(f'  {label}: player list failed ({type(e).__name__})')
            continue

        def goals_of(p):
            try:
                return int(p.get('goals') or 0)
            except (TypeError, ValueError):
                return 0

        ranked = sorted(players, key=goals_of, reverse=True)[:per_league]
        got = 0
        for p in ranked:
            pid = p.get('id') or p.get('player_id')
            name = p.get('player_name')
            if not pid or not name:
                continue
            try:
                ms = player_matches(pid, fetch=page_fetch)
            except Exception:
                ms = None
            if not ms:
                misses += 1
                if sleep:
                    time.sleep(sleep)
                continue
            # The club to name is the one he plays for NOW, which is the club on
            # his most recent appearance -- not the season-totals team_title,
            # which is a season aggregate and lags a January move.
            team = ms[-1][1]
            sig = h2h_signals(name, team, ms)
            for r in sig:
                r['league'] = label
            rows.extend(sig)
            got += 1
            if sleep:
                time.sleep(sleep)
        seasons = sorted({m[0][:4] for p in () for m in ()})   # filled below
        report.append(f'  {label}: {got}/{len(ranked)} player pages read '
                      f'(of {len(players)} in the league), '
                      f'{sum(1 for r in rows if r.get("league") == label)} records')
    rows.sort(key=lambda r: (-(r['hits'] / r['n']), -r['goals'], -r['n']))
    if misses:
        report.append(f'  {misses} player pages carried no matchesData '
                      f'-- reshaped or empty, counted not swallowed')
    return {'h2h': rows, 'report': report}


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    # understat hex-escapes its embedded JSON.
    page = ("junk var matchesData = JSON.parse('[\\x7B\\x22goals\\x22:\\x222\\x22,"
            "\\x22date\\x22:\\x222026-03-01\\x22,\\x22h_team\\x22:\\x22Arsenal\\x22,"
            "\\x22a_team\\x22:\\x22Chelsea\\x22,\\x22h_a\\x22:\\x22h\\x22\\x7D]') more")
    d = embedded(page, 'matchesData')
    chk(d and d[0]['h_team'] == 'Arsenal' and d[0]['goals'] == '2',
        'the hex-escaped matchesData block decodes to JSON')
    chk(embedded('nothing here', 'matchesData') is None,
        'a page without the block returns None rather than raising')
    chk(embedded("var matchesData = JSON.parse('not json')", 'matchesData') is None,
        'and a block that is not JSON returns None too')

    ROWS = [
        {'date': '2024-09-01', 'h_team': 'Arsenal', 'a_team': 'Wolves', 'h_a': 'h', 'goals': '1'},
        {'date': '2025-02-01', 'h_team': 'Wolves', 'a_team': 'Arsenal', 'h_a': 'a', 'goals': '2'},
        {'date': '2025-09-01', 'h_team': 'Arsenal', 'a_team': 'Wolves', 'h_a': 'h', 'goals': '0'},
        {'date': '2026-02-01', 'h_team': 'Wolves', 'a_team': 'Arsenal', 'h_a': 'a', 'goals': '1'},
        {'date': '2026-03-01', 'h_team': 'Arsenal', 'a_team': 'Spurs', 'h_a': 'h', 'goals': '3'},
        {'date': '2026-04-01', 'h_team': 'Spurs', 'a_team': 'Arsenal', 'h_a': 'a', 'goals': '0'},
    ]
    esc = json.dumps(ROWS).replace('{', '\\x7B').replace('}', '\\x7D')
    fake = f"var matchesData = JSON.parse('{esc}')"
    ms = player_matches('1', fetch=lambda u: fake)
    chk(len(ms) == 6 and ms[0][0] == '2024-09-01',
        'player matches come back oldest first')
    chk(ms[0][1] == 'Arsenal' and ms[0][2] == 'Wolves' and ms[0][4] == 'home',
        'a home row names his club and the opponent the right way round')
    chk(ms[1][1] == 'Arsenal' and ms[1][2] == 'Wolves' and ms[1][4] == 'away',
        'and an away row does NOT invert them -- that would file the record '
        'against his own club')
    # Build the broken variant from the data, not by string-replacing the
    # escaped page: the first version's replace pattern did not match anything,
    # so the check passed while testing nothing at all.
    def page_of(rows):
        e = json.dumps(rows).replace('{', '\\x7B').replace('}', '\\x7D')
        return f"var matchesData = JSON.parse('{e}')"
    sideless = [dict(r, h_a='?') if r['h_a'] == 'a' else dict(r) for r in ROWS]
    half = player_matches('1', fetch=lambda u: page_of(sideless))
    chk(len(half) == 3 and all(m[4] == 'home' for m in half),
        'a row with no usable side is dropped, never guessed')
    noteam = player_matches('1', fetch=lambda u: page_of(
        [dict(r, a_team=None) for r in ROWS]))
    chk(noteam == [], 'a row missing a team name is dropped as well')

    sig = h2h_signals('P', 'Arsenal', ms)
    wolves = [r for r in sig if r['opp'] == 'Wolves']
    chk(len(wolves) == 1, 'an opponent met four times is eligible')
    chk(wolves[0]['text'] == 'scored in 3 of his 4 against Wolves — 4 goals',
        f"the sentence says HIS four, not the club's: {wolves[0]['text']!r}")
    chk('2024-09 to 2026-02' == wolves[0]['span'],
        'and it carries the span, which crosses seasons -- the whole point')
    chk(not [r for r in sig if r['opp'] == 'Spurs'],
        'an opponent met twice is below the floor, however many goals were in it')
    chk(wolves[0]['source'] == 'understat per-match appearances',
        'the source names an APPEARANCE record, which is why "his" is honest')
    chk(len(wolves[0]['evidence']) == 3,
        'evidence lists only the meetings he actually scored in')

    # A 2-FROM-2 IS THE SHAPE TO REFUSE. The Spurs pair above is blocked by the
    # hits floor rather than the meeting floor, so it does not test the meeting
    # floor at all -- this pair is perfect and must still be refused, the same
    # rule the club head-to-head already follows.
    two = [('2025-09-01', 'A', 'B', 1, 'home'), ('2026-02-01', 'A', 'B', 2, 'away')]
    chk(not h2h_signals('R', 'A', two),
        'two meetings is not a head-to-head record even when he scored in both')

    quiet = [('2025-01-01', 'A', 'B', 0, 'home'), ('2025-06-01', 'A', 'B', 0, 'away'),
             ('2026-01-01', 'A', 'B', 0, 'home'), ('2026-06-01', 'A', 'B', 1, 'away')]
    chk(not h2h_signals('Q', 'A', quiet),
        'one goal in four meetings is not a head-to-head record')

    # build(): the club named is the CURRENT one, not the season aggregate
    B = build(per_league=2, sleep=0,
              list_fetch=lambda lg: ([{'id': '9', 'player_name': 'Mover',
                                       'team_title': 'Old Club', 'goals': '9'}]
                                     if lg == 'EPL' else []),
              page_fetch=lambda u: fake)
    chk(B['h2h'] and B['h2h'][0]['team'] == 'Arsenal',
        "the club on the row is the one from his latest appearance, not the "
        "season-totals team_title that lags a January move")
    chk(any('player pages read' in l for l in B['report']),
        'the report states how many pages were actually read')
    B2 = build(per_league=2, sleep=0,
               list_fetch=lambda lg: ([{'id': '9', 'player_name': 'X', 'goals': '1'}]
                                      if lg == 'EPL' else []),
               page_fetch=lambda u: 'no block here')
    chk(not B2['h2h'] and any('no matchesData' in l for l in B2['report']),
        'pages with no data are COUNTED in the report, not silently dropped')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


# ESPN'S BOX SCORES. Ryan's question -- "you can't look at box scores?" -- is
# the right axis and I had the wrong one. Every source I probed was indexed BY
# PLAYER: fbref player pages, understat's getPlayerMatches, sofascore, fotmob.
# All rejected, and the rejection is recorded in socplayers.py so nobody
# re-walks it, which I then re-walked three times.
#
# A box score is indexed BY MATCH. Walk the fixtures, read who scored in each,
# and the player histories fall out of the pile. It is the same shape
# openfootball already provides for one season -- there is just no reason the
# only source of that shape has to be openfootball.
#
# nethunt.py already establishes that site.api.espn.com answers from the runner
# and that its scoreboard parses as JSON with an `events` list. What it never
# asked is whether the SUMMARY endpoint carries scorers. That is this probe.
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/{path}'
ESPN_LEAGUES = {'eng.1': 'England Premier League', 'esp.1': 'Spain La Liga',
                'ger.1': 'Germany Bundesliga', 'ita.1': 'Italy Serie A'}


def espn(lg, path, **q):
    url = ESPN.format(lg=lg, path=path)
    if q:
        url += '?' + urllib.parse.urlencode(q)
    return json.loads(http(url, referer='https://www.espn.com/'))


def probe():
    """Does ESPN's summary endpoint name the scorers, and how far back?"""
    lg = 'eng.1'
    # A date in the middle of last season, so the fixtures are finished.
    for dates in ('20260214-20260216', '20250214-20250216', '20230214-20230216',
                  '20190214-20190216'):
        try:
            d = espn(lg, 'scoreboard', dates=dates)
        except Exception as e:
            print(f'  scoreboard {dates}: ERR {type(e).__name__} '
                  f'{getattr(e, "code", "")}')
            continue
        evs = d.get('events') or []
        print(f'  scoreboard {dates}: {len(evs)} events')
        for e in evs[:2]:
            print(f"      {e.get('id')}  {e.get('date','')[:10]}  {e.get('name')}")
    print()

    d = espn(lg, 'scoreboard', dates='20260214-20260216')
    evs = d.get('events') or []
    if not evs:
        print('no events to summarise -- stopping')
        return 1
    eid = evs[0].get('id')
    try:
        sm = espn(lg, 'summary', event=eid)
    except Exception as e:
        print(f'summary {eid}: ERR {type(e).__name__} {getattr(e, "code", "")}')
        return 1
    print(f'summary {eid}: top-level keys {sorted(sm.keys())}')

    # Which of these carries "who scored"? Report each candidate's shape.
    for k in ('scoringPlays', 'keyEvents', 'plays', 'boxscore', 'rosters',
              'header', 'commentary'):
        v = sm.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            print(f'  {k}: [{len(v)}]' + (f' first keys {sorted(v[0].keys())[:12]}'
                                          if v and isinstance(v[0], dict) else ''))
        elif isinstance(v, dict):
            print(f'  {k}: {{{",".join(sorted(v.keys())[:10])}}}')

    for sp in (sm.get('scoringPlays') or [])[:4]:
        who = (sp.get('athletesInvolved') or [{}])
        print(f"    scoringPlay: {sp.get('clock', {}).get('displayValue')} "
              f"{(sp.get('team') or {}).get('displayName')} "
              f"{[a.get('displayName') for a in who]} "
              f"type={(sp.get('type') or {}).get('text')}")

    ros = sm.get('rosters') or []
    if ros:
        print(f'  rosters: {len(ros)} teams')
        t0 = ros[0]
        print(f"    team {(t0.get('team') or {}).get('displayName')} "
              f"keys {sorted(t0.keys())}")
        pl = (t0.get('roster') or [])[:1]
        if pl:
            print(f'    a roster entry: {sorted(pl[0].keys())[:14]}')
            st = pl[0].get('stats')
            if isinstance(st, list) and st:
                print(f'      stats sample: {st[:6]}')
    return 0


def main():
    res = build()
    print('socph2h')
    for line in res['report']:
        print(line)
    json.dump({'h2h': res['h2h']}, open(OUT, 'w'), ensure_ascii=False,
              separators=(',', ':'))
    print(f"\nwrote {OUT} -- {len(res['h2h'])} player head-to-head records")
    for r in res['h2h'][:14]:
        print(f"  {r['player'][:22]:22} {r['text'][:62]:62} {r['span']}")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv
             else probe() if '--probe' in sys.argv else main())

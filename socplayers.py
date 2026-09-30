#!/usr/bin/env python3
"""socplayers.py — player signals, from the two sources that actually answer.

    python3 socplayers.py            # runner only (understat is egress-blocked here)
    python3 socplayers.py --selftest

TWO SOURCES BECAUSE NEITHER ALONE IS ENOUGH, and the split is the whole
point of the file:

  understat getPlayersStats   CURRENT season, every player, but SEASON TOTALS.
                              Knows Haaland has 5 goals in 5 games. Does not
                              know which five games. Good for rates.
  openfootball .txt           Named scorers with minutes, PER MATCH -- the only
                              shape that can say "scored in 5 of last 6". But
                              scorers are backfilled AFTER a season: the
                              2025-26 file carries 519 goal events, the live
                              2026-27 file carries zero.

So rate signals are live today and streak signals appear the moment
openfootball backfills the running season. Until then this reports that they
are absent rather than quietly serving last season's under a "last 6" label --
which is the Colombia stale-form trap with a player's name on it.

WHAT WAS PROBED AND REJECTED (srcprobe rounds 12-16, so nobody re-walks it):
fbref 403, sofascore 403, fotmob 404. understat's per-match routes:
/main/getPlayerStats/ 404, /main/getPlayerShots/ 404, and
/main/getPlayerMatches/ answers {"success": true, "matches": []} -- the route
is real and serves nothing. understat's league PAGE is served without its
embedded JSON, so the POST route is the only way in. The long-standing note
in SoccerTool that understat Cloudflare-walls the runner is STALE: the POST
route works, which is why player_shares_pin.json could be live again.
"""
import gzip, json, math, os, re, sys, urllib.parse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'socplayers.json')
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

UNDERSTAT_POST = 'https://understat.com/main/getPlayersStats/'
UNDERSTAT_LEAGUES = {'EPL': 'England Premier League', 'La_liga': 'Spain La Liga',
                     'Bundesliga': 'Germany Bundesliga', 'Serie_A': 'Italy Serie A'}
SEASON = '2026'

OF = 'https://raw.githubusercontent.com/openfootball/{repo}/master/{yr}/{file}'
OF_LEAGUES = {
    'England Premier League': ('england', '1-premierleague.txt'),
    'Spain La Liga':          ('espana', '1-liga.txt'),
    'Germany Bundesliga':     ('deutschland', '1-bundesliga.txt'),
    'Italy Serie A':          ('italy', '1-seriea.txt'),
}
OF_YEARS = ['2026-27', '2025-26']

WINDOW = 6           # "of last 6" -- a player's recent run
MIN_PLAYED = 4
MAX_AGE_DAYS = 45    # a streak older than this is last season's, not form

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}

DATE_LINE = re.compile(r'^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+'
                       r'(\d{1,2})(?:\s+(\d{4}))?\s*$')
MATCH_LINE = re.compile(r'^\s*(?:\d{1,2}:\d{2})?\s+(.+?)\s+(\d{1,2})-(\d{1,2})\s*'
                        r'\(\d{1,2}-\d{1,2}\)\s*(.+?)\s*$')
MINUTE = re.compile(r"(\d{1,3}(?:\+\d{1,2})?)'")


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


# --------------------------------------------------------------- openfootball
def split_scorers(chunk):
    """'Hugo EKITIKE 37', Cody GAKPO 49'' -> [('Hugo EKITIKE', 1), ...]

    A player with two goals is written once with both minutes ("SEMENYO 64',
    76'"), so goals are counted from MINUTE MARKERS, not from commas. Own
    goals are dropped: an (og) is not the scorer scoring, and crediting it
    would put a defender on a goalscorer streak.
    """
    out = []
    for part in chunk.split(','):
        part = part.strip()
        if not part:
            continue
        mins = MINUTE.findall(part)
        name = MINUTE.split(part)[0].strip(" ,;()")
        name = re.sub(r'\((?:p|pen|og)\)', '', name, flags=re.I).strip()
        if not mins:
            # a bare continuation like "76'" belongs to the previous scorer
            continue
        if re.search(r'\bog\b|\(og\)', part, re.I):
            continue
        if name:
            out.append((name, len(mins)))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + len(mins))
    return out


def parse_openfootball(text, default_year=None):
    """[(date, home, away, hg, ag, [(player, goals)], [(player, goals)])]"""
    games, cur_date, pending = [], None, None
    year = default_year

    def flush(block):
        if not pending or not block:
            return
        body = ' '.join(block).strip()
        body = body.strip('()')
        h, _, a = body.partition(';')
        pending[5].extend(split_scorers(h))
        pending[6].extend(split_scorers(a))

    block = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = DATE_LINE.match(line)
        if m:
            flush(block)
            block = []
            mon, day, yr = m.group(1), int(m.group(2)), m.group(3)
            if yr:
                year = int(yr)
            if year and mon in MONTHS:
                cur_date = f'{year:04d}-{MONTHS[mon]:02d}-{day:02d}'
            continue
        if line.lstrip().startswith('(') or (block and not MATCH_LINE.match(line)):
            if line.lstrip().startswith('(') or block:
                block.append(line.strip())
                if line.rstrip().endswith(')'):
                    flush(block)
                    block = []
                continue
        m = MATCH_LINE.match(line)
        if m and cur_date:
            flush(block)
            block = []
            home, hg, ag, away = m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4).strip()
            pending = [cur_date, home, away, hg, ag, [], []]
            games.append(pending)
    flush(block)
    return [tuple(g) for g in games]


def team_matches(games):
    """{team: [(date, opp, {player: goals})]} oldest first."""
    by = defaultdict(list)
    for date, home, away, _hg, _ag, hs, as_ in games:
        by[home].append((date, away, dict(hs)))
        by[away].append((date, home, dict(as_)))
    for k in by:
        by[k].sort()
    return by


def player_matches(games):
    """{player: [(date, team, opp, goals)]} for the matches they SCORED in.

    Kept because it is the honest record of what the source knows. It cannot
    answer "in 5 of last 6" on its own -- see streak_signals."""
    by = defaultdict(list)
    for date, home, away, _hg, _ag, hs, as_ in games:
        for team, opp, scorers in ((home, away, hs), (away, home, as_)):
            for name, goals in scorers:
                by[name].append((date, team, opp, goals))
    for k in by:
        by[k].sort()
    return by


def streak_signals(games, today=None, window=WINDOW, min_hits=3):
    """'scored in N of {team}'s last M' -- and the phrasing is the honest part.

    A GOAL FEED KNOWS WHO SCORED, NOT WHO PLAYED. openfootball lists scorers;
    nothing in it says who was on the pitch. So the denominator can only be
    the TEAM's last M matches, and a blank is "did not score" OR "did not
    play" and this file cannot tell them apart. The sentence says "of
    {team}'s last 6" for exactly that reason.

    It is also why Ryan's "scored every game AS A STARTER" and "scored every
    time X is out" are NOT produced here: both need an appearance record, and
    no source reachable from this runner publishes one for a live season.
    """
    import datetime as dt
    today = today or dt.date.today()
    tm = team_matches(games)
    out, stale = [], 0
    for team, rows in tm.items():
        recent = rows[-window:]
        # Tied to min_hits, not a second hard 3: a separate literal floor here
        # silently cancelled the parameter and produced an empty result set.
        if len(recent) < min_hits:
            continue
        newest = recent[-1][0]
        try:
            age = (today - dt.date.fromisoformat(newest)).days
        except Exception:
            continue
        scorers = defaultdict(int)
        for _d, _o, gs in rows:
            for p, g in gs.items():
                scorers[p] += g
        for player in scorers:
            hits = sum(1 for _d, _o, gs in recent if gs.get(player))
            if hits < min_hits or hits / len(recent) < 0.6:
                continue
            if age > MAX_AGE_DAYS:
                stale += 1
                continue
            text = (f"scored in all of {team}'s last {len(recent)}"
                    if hits == len(recent) else
                    f"scored in {hits} of {team}'s last {len(recent)}")
            out.append({'player': player, 'team': team, 'category': 'Player',
                        'text': text, 'hits': hits, 'n': len(recent),
                        'newest': newest, 'source': 'openfootball per-match',
                        'evidence': [{'date': d, 'opp': o, 'goals': gs.get(player, 0)}
                                     for d, o, gs in recent][::-1]})
    out.sort(key=lambda r: (-(r['hits'] / r['n']), -r['n']))
    return out, stale


# ------------------------------------------------------------------ understat
def understat(league, season=SEASON):
    body = urllib.parse.urlencode({'league': league, 'season': season}).encode()
    txt = http(UNDERSTAT_POST, post=body,
               referer=f'https://understat.com/league/{league}/{season}')
    d = json.loads(txt)
    return (d.get('response') or {}).get('players') or d.get('players') or []


def rate_signals(rows, league_name, min_games=3):
    """Season-total signals: rates, never dressed as streaks.

    These CANNOT say "in 5 of last 6" -- the source does not know which games.
    Every sentence here is a rate or a total, which is what the data supports.
    """
    out = []
    for p in rows:
        try:
            g, games = int(p.get('goals', 0)), int(p.get('games', 0))
            mins, xg = int(p.get('time', 0)), float(p.get('xG', 0) or 0)
        except (TypeError, ValueError):
            continue
        if games < min_games or g < 2:
            continue
        name = p.get('player_name') or '?'
        team = p.get('team_title') or ''
        if g >= games:
            out.append({'player': name, 'team': team, 'league': league_name,
                        'category': 'Player rate',
                        'text': f'{g} goals in {games} games — a goal a game or better',
                        'goals': g, 'games': games, 'minutes': mins,
                        'source': 'understat season totals'})
        over = g - xg
        if over >= 2.0 and g >= 3:
            out.append({'player': name, 'team': team, 'league': league_name,
                        'category': 'Player rate',
                        'text': (f'{g} goals from {xg:.1f} expected — '
                                 f'{over:+.1f} above the chances taken'),
                        'goals': g, 'games': games, 'minutes': mins,
                        'source': 'understat season totals'})
        if mins and games >= 4 and mins / games >= 88:
            out.append({'player': name, 'team': team, 'league': league_name,
                        'category': 'Player rate',
                        'text': f'has played {mins} of a possible {games * 90} minutes',
                        'goals': g, 'games': games, 'minutes': mins,
                        'source': 'understat season totals'})
    out.sort(key=lambda r: (-(r.get('goals') or 0), -(r.get('games') or 0)))
    return out


def build(of_fetch=None, us_fetch=None, today=None):
    of_fetch = of_fetch or (lambda url: http(url))
    us_fetch = us_fetch or understat
    report, streaks, rates = [], [], []

    for league, (repo, fname) in OF_LEAGUES.items():
        for yr in OF_YEARS:
            url = OF.format(repo=repo, yr=yr, file=fname)
            try:
                txt = of_fetch(url)
            except Exception as e:
                report.append(f'  openfootball {league} {yr}: {type(e).__name__}')
                continue
            games = parse_openfootball(txt, default_year=int(yr[:4]))
            withgoals = [g for g in games if g[5] or g[6]]
            if not withgoals:
                report.append(f'  openfootball {league} {yr}: {len(games)} matches, '
                              f'NO goal events yet (backfilled after the season)')
                continue
            got, stale = streak_signals(withgoals, today=today)
            for r in got:
                r['league'] = league
            streaks.extend(got)
            nplayers = len(player_matches(withgoals))
            report.append(f'  openfootball {league} {yr}: {len(withgoals)} matches with '
                          f'scorers, {nplayers} players, {len(got)} live streaks'
                          + (f', {stale} too old to call form' if stale else ''))

    for slug, name in UNDERSTAT_LEAGUES.items():
        try:
            rows = us_fetch(slug)
        except Exception as e:
            report.append(f'  understat {name}: {type(e).__name__}')
            continue
        got = rate_signals(rows, name)
        rates.extend(got)
        report.append(f'  understat {name}: {len(rows)} players, {len(got)} rate signals')

    return {'streaks': streaks, 'rates': rates, 'report': report}


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(('PASS  ' if c else 'FAIL  ') + m)

    TXT = """= England | Premier League 2025/26
▪ Regular Season - 1
Fri Aug 15 2025
  19:00   Liverpool  4-2 (1-0)  Bournemouth
                  (Hugo EKITIKE 37', Cody GAKPO 49', MOHAMED SALAH 90+4';
                   Antoine SEMENYO 64', 76')
Sat Aug 16
  12:30   Aston Villa  0-0 (0-0)  Newcastle United
  15:00   Sunderland  3-0 (0-0)  West Ham United
                  (Eliezer Mayenda 61', Daniel BALLARD 73', Wilson Isidor 90+2')
Sat Aug 23
  15:00   Bournemouth  2-1 (1-0)  Liverpool
                  (Antoine SEMENYO 12', 55'; MOHAMED SALAH 80')
Sat Aug 24
  15:00   Bournemouth  1-0 (0-0)  Sunderland
                  (Antoine SEMENYO 70')
"""
    g = parse_openfootball(TXT, default_year=2025)
    chk(len(g) == 5, f'five matches parsed, got {len(g)}')
    chk(g[0][0] == '2025-08-15' and g[1][0] == '2025-08-16',
        'a bare "Sat Aug 16" inherits the year from the line that had one')
    chk(g[0][1] == 'Liverpool' and g[0][2] == 'Bournemouth' and g[0][3] == 4,
        f'teams and score read correctly: {g[0][1:5]}')
    chk(g[1][5] == [] and g[1][6] == [], 'a 0-0 carries no scorers and does not crash')

    hs = dict(g[0][5])
    chk(hs.get('Hugo EKITIKE') == 1 and hs.get('MOHAMED SALAH') == 1,
        f'home scorers parsed: {g[0][5]}')
    as_ = dict(g[0][6])
    chk(as_.get('Antoine SEMENYO') == 2,
        f'a two-goal player is ONE entry with 2 goals, not two entries: {g[0][6]}')
    chk(len(g[0][5]) == 3 and len(g[0][6]) == 1,
        'the semicolon splits home scorers from away scorers')

    chk(split_scorers("Matt ORILEY 55'(p)") == [('Matt ORILEY', 1)],
        'a penalty still counts and the marker is stripped')
    chk(split_scorers("Joe BLOGGS 12'(og)") == [],
        'an OWN GOAL is not credited to the scorer as a goal')
    chk(split_scorers('') == [], 'an empty chunk yields nothing')

    by = player_matches(g)
    chk(sorted(by['MOHAMED SALAH'])[0][0] == '2025-08-15' and len(by['MOHAMED SALAH']) == 2,
        'the scored-in record lists a player once per match they scored in')

    tm = team_matches(g)
    chk(len(tm['Liverpool']) == 2 and len(tm['Bournemouth']) == 3,
        "every club's own match list is built, scored in or not")
    chk(tm['Liverpool'][1][2] == {'MOHAMED SALAH': 1},
        f'and carries who scored in each: {tm["Liverpool"][1][2]}')

    import datetime as dt
    fresh, stale = streak_signals(g, today=dt.date(2025, 8, 25), window=2, min_hits=2)
    names = {r['player']: r for r in fresh}
    chk('Antoine SEMENYO' in names, 'a live scoring run is reported')
    chk("of Bournemouth's last 2" in names['Antoine SEMENYO']['text'],
        f"the denominator is the TEAM's matches, and says so: "
        f"{names['Antoine SEMENYO']['text']!r}")
    chk('MOHAMED SALAH' in names and names['MOHAMED SALAH']['hits'] == 2,
        'a player who scored in both of his team\'s last two is found')
    _, stale2 = streak_signals(g, today=dt.date(2026, 9, 30), window=2, min_hits=2)
    chk(stale2 > 0, 'the same runs are REFUSED as stale a year later, not re-served')
    chk(not streak_signals(g, today=dt.date(2026, 9, 30), window=2, min_hits=2)[0],
        'and nothing stale reaches the output')
    chk(all("of last" not in r['text'] or "'s last" in r['text'] for r in fresh),
        'no sentence claims a player-appearance denominator the source cannot support')

    US = [{'player_name': 'Erling Haaland', 'team_title': 'Manchester City',
           'games': '5', 'goals': '5', 'time': '450', 'xG': '4.76'},
          {'player_name': 'Bench Warmer', 'team_title': 'X', 'games': '5',
           'goals': '0', 'time': '30', 'xG': '0.1'},
          {'player_name': 'Overperformer', 'team_title': 'Y', 'games': '6',
           'goals': '6', 'time': '540', 'xG': '2.9'}]
    rs = rate_signals(US, 'England Premier League')
    txt = ' | '.join(r['text'] for r in rs)
    chk('5 goals in 5 games' in txt, f'a goal-a-game rate is reported: {txt[:60]}')
    chk('Bench Warmer' not in {r['player'] for r in rs},
        'a player with no goals produces no signal')
    chk('above the chances taken' in txt, 'overperformance against xG is reported')
    chk(all('of last' not in r['text'] for r in rs),
        'NO rate signal is phrased as a streak -- season totals cannot support one')

    def of_stub(url):
        return TXT if 'england' in url and '2025-26' in url else '= empty\n'
    res = build(of_fetch=of_stub, us_fetch=lambda slug: US if slug == 'EPL' else [],
                today=dt.date(2025, 8, 25))
    chk(any('NO goal events yet' in line for line in res['report']),
        'a season whose scorers are not backfilled says so explicitly')
    chk(res['streaks'] and res['rates'], 'both kinds of signal are produced')
    chk({r['source'] for r in res['streaks']} == {'openfootball per-match'} and
        {r['source'] for r in res['rates']} == {'understat season totals'},
        'every signal names which source it came from')

    print(f'\n{ok[0]}/{ok[1]} checks pass')
    return 0 if ok[0] == ok[1] else 1


def main():
    res = build()
    print('socplayers')
    for line in res['report']:
        print(line)
    json.dump({'streaks': res['streaks'], 'rates': res['rates']},
              open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f"\nwrote {OUT} -- {len(res['streaks'])} streaks, {len(res['rates'])} rates")
    for r in res['streaks'][:10]:
        print(f"  {r['player'][:24]:24} {r['text'][:34]:34} {r['team'][:18]}")
    for r in res['rates'][:12]:
        print(f"  {r['player'][:24]:24} {r['text'][:52]:52} {r['team'][:18]}")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

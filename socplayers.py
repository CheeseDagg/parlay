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
import datetime as dt, gzip, json, math, os, re, sys, urllib.parse, urllib.request
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


def parse_openfootball(text, default_year=None, stats=None):
    """[(date, home, away, hg, ag, [(player, goals)], [(player, goals)])]

    Pass a dict as `stats` to get the reconciliation counts back. Nothing
    checked them for the first build and a quarter of every league was wrong
    in silence -- see flush().
    """
    games, cur_date, pending = [], None, None
    year = default_year
    st = stats if stats is not None else {}
    for k in ('ambiguous', 'reconciled', 'mismatch'):
        st.setdefault(k, 0)

    def flush(block):
        if not pending or not block:
            return
        body = ' '.join(block).strip().strip('()')
        if ';' in body:
            h, _, a = body.partition(';')
            pending[5].extend(split_scorers(h))
            pending[6].extend(split_scorers(a))
            return
        # NO SEMICOLON, AND THIS IS WHERE A QUARTER OF EVERY LEAGUE WENT WRONG.
        # openfootball separates the two sides' scorers with ';' -- but omits
        # it entirely when only one side scored:
        #     Wolverhampton Wanderers  0-4 (0-2)  Manchester City
        #                   (Erling HAALAND 34', 61', ...)
        # str.partition on a string with no ';' returns the WHOLE THING as the
        # first part, so every goal in every one-sided away win was credited
        # to the home team. 95 of 380 Premier League matches. It is why
        # Raphinha read as "all 11 of his goals came at home": his away goals
        # were filed under the teams Barcelona beat.
        #
        # The scoreline sitting on the line above disambiguates it completely
        # -- measured across the 2025-26 Premier League, all 140 semicolon-less
        # blocks are one-sided (81 home, 59 away) and none is ambiguous. The
        # ambiguous branch is kept anyway and COUNTED, because a source that
        # starts omitting the separator on a two-sided scoreline would
        # otherwise reintroduce the same silent mis-attribution.
        one = split_scorers(body)
        hg, ag = pending[3], pending[4]
        if ag == 0 and hg:
            pending[5].extend(one)
        elif hg == 0 and ag:
            pending[6].extend(one)
        else:
            st['ambiguous'] += 1

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
    # Reconcile against the scoreline the file already gave us. A match whose
    # listed scorers do not add up to its own result is either incomplete at
    # source or mis-attributed here, and the first build could not tell the
    # difference because it never looked.
    for g in games:
        if sum(n for _, n in g[5]) == g[3] and sum(n for _, n in g[6]) == g[4]:
            st['reconciled'] += 1
        elif g[5] or g[6]:
            st['mismatch'] += 1
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


def team_matches_venue(games):
    """{team: [(date, opp, venue, {player: goals})]} oldest first.

    Separate from team_matches() rather than a wider tuple on it: that one is
    load-bearing for streak_signals and its selftest pins the shape.
    """
    by = defaultdict(list)
    for date, home, away, _hg, _ag, hs, as_ in games:
        by[home].append((date, away, 'home', dict(hs)))
        by[away].append((date, home, 'away', dict(as_)))
    for k in by:
        by[k].sort()
    return by


def poss(name):
    """Possessive that survives a club called Wolves."""
    return name + ("'" if name.endswith('s') else "'s")


def player_spells(games):
    """{(player, team): (first_date, last_date)} for players who changed club.

    A goal feed has no transfer list, but it has something almost as good: a
    player who appears under two different clubs inside one season moved, and
    the file says exactly when. Antoine Semenyo scored for Bournemouth through
    January and for Manchester City after it, and quoting "5 of Manchester
    City's 19 home matches" over a season he spent half of at Bournemouth is
    not a small error -- the denominator counts ten matches before he signed.

    Only players with more than one club get a spell. For everyone else the
    full season is the honest denominator, and it is the CONSERVATIVE one:
    counting matches a player missed through injury understates his rate,
    which is the safe direction for a number someone is going to bet on.
    """
    seen = defaultdict(list)
    for date, home, away, _hg, _ag, hs, as_ in games:
        for team, scorers in ((home, hs), (away, as_)):
            for name, _g in scorers:
                seen[name].append((date, team))
    end = max((g[0] for g in games), default='9999-12-31')
    spells = {}
    for name, rows in seen.items():
        clubs = {t for _d, t in rows}
        if len(clubs) < 2:
            continue
        rows.sort()
        # Order the clubs by FIRST goal, and run each spell from that date up to
        # the day before the next club's first goal. Bounding a spell by the
        # player's own last goal instead -- the obvious first try -- makes it
        # far too tight: a striker who stops scoring in April still played in
        # May, and the denominator would shrink to the weeks he was hot, which
        # inflates every rate built on it. The transfer boundary is a fact in
        # the data; a scoring drought is not a boundary at all.
        firsts = sorted({t: min(d for d, tt in rows if tt == t) for t in clubs}.items(),
                        key=lambda kv: kv[1])
        for i, (club, start) in enumerate(firsts):
            if i + 1 < len(firsts):
                # The day BEFORE the next club's first goal. An inclusive bound
                # would put a match played on the changeover date inside both
                # spells, and the same fixture would be counted twice.
                nxt = dt.date.fromisoformat(firsts[i + 1][1]) - dt.timedelta(days=1)
                stop = min(nxt.isoformat(), end)
            else:
                stop = end
            spells[(name, club)] = (start, stop)
    return spells


def split_signals(games, min_venue=8, min_h2h=3, min_hits=4):
    """Player scoring rates split by venue, and by opponent.

    THESE ARE NOT FORM, AND THAT IS WHY THEY DO NOT EXPIRE. "scored in 5 of
    the last 6" is a claim about right now, so streak_signals kills it at
    MAX_AGE_DAYS. "scored in 9 of 19 at home" is a claim about a completed
    record, and the record does not get less true in October. So these are
    built from every match the source has, and every row carries the span it
    covers instead of being stale-refused.

    The denominator problem is unchanged and handled the same way it is in
    streak_signals: a goal feed knows who scored, not who played. The
    denominator can only be the TEAM's matches at that venue, and the sentence
    says so -- "of Barcelona's 19 home matches", never "of his 19".

    One row per player per venue pair, stating both sides. A row that gave
    only the home number would be the same trap as a de-vigged price quoted
    without its other side: 9 of 19 at home means one thing next to 3 of 19
    away and something else entirely next to 8 of 19.
    """
    tm = team_matches_venue(games)
    spells = player_spells(games)
    dates = sorted(g[0] for g in games)
    span = f'{dates[0][:7]} to {dates[-1][:7]}' if dates else ''
    out, h2h_pairs = [], 0

    def window(player, team, rows):
        """The club's matches that can honestly be this player's denominator."""
        sp = spells.get((player, team))
        if not sp:
            return rows
        lo, hi = sp
        return [r for r in rows if lo <= r[0] <= hi]

    for team, rows in tm.items():
        totals = defaultdict(int)
        for _d, _o, _v, gs in rows:
            for pl, g in gs.items():
                totals[pl] += g

        for player in totals:
            mine = window(player, team, rows)
            home = [r for r in mine if r[2] == 'home']
            away = [r for r in mine if r[2] == 'away']
            if len(home) >= min_venue and len(away) >= min_venue:
                kh = sum(1 for _d, _o, _v, gs in home if gs.get(player))
                ka = sum(1 for _d, _o, _v, gs in away if gs.get(player))
                if max(kh, ka) < min_hits:
                    continue
                rh, ra = kh / len(home), ka / len(away)
                hi, lo = max(rh, ra), min(rh, ra)
                # Rank 0: a genuine split -- one side at least twice the other,
                # or a clean zero. Rank 1: no real split, but a high rate at one
                # venue is still a fact worth a line. Anything else is a good
                # player scoring at a normal clip in both directions, which is
                # not a signal about venue and does not belong in a venue list.
                if lo == 0 or hi >= 2 * lo:
                    rank = 0
                elif hi >= 0.45:
                    rank = 1
                else:
                    continue
                # A windowed denominator has to SAY it is windowed, or "5 of 8"
                # next to a neighbouring "8 of 19" reads as a worse player
                # rather than a shorter spell.
                tail = " since joining" if (player, team) in spells else ""
                out.append({
                    'player': player, 'team': team, 'league': None,
                    'category': 'Player split', 'split': 'venue',
                    'text': (f"scored in {kh} of {poss(team)} {len(home)} home "
                             f"matches{tail}, {ka} of {len(away)} away"),
                    'home_hits': kh, 'home_n': len(home),
                    'away_hits': ka, 'away_n': len(away),
                    'hits': max(kh, ka), 'n': len(home) if rh >= ra else len(away),
                    'goals': sum(gs.get(player, 0) for _d, _o, _v, gs in mine),
                    'span': span, 'rank': rank, 'partial': (player, team) in spells,
                    'source': 'openfootball per-match',
                    'evidence': [{'date': d, 'opp': o, 'venue': v,
                                  'goals': gs.get(player, 0)}
                                 for d, o, v, gs in mine if gs.get(player)][::-1]})

        # Head-to-head. Keyed on the club the player scored for, not on the
        # player alone: a transfer would otherwise sum two clubs' fixtures into
        # one denominator. Keeping the club makes the denominator too LARGE
        # when a player joined mid-window, which understates the rate -- the
        # safe direction for a claim someone is going to bet on.
        #
        # This is also where a search across every player x every opponent will
        # hand you whatever you ask for, so the floor is the same as a streak's:
        # three or more meetings, three or more of them scored in. Never a
        # two-from-two.
        by_opp = defaultdict(list)
        for d, o, v, gs in rows:
            by_opp[o].append((d, v, gs))
        for opp, met in by_opp.items():
            if len(met) < min_h2h:
                continue
            h2h_pairs += 1
            for player in totals:
                # Same transfer window as the venue rows: a player's meetings
                # with an opponent are the ones inside his spell at the club,
                # not every fixture the club played that season.
                sp = spells.get((player, team))
                mine = ([m for m in met if sp[0] <= m[0] <= sp[1]] if sp else met)
                if len(mine) < min_h2h:
                    continue
                hits = sum(1 for _d, _v, gs in mine if gs.get(player))
                if hits < 3 or hits / len(mine) < 0.6:
                    continue
                met_n, goals = len(mine), sum(gs.get(player, 0) for _d, _v, gs in mine)
                text = (f"scored in all {met_n} of {poss(team)} meetings with {opp}"
                        if hits == met_n else
                        f"scored in {hits} of {poss(team)} {met_n} meetings with {opp}")
                if goals > hits:
                    text += f' — {goals} goals'
                out.append({'player': player, 'team': team, 'league': None,
                            'category': 'Player split', 'split': 'h2h', 'opp': opp,
                            'text': text, 'hits': hits, 'n': met_n, 'goals': goals,
                            'span': span, 'rank': 0, 'partial': bool(sp),
                            'source': 'openfootball per-match',
                            'evidence': [{'date': d, 'opp': opp, 'venue': v,
                                          'goals': gs.get(player, 0)}
                                         for d, v, gs in mine if gs.get(player)][::-1]})
    out.sort(key=lambda r: (r['rank'], -(r['hits'] / r['n']), -r['goals']))
    for r in out:
        r.pop('rank', None)
    return out, h2h_pairs


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
    Every sentence is a rate or a total, which is what the data supports.

    RANKED, AND THE DURABILITY ONE IS LAST ON PURPOSE. The first build let
    "has played 450 of a possible 450 minutes" through on any ever-present
    player and it took twelve of the top twelve rows -- true of half a squad,
    and not a signal. It now needs EVERY minute of a real run of games, and
    goals outrank it.
    """
    scored = [p for p in rows if str(p.get('goals', '0')).isdigit() and int(p['goals']) > 0]
    # Key on id OR name: keying on id alone made every player without one
    # collapse to None, and `None in {None}` flagged the whole league as top
    # scorers. Real understat rows carry ids; a source that stops would not
    # announce itself.
    def pkey(p):
        return p.get('id') or p.get('player_name')
    top = sorted(scored, key=lambda p: -int(p['goals']))[:3]
    top_ids = {pkey(p) for p in top if pkey(p)}
    lead = int(top[0]['goals']) if top else 0
    out = []
    for p in rows:
        try:
            g, games = int(p.get('goals', 0)), int(p.get('games', 0))
            mins, xg = int(p.get('time', 0)), float(p.get('xG', 0) or 0)
        except (TypeError, ValueError):
            continue
        if games < min_games:
            continue
        name = p.get('player_name') or '?'
        team = p.get('team_title') or ''
        base = {'player': name, 'team': team, 'league': league_name,
                'category': 'Player rate', 'goals': g, 'games': games,
                'minutes': mins, 'source': 'understat season totals'}

        if pkey(p) in top_ids and g >= 3:
            rank = 'leads the league' if g == lead else 'is among the top scorers'
            out.append(dict(base, rank=0,
                            text=f'{rank} with {g} goals in {games} games'))
        elif g >= games and g >= 2:
            out.append(dict(base, rank=1,
                            text=f'{g} goals in {games} games — a goal a game or better'))
        elif g >= 4:
            out.append(dict(base, rank=2,
                            text=f'{g} goals in {games} games'))

        if g >= 3 and g - xg >= 2.0:
            out.append(dict(base, rank=3,
                            text=(f'{g} goals from {xg:.1f} expected — '
                                  f'{g - xg:+.1f} above the chances he has had')))
        elif g >= 3 and xg - g >= 2.0:
            out.append(dict(base, rank=4,
                            text=(f'{g} goals from {xg:.1f} expected — '
                                  f'{g - xg:+.1f} below the chances he has had')))

        # Durability: every minute of a real run, and it sorts beneath goals.
        if games >= 5 and mins >= games * 90:
            out.append(dict(base, rank=9,
                            text=f'has played every minute of all {games} games'))
    out.sort(key=lambda r: (r.get('rank', 5), -(r.get('goals') or 0)))
    for r in out:
        r.pop('rank', None)
    return out


def build(of_fetch=None, us_fetch=None, today=None):
    of_fetch = of_fetch or (lambda url: http(url))
    us_fetch = us_fetch or understat
    report, streaks, rates, splits = [], [], [], []
    pooled = defaultdict(list)

    for league, (repo, fname) in OF_LEAGUES.items():
        for yr in OF_YEARS:
            url = OF.format(repo=repo, yr=yr, file=fname)
            try:
                txt = of_fetch(url)
            except Exception as e:
                report.append(f'  openfootball {league} {yr}: {type(e).__name__}')
                continue
            pstats = {}
            games = parse_openfootball(txt, default_year=int(yr[:4]), stats=pstats)
            # A 0-0 IS A MATCH THE PLAYER DID NOT SCORE IN. The first build
            # filtered to matches that had goal events and then used that list
            # as the denominator, so every goalless draw vanished and every
            # rate was quoted over a short season: Crystal Palace read as
            # "14 home matches" because five of their nineteen finished 0-0.
            # The filter is only fit for deciding whether the FILE carries goal
            # events at all (2026-27 parses fine and lists none), which is what
            # it is used for now -- the full list goes downstream.
            withgoals = [g for g in games if g[5] or g[6]]
            if not withgoals:
                report.append(f'  openfootball {league} {yr}: {len(games)} matches, '
                              f'NO goal events yet (backfilled after the season)')
                continue
            got, stale = streak_signals(games, today=today)
            for r in got:
                r['league'] = league
            streaks.extend(got)
            # Splits pool ACROSS seasons on purpose. A streak is about now, so
            # it lives inside one season and expires; a home/away or
            # head-to-head record is a standing fact, and two seasons of
            # meetings is the difference between a head-to-head worth reading
            # and a 2-from-2 that means nothing.
            pooled[league].extend(games)
            nplayers = len(player_matches(games))
            report.append(f'  openfootball {league} {yr}: {len(games)} matches '
                          f'({len(withgoals)} with scorers), {nplayers} players, '
                          f'{len(got)} live streaks'
                          + (f', {stale} too old to call form' if stale else ''))
            # The scoreline reconciliation is REPORTED, not hidden. The first
            # build credited every one-sided away win's scorers to the home
            # team and nothing noticed, because nothing compared the parsed
            # scorers against the result printed on the line above them.
            report.append(f'    reconciled {pstats["reconciled"]} vs scoreline, '
                          f'{pstats["mismatch"]} short (own goals and gaps at source)'
                          + (f', {pstats["ambiguous"]} REFUSED as unattributable'
                             if pstats['ambiguous'] else ''))

    for league, games in pooled.items():
        got, h2h_pairs = split_signals(games)
        for r in got:
            r['league'] = league
        splits.extend(got)
        nv = sum(1 for r in got if r['split'] == 'venue')
        nh = sum(1 for r in got if r['split'] == 'h2h')
        line = f'  splits {league}: {len(games)} pooled matches, {nv} venue, {nh} head-to-head'
        if not h2h_pairs:
            # Say WHY it is empty. openfootball carries goal events for one
            # season only (2024-25 and earlier parse but list no scorers), and
            # inside one season no two clubs meet more than twice -- below the
            # three-meeting floor by construction. This turns on by itself the
            # season a second year of scorers lands, and until then an empty
            # head-to-head list is the source's limit, not a missing feature.
            line += ' (no pair has met 3+ times in the seasons that carry scorers)'
        report.append(line)

    for slug, name in UNDERSTAT_LEAGUES.items():
        try:
            rows = us_fetch(slug)
        except Exception as e:
            report.append(f'  understat {name}: {type(e).__name__}')
            continue
        got = rate_signals(rows, name)
        rates.extend(got)
        report.append(f'  understat {name}: {len(rows)} players, {len(got)} rate signals')

    return {'streaks': streaks, 'rates': rates, 'splits': splits, 'report': report}


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
    chk(rs[0]['player'] in ('Erling Haaland', 'Overperformer') and 'goals' in rs[0]['text'],
        'a GOAL signal leads, never the durability one')
    mins_i = [i for i, r in enumerate(rs) if 'every minute' in r['text']]
    goal_i = [i for i, r in enumerate(rs) if 'goals' in r['text']]
    chk(not mins_i or not goal_i or min(mins_i) > max(goal_i),
        'durability sorts beneath every goal signal -- it flooded the first build')
    chk(all('rank' not in r for r in rs), 'the sort key is stripped before output')
    chk('Bench Warmer' not in {r['player'] for r in rs},
        'a player with no goals produces no signal')
    chk('above the chances he has had' in txt, 'overperformance against xG is reported')
    chk(sum(1 for r in rs if 'top scorers' in r['text'] or 'leads the league' in r['text']) <= 3,
        'at most three players per league read as top scorers')
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

    # ---------------------------------------------------------- the parser bug
    # openfootball omits the ';' between the two sides' scorers when only one
    # side scored. str.partition then returns the WHOLE block as the home part,
    # so every goal in every one-sided away win was credited to the home team:
    # 95 of 380 Premier League matches, and the symptom was strikers reading as
    # "all his goals came at home" because their away goals were filed under
    # the clubs they beat.
    ONE_SIDED = """= T
Fri Aug 15 2025
  19:00   Wolves  0-4 (0-2)  Manchester City
                  (Erling HAALAND 34', 61', Rayan CHERKI 81', Tijjani REIJNDERS 37')
  19:00   Sunderland  3-0 (0-0)  West Ham United
                  (Eliezer Mayenda 61', Daniel BALLARD 73', Wilson Isidor 90+2')
  19:00   Chelsea  0-0 (0-0)  Palace
  19:00   Everton  2-1 (1-0)  Leeds
                  (Iliman NDIAYE 12', Beto 55'; Joe RODON 80')
"""
    st = {}
    gs_ = parse_openfootball(ONE_SIDED, 2025, stats=st)
    byname = {f'{g[1]} v {g[2]}': g for g in gs_}
    wolves = byname['Wolves v Manchester City']
    chk(wolves[5] == [] and sum(n for _, n in wolves[6]) == 4,
        'a 0-4 with no semicolon credits all four goals to the AWAY team')
    chk(dict(wolves[6]).get('Erling HAALAND') == 2,
        'a two-goal player in a semicolon-less block is one entry with 2 goals')
    sund = byname['Sunderland v West Ham United']
    chk(sum(n for _, n in sund[5]) == 3 and sund[6] == [],
        'a 3-0 with no semicolon still credits the HOME team')
    ev = byname['Everton v Leeds']
    chk(sum(n for _, n in ev[5]) == 2 and sum(n for _, n in ev[6]) == 1,
        'a semicolon block is still split on the semicolon')
    chk(st['reconciled'] == 4 and st['mismatch'] == 0 and st['ambiguous'] == 0,
        'every parsed match reconciles against its own scoreline')
    AMBIG = """= T
Fri Aug 15 2025
  19:00   A  1-1 (0-0)  B
                  (Someone 12')
"""
    st2 = {}
    ag = parse_openfootball(AMBIG, 2025, stats=st2)
    chk(ag[0][5] == [] and ag[0][6] == [] and st2['ambiguous'] == 1,
        'a semicolon-less block on a two-sided scoreline is REFUSED, not guessed')

    # ------------------------------------------------------- splits: the rules
    def season(team, hs_dates, as_dates, scorer, home_goals, away_goals, opp='Rival'):
        """A synthetic club season: n home + n away, scorer hits listed dates."""
        out = []
        for i, d in enumerate(hs_dates):
            sc = [(scorer, 1)] if i in home_goals else []
            out.append((d, team, f'{opp}{i}', 1 if sc else 0, 0, sc, []))
        for i, d in enumerate(as_dates):
            sc = [(scorer, 1)] if i in away_goals else []
            out.append((d, f'{opp}{i}', team, 0, 1 if sc else 0, [], sc))
        return out

    hd = [f'2025-09-{i+1:02d}' for i in range(10)]
    ad = [f'2025-10-{i+1:02d}' for i in range(10)]
    g1 = season('Cats', hd, ad, 'Striker', {0, 1, 2, 3, 4, 5}, set())
    sp, pairs = split_signals(g1, min_venue=8, min_h2h=3, min_hits=4)
    v = [r for r in sp if r['split'] == 'venue' and r['player'] == 'Striker']
    chk(len(v) == 1 and v[0]['text'] == "scored in 6 of Cats' 10 home matches, 0 of 10 away",
        'a venue row states BOTH sides in one sentence, and Cats\' takes a bare apostrophe')
    chk(v[0]['home_hits'] == 6 and v[0]['away_n'] == 10 and not v[0].get('partial'),
        'the venue row carries both denominators as fields, unwindowed')
    chk(pairs == 0, 'no opponent met 3 times, so no head-to-head was even attempted')

    # A GOALLESS DRAW IS A MATCH HE DID NOT SCORE IN. All ten away fixtures
    # above finished 0-0, so an away_n of 10 is the whole check: the first build
    # filtered goalless matches out before measuring and quoted every rate over
    # a short season.
    chk(sum(1 for g in g1 if not g[5] and not g[6]) == 14 and v[0]['away_n'] == 10,
        'goalless matches stay in the denominator instead of shortening the season')

    # an even scorer at both ends is not a VENUE signal
    g3 = season('Dogs', hd, ad, 'Even', {0, 1, 2, 3}, {0, 1, 2, 3})
    sp3, _ = split_signals(g3, min_venue=8, min_h2h=3, min_hits=4)
    chk(not [r for r in sp3 if r['split'] == 'venue'],
        'scoring at the same clip home and away is not a venue split')

    # below the hit floor at both ends -> nothing
    g4 = season('Eels', hd, ad, 'Quiet', {0, 1}, set())
    sp4, _ = split_signals(g4, min_venue=8, min_h2h=3, min_hits=4)
    chk(not sp4, 'two goals at one venue is below the floor and produces no row')

    # short seasons cannot support a venue claim
    g5 = season('Figs', hd[:5], ad[:5], 'Striker', {0, 1, 2, 3}, set())
    sp5, _ = split_signals(g5, min_venue=8, min_h2h=3, min_hits=4)
    chk(not [r for r in sp5 if r['split'] == 'venue'],
        'a club with fewer than min_venue matches at a venue gets no venue row')

    # ------------------------------------------------------ splits: transfers
    moved = (season('Old', hd[:5], ad[:5], 'Mover', {0, 1, 2}, set())
             + season('New', hd[5:], ad[5:], 'Mover', {0, 1, 2, 3}, set()))
    # give New a full pre-transfer slate that Mover was NOT part of
    moved += [(f'2025-08-{i+1:02d}', 'New', f'X{i}', 0, 0, [], []) for i in range(6)]
    moved += [(f'2025-08-{i+1:02d}', f'X{i}', 'New', 0, 0, [], []) for i in range(6, 12)]
    spells = player_spells(moved)
    chk(('Mover', 'New') in spells and ('Mover', 'Old') in spells,
        'a player appearing under two clubs is detected as having moved')
    chk(spells[('Mover', 'New')][0] == '2025-09-06',
        "the spell starts at the player's first goal for the new club, not the season")
    spm, _ = split_signals(moved, min_venue=5, min_h2h=3, min_hits=4)
    vm = [r for r in spm if r['player'] == 'Mover' and r['team'] == 'New']
    chk(vm and vm[0]['home_n'] == 5 and vm[0]['partial'],
        "a transferred player's denominator is his spell, not the club's season")
    chk(vm and 'since joining' in vm[0]['text'],
        'a windowed denominator says so, or "5 of 8" reads as a worse player')

    # ----------------------------------------------------- splits: head-to-head
    h2h = []
    for i, d in enumerate(['2024-09-01', '2025-02-01', '2025-09-01', '2026-02-01']):
        sc = [('Nemesis', 1)] if i != 1 else []
        h2h.append((d, 'Cats', 'Rival', 1 if sc else 0, 0, sc, []))
    h2h += [(f'2025-11-{i+1:02d}', 'Cats', f'Other{i}', 0, 0, [], []) for i in range(6)]
    sph, pairs2 = split_signals(h2h, min_venue=99, min_h2h=3, min_hits=4)
    hh = [r for r in sph if r['split'] == 'h2h']
    # pairs2 is 2 because the pairing is counted from BOTH clubs' fixture
    # lists; only Cats have a player who scored in it, so only one row exists.
    chk(pairs2 == 2 and len(hh) == 1,
        'only the opponent met 3+ times is eligible for a head-to-head row')
    chk(hh[0]['text'] == "scored in 3 of Cats' 4 meetings with Rival",
        'the head-to-head sentence names the club whose fixtures are the denominator')
    two = [(d, 'Cats', 'Rival', 1, 0, [('Flash', 1)], []) for d in ('2025-09-01', '2026-02-01')]
    sp2, _ = split_signals(two, min_venue=99, min_h2h=3, min_hits=4)
    chk(not sp2, 'a two-from-two is never a head-to-head signal')

    # ------------------------------------------------------------- not form
    chk(not any('last' in r['text'] for r in sp + sph),
        'a split never borrows the language of form -- no "last N" in a standing record')
    chk(all(r.get('span') for r in sp + sph),
        'every split row carries the span it was built from')

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

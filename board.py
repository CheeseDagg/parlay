"""Candidate-leg construction, factored out of solve.py so more than one solver
can share one definition of what is bettable.

Nothing here optimises. It answers a single question: given a book, a wall
clock, and the constraints Ryan has set, which legs exist? Every filter is
applied HERE, before any solver sees the pool, because a filter applied after
the fact only edits the answer -- a filter applied before it changes what the
answer is optimising over.

Market keys, i.e. what a solver may take at most one of:
  ('K', pitcher)  -- the strikeout ladder is nested, one rung only
  ('GT', game)    -- full-game AND first-five share a key. Not nested, but one
                     run-scoring process measured twice, and exactly the pair
                     an SGP+ engine reprices hardest.
  ('F', card, fighter) -- both sides, so a solver cannot take both fighters
"""
import json, math, sys
from scipy.optimize import brentq
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from totals import TOTALS_RAW, GAME_OF
from f5 import F5_RAW
from mma import MMA_RAW
from other import OTHER_RAW
from mlbml import MLBML_RAW
from times import START, FIGHT_START

# Cross-repo reads into MLBTool's published data. These are ENRICHMENT, not
# structure: K lambdas price strikeout rungs (a family that is currently
# excluded by standing instruction anyway) and slate.json lends the moneyline
# legs a model opinion to agree or disagree with. Neither exists on the GitHub
# Actions runner -- only THIS repo is checked out there -- and the hardcoded
# /root path failed the whole board with PermissionError on 2026-08-04, three
# steps after a perfect 510-leg pull. Absence has to be a stated condition,
# not a crash: legs still price from the market, opinions simply say nothing.
def _mlbtool(fname):
    import os
    cands = []
    if os.environ.get('MLBTOOL_DATA'):
        cands.append(os.path.join(os.environ['MLBTOOL_DATA'], fname))
    # /root was this container's checkout root once and is not any more. A
    # sibling checkout next to THIS repo is the layout that actually ships --
    # both here (/home/user/{parlay,MLBTool}) and anywhere else the two repos
    # are cloned side by side -- so derive it from __file__ rather than naming
    # a machine. The absolute path stays as a fallback, and the Actions runner
    # still legitimately finds nothing, which is why absence stays a printed
    # condition rather than a crash.
    _sib = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'MLBTool', 'mlb', 'data')
    cands.append(os.path.join(_sib, fname))
    cands.append(os.path.join('/root/MLBTool/mlb/data', fname))
    for p in cands:
        try:
            with open(p) as fh:
                return json.load(fh)
        except Exception:
            continue
    print(f"  board: MLBTool's {fname} is not readable here -- "
          f"{'K lambdas' if 'kprops' in fname else 'ML model opinions'} off. "
          f"Every leg still prices from the market; nothing else is affected.")
    return None

_kp = _mlbtool('kprops.json')
LAM = {b['pitcher']: b['lam'] for b in _kp['board']} if _kp else {}

# Model win probability for the HOME side of each game on today's slate. Used
# only to AGREE OR DISAGREE with the market, never to replace it: the reported
# probability on a moneyline leg stays the de-vigged price, because a model
# number substituted into a parlay quote would be reporting my own opinion back
# to myself as if it were a fact. Saturday games are not on the slate, so they
# simply carry no model opinion and are neither endorsed nor vetoed.
_SL = _mlbtool('slate.json') or {}
TEAM3 = {'Arizona Diamondbacks': 'ARI', 'Atlanta Braves': 'ATL',
         'Baltimore Orioles': 'BAL', 'Boston Red Sox': 'BOS',
         'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS',
         'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE',
         'Colorado Rockies': 'COL', 'Detroit Tigers': 'DET',
         'Houston Astros': 'HOU', 'Kansas City Royals': 'KC',
         'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD',
         'Miami Marlins': 'MIA', 'Milwaukee Brewers': 'MIL',
         'Minnesota Twins': 'MIN', 'New York Mets': 'NYM',
         'New York Yankees': 'NYY', 'Athletics': 'ATH',
         'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT',
         'San Diego Padres': 'SD', 'San Francisco Giants': 'SF',
         'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL',
         'Tampa Bay Rays': 'TB', 'Texas Rangers': 'TEX',
         'Toronto Blue Jays': 'TOR', 'Washington Nationals': 'WSH'}
assert len(set(TEAM3.values())) == len(TEAM3) == 30, \
    f"TEAM3 must map 30 distinct clubs, got {len(TEAM3)} names / " \
    f"{len(set(TEAM3.values()))} codes"

# MODEL_P IS KEYED BY GAME, NOT BY TEAM. It used to be {team_code: p}, which is
# wrong in two ways at once and was wrong in production:
#
#   1. slate.json holds ONE day. mlbml.py is a hand-pasted snapshot that can be
#      several days old. A team-keyed map happily stamps TODAY'S win probability
#      onto a moneyline for a game that finished three days ago -- and did: on
#      2026-08-03, 9 of 27 ML legs carried an "opinion" belonging to a different
#      game entirely, and --mlagree was filtering on it.
#   2. A team plays twice on a doubleheader date. A team-keyed map holds one
#      number and hands the SAME opinion to both halves.
#
# The key is (ET slate date, AWAY@HOME). Both have to match or there is no
# opinion -- which, since --mlagree now abstains rather than vetoes, is the safe
# direction to be wrong in.
SLATE_DATE = _SL.get('slate_date', '')

def _et_date(utc):
    """ET calendar date of a UTC start. Eastern is UTC-4 across this whole board;
    a 01:41Z start is the PREVIOUS day's slate, which is exactly the confusion
    that makes matching on the UTC date silently wrong for every night game."""
    from datetime import datetime, timedelta
    return (datetime.strptime(utc, "%Y-%m-%dT%H:%MZ")
            - timedelta(hours=4)).strftime("%Y-%m-%d")


def _utcnow():
    """Wall clock in the same string shape every leg's t carries, so the two are
    directly comparable as strings and no leg ever gets parsed just to be
    compared. One definition, because two solvers were each building their own."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')


def _age_h(then, now):
    """'42h' / '3.1d' -- how long ago `then` was. A raw pair of timestamps makes
    a reader do date arithmetic to find out whether a board is an hour stale or a
    week stale, and those two call for completely different responses."""
    from datetime import datetime
    f = "%Y-%m-%dT%H:%MZ"
    h = (datetime.strptime(now, f) - datetime.strptime(then, f)).total_seconds() / 3600
    return f"{h:.0f}h" if h < 48 else f"{h/24:.1f}d"


# Set by build(): True when NOT ONE leg in the raw pool is still to come. It is a
# property of the feed, so it survives the filters -- a solver that finds nothing
# needs to know whether it found nothing because its constraints were tight or
# because there was never anything live to find. Those have opposite fixes.
FEED_DEAD = False

MODEL_P = {}
ADJ_TOTAL = {}
_unmapped = set()
for _g in _SL.get('games', []):
    _h, _a = TEAM3.get(_g['home']), TEAM3.get(_g['away'])
    # A name slate.json uses that TEAM3 has never heard of is a VOCABULARY BUG, not
    # a missing opinion. It used to vanish here in silence, and the only visible
    # symptom downstream was --mlagree quietly having nothing to say. If MLB renames
    # a club (Cleveland Indians -> Guardians, Oakland Athletics -> Athletics) every
    # game silently drops out and the filter degrades to a no-op. Name it out loud.
    if _g['home'] not in TEAM3: _unmapped.add(_g['home'])
    if _g['away'] not in TEAM3: _unmapped.add(_g['away'])
    if not (_h and _a):
        continue
    _key = (_g.get('date', SLATE_DATE), f"{_a}@{_h}")
    if _g.get('adj_total') is not None:
        # The park/weather-adjusted total is the model's read on the game's run
        # ENVIRONMENT, and it is the input the hot-game veto below runs on. On
        # 8/11 the slate had CHC@WSH at 10.52 -- the hottest game of fifteen,
        # two full runs above the market's main total -- and the board never
        # saw it, because this number was parsed for nothing.
        ADJ_TOTAL[_key] = float(_g['adj_total'])
    if _g.get('p_home') is None:
        continue
    MODEL_P[_key] = _g['p_home'] / 100.0
if _unmapped:
    print(f"  board: slate.json uses {len(_unmapped)} team name(s) TEAM3 does not "
          f"know -- {sorted(_unmapped)}. Those games carry no model opinion.")

# A stale slate abstains cleanly on every keyed lookup (the date never matches),
# but silence is how it stayed four days old without anyone noticing: the fix
# was one `git pull` away the whole time. Say it once, loudly, at import.
if _SL:
    _today_et = _et_date(_utcnow())
    if SLATE_DATE != _today_et:
        print(f"  board: MLBTool slate.json is dated {SLATE_DATE}, today is "
              f"{_today_et} ET -- park/weather/adj-total and model opinions are "
              f"ABSTAINING. Fix: git -C ../MLBTool pull")


def _mainline(rows):
    """The market's MAIN total for a game is the rung with the most balanced
    juice, not the deepest rung posted. Confusing those two is how a ladder top
    of U15.5 got quoted as 'the game total is 15.5' in a post-mortem while the
    actual main line sat at 8.5. rows: [(point, over_am, under_am), ...]."""
    def bal(r):
        io = 1 / dec(r[1]); iu = 1 / dec(r[2])
        return abs(io - iu)
    return min(rows, key=bal)[0] if rows else None


def main_totals(book='FanDuel'):
    """{ 'AWAY@HOME': main full-game total } straight from totals.py."""
    from totals import TOTALS_RAW
    games = {}
    for ln in TOTALS_RAW.strip().splitlines():
        p = ln.strip().split('|')
        if len(p) != 5 or p[1] != book:
            continue
        games.setdefault(p[0], []).append((float(p[2]), int(p[3]), int(p[4])))
    return {g: _mainline(rows) for g, rows in games.items()}


def _hot(main, adj, slate_fresh):
    """The 8/11 rule, as a pure function so the selftest can hold it down.

    A game is HOT -- its F5 unders are top-rung-only -- when the model's
    adjusted total says the run environment is extreme (>= 10), or when the
    model sits 1.5+ runs ABOVE the market's main total (heat the market has
    not priced; CHC@WSH was adj 10.52 vs main 8.5 the night it killed a
    20-leg slip). With no fresh slate the market-only arm still catches the
    obvious bandbox: main total >= 10.
    """
    out = {}
    for g, m in main.items():
        a = adj.get(g) if slate_fresh else None
        if a is not None:
            if a >= 10.0:
                out[g] = f"model adj_total {a:.2f} >= 10"
            elif m is not None and a - m >= 1.5:
                out[g] = f"model {a:.2f} sits {a - m:.1f} runs above the market's main {m}"
        elif m is not None and m >= 10.0:
            out[g] = f"market main total {m} >= 10 (no fresh slate)"
    return out


def hot_games(book='FanDuel'):
    """{ grp: reason } for games whose F5 ladder should be top-rung-only."""
    fresh = bool(_SL) and SLATE_DATE == _et_date(_utcnow())
    adj = {g: t for (d, g), t in ADJ_TOTAL.items() if d == SLATE_DATE}
    return _hot(main_totals(book), adj, fresh)


def model_p(code, game, utc):
    """Model probability that THIS leg's team wins THIS game, or None.

    code : full club name off the leg label      ('Cincinnati Reds')
    game : the AWAY@HOME group off the feed      ('PIT@CIN', or 'PIT@CIN2' for
           the second meeting of a series -- the trailing digit is a feed-side
           disambiguator, never part of a club code, so stripping it is safe)
    utc  : the leg's scheduled start

    Returns None -- ABSTAIN, not veto -- whenever the game is not on the model's
    slate, the club name is unknown, or the leg's team is not actually in the
    matchup. Every one of those used to silently resolve to "some team's number
    from some other day."
    """
    t3 = TEAM3.get(code)
    if not t3:
        return None
    key = game.rstrip('0123456789')
    p_home = MODEL_P.get((_et_date(utc), key))
    if p_home is None:
        return None
    try:
        away, home = key.split('@')
    except ValueError:
        return None
    if t3 == home:
        return p_home
    if t3 == away:
        return 1.0 - p_home
    return None          # leg's team is not in this matchup: a feed error, not an opinion


def dec(am):
    am = float(am)
    return 1 + (am / 100 if am > 0 else 100 / -am)


def pois_sf(k, lam):
    """P(X > k) for X ~ Poisson(lam), summed forward so the tail is not a
    difference of two nearly-equal numbers."""
    t = math.exp(-lam); c = t
    for i in range(1, int(k) + 1):
        t *= lam / i; c += t
    return 1 - c


# Which de-vig the whole board uses. 'mult' splits the overround in proportion
# to implied price, which is known to understate heavy favourites: books load
# more margin on the longshot side. 'power' solves sum(q_i^k)=1, taking margin
# off the longshot first, and is the most favourite-friendly of the standard
# corrections. This is a global switch and not a per-leg fudge -- a de-vig that
# flattered one ticket's legs and not another's would make the two
# unbcomparable, which is the whole thing the comparison is for.
METHOD = 'power'
# Changed from 'mult' on 2026-08-03. Multiplicative de-vig is the wrong default
# for THIS board specifically: every ticket built here is heavy favourites, and
# multiplicative de-vig is biased against heavy favourites in a known direction.
# It splits the overround in proportion to implied price, but books do not load
# margin that way -- they load more of it onto the longshot side. A -5000 leg
# de-vigs to .9363 under 'mult' and .9737 under 'power', and a 16-leg slip made
# of legs like that compounds the difference into the headline number. See
# devigcmp.py for the side-by-side, including Shin (more aggressive still).
#
# 'mult' remains available and is the more conservative choice; it is NOT the
# safer one here, because understating a favourite makes a bad parlay look
# worse but also makes a solver prefer the wrong legs.


def _split(qs):
    if METHOD == 'mult':
        s = sum(qs)
        return [q / s for q in qs]
    if METHOD == 'power':
        k = brentq(lambda k: sum(q ** k for q in qs) - 1, 0.2, 8.0)
        return [q ** k for q in qs]
    raise ValueError(METHOD)


def devig(yes, no):
    """De-vig of a matched two-way pair under the board's current METHOD."""
    return _split([1 / dec(yes), 1 / dec(no)])[0]


def devig_n(sel, others):
    """Same idea as devig() but for a market with any number of outcomes, which
    is what a soccer three-way needs: the draw is a real outcome and dropping it
    would overstate the favourite by roughly the draw's whole share."""
    return _split([1 / dec(sel)] + [1 / dec(o) for o in others])[0]


def build(book, no_plus=True, min_price=0, cutoff=None, drop=(), max_price=0,
          drop_fam=(), drop_lab=(), nostack=False, horizon=None):
    """min_price is a POSITIVE magnitude: min_price=200 keeps only legs at -200
    or heavier. max_price is the mirror of it: max_price=200 keeps only legs at
    -200 or LONGER, which is what a promo token that caps each leg at -200 needs.
    The two are not redundant -- one is a floor on how much price a leg buys, the
    other a ceiling, and a token can impose the ceiling while the 20-1 target
    still imposes a total. cutoff is a UTC 'YYYY-MM-DDTHH:MMZ' string; legs
    starting at or before it are gone (a game already underway is not bettable
    at the posted price, so it is not a candidate). drop_fam removes whole leg
    FAMILIES ('K', 'F5', 'FG', 'MMA', ...) rather than single events, which is
    what "no pitcher props at all" needs -- it is a statement about a kind of
    bet, not about a game. drop_lab is a list of case-insensitive substrings
    matched against a leg's label, which is how a veto on one named player or
    team is expressed: Ryan's read on a specific pitcher is information the
    board does not contain, so it belongs at pool construction like every other
    constraint, not as a post-hoc edit of the answer. nostack collapses a
    pitcher's strikeout ladder into that game's ('GT', game) slot, so a K prop
    can no longer sit alongside the same game's total or moneyline, and two
    opposing starters can no longer both appear. Strikeouts suppress runs, so
    those pairs are positively correlated and an SGP+ engine reprices them --
    the payout shown on the slip would not be the payout offered.

    horizon is the mirror of cutoff and exists for a failure this board only
    acquired once boxing and the European league restarts joined it. cutoff
    removes legs that have already STARTED; nothing removed legs that start in
    OCTOBER. The solver has no notion of "soon", it maximises probability at a
    price, and the heaviest prices on a three-month board are the ones furthest
    out -- so a ticket that reads as "this weekend" in every visible respect
    quietly contained a 2026-09-13 boxing leg and a 2026-10-31 one, and would
    not have resolved for three months. Nothing on the printout said so; the
    start column said 'Sat 11:00pm' and gave no date. Same defect family as the
    rest of this package: correct arithmetic about a question nobody asked. Pass
    a 'YYYY-MM-DD' or a full UTC stamp; legs starting after it are gone."""
    markets = {}

    def add(key, **kw):
        markets.setdefault(key, []).append(kw)

    # ---- K legs: Poisson off the kprops lambda, one rung per pitcher
    # Resolved relative to THIS file, not to /root/parlay: the same absolute-path
    # habit that broke the Actions runner on the MLBTool reads broke it again
    # right here, one run later, on the board's own ladder file.
    import os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    src = _os.path.join(_here, 'fd_k_ladder.txt' if book == 'FanDuel' else 'kraw.txt')
    # A pitcher on the ladder but not in LAM has no lambda, so there is no
    # distribution to price him off and he MUST be skipped. But skipping in
    # silence is how the ENTIRE K family disappeared on 2026-08-03: kprops.json
    # is regenerated for today's slate while fd_k_ladder.txt is a hand-pasted
    # snapshot of an older one, so the two name sets had ZERO overlap -- 26
    # ladder pitchers, 26 skips, 0 K legs, no message. "No K legs on the board"
    # and "the K feed is stale" look identical from the outside. Count them.
    #
    # An EMPTY ladder file is a third state and needs its own message. It reads
    # exactly like the two above from the outside -- zero K legs, no complaint --
    # but it means something completely different: the ladder was cleared on
    # purpose because pitcher props are excluded by standing instruction. Say so,
    # otherwise the next reader "fixes" the silence by repasting a ladder and puts
    # a family back on the board that was removed deliberately.
    _kraw = open(src).read().strip()
    if not _kraw:
        print(f"  board: {src.rsplit('/', 1)[-1]} is EMPTY, so there are no "
              f"strikeout legs. That is deliberate -- pitcher props are excluded. "
              f"It is not a failed paste.")
    _nolam = set()
    for line in _kraw.splitlines():
        if not line.strip():
            continue
        parts = line.split('|')
        if book == 'FanDuel':
            p, pt, price = parts
        else:
            bk, p, pt, price = parts
            if bk != book:
                continue
        if p not in LAM:
            _nolam.add(p)
            continue
        g = GAME_OF.get(p, '?')
        add((('GT', g) if nostack else ('K', p)),
            p=pois_sf(int(float(pt) - 0.5), LAM[p]), d=dec(price),
            lab=f"{p} {int(float(pt)+0.5)}+ Ks", price=int(price),
            grp=g, fam='K', sport='MLB', t=START.get(g, 'Z'))
    if _nolam:
        _kn = sum(1 for v in markets.values() for o in v if o['fam'] == 'K')
        print(f"  board: {len(_nolam)} pitcher(s) on the K ladder have no lambda in "
              f"kprops.json and were skipped -- {sorted(_nolam)[:6]}"
              f"{' ...' if len(_nolam) > 6 else ''}. K legs built: {_kn}.")
        if _kn == 0:
            print("  WARNING: the K family is EMPTY. The ladder file and kprops.json "
                  "are describing different slates (or different name spellings).")

    # ---- full-game alternate totals, both sides
    for line in TOTALS_RAW.strip().splitlines():
        if not line.strip():
            continue
        g, bk, pt, over, under = line.split('|')
        if bk != book:
            continue
        add(('GT', g), p=devig(int(under), int(over)), d=dec(under),
            lab=f"{g} Under {pt}", price=int(under), grp=g, fam='FG',
            sport='MLB', t=START[g])
        add(('GT', g), p=devig(int(over), int(under)), d=dec(over),
            lab=f"{g} Over {pt}", price=int(over), grp=g, fam='FG',
            sport='MLB', t=START[g])

    # ---- first-five totals. FanDuel only: DraftKings' F5 ladder stops at 5.5
    #      and its deepest leg de-vigs to .674, below every leg already in play.
    if book == 'FanDuel':
        for line in F5_RAW.strip().splitlines():
            if not line.strip():
                continue
            g, pt, over, under = line.split('|')
            add(('GT', g), p=devig(int(under), int(over)), d=dec(under),
                lab=f"{g} F5 Under {pt}", price=int(under), grp=g, fam='F5',
                sport='MLB', t=START[g])
            add(('GT', g), p=devig(int(over), int(under)), d=dec(over),
                lab=f"{g} F5 Over {pt}", price=int(over), grp=g, fam='F5',
                sport='MLB', t=START[g])

    # ---- fight moneylines, de-vigged matched pair, no model involved
    for line in MMA_RAW.strip().splitlines():
        if not line.strip():
            continue
        bk, card, who, price, opp = line.split('|')
        if bk != book:
            continue
        add(('F', card, who), p=devig(int(price), int(opp)), d=dec(price),
            lab=f"{who} ML", price=int(price), grp=card, fam='MMA',
            sport='FIGHT', t=FIGHT_START[who])
        add(('F', card, who), p=devig(int(opp), int(price)), d=dec(opp),
            lab=f"{who}'s opponent ML", price=int(opp), grp=card, fam='MMA',
            sport='FIGHT', t=FIGHT_START[who])

    # ---- everything else on the weekend board: boxing, WNBA, tennis, CFL,
    #      soccer. FanDuel only in the source file, so no book filter here.
    #      One market key per event, every outcome listed, so a solver can take
    #      at most one side and the de-vig sees the whole book.
    #
    #      SOCCER IS THE EXCEPTION, and the exception is RULES.md #8: never a
    #      3-way moneyline -- PSV drew v Fortuna Sittard on 8/8 and killed a
    #      20-leg slip sitting 15/20. Until 8/12 that rule lived in prose and
    #      in chat habits while this loop kept loading the banned sides into
    #      every solver pool, one forgotten --nofam=SOC away from a ticket.
    #      Now a 3-way group is collapsed to the ONE bettable shape: the
    #      favourite's Double Chance (win or draw), p = 1 - p(underdog). The
    #      feed has no DC market, so the PAYOUT is synthesized: fair odds for
    #      that p with 85% of the excess kept -- the standing FanDuel-haircut
    #      estimate, uncalibrated against real DC prints and labelled
    #      "derived" so nobody quotes it as a book price. The app's print is
    #      the truth (rule 8); this leg exists so the solver can SEE soccer
    #      at all without being handed a draw-loses bet.
    if book == 'FanDuel':
        _soc = {}
        for line in OTHER_RAW.strip().splitlines():
            if not line.strip():
                continue
            sp, grp, who, price, opps, t = line.split('|')
            if sp == 'SOC':
                _soc.setdefault(grp, []).append((who, int(price), opps, t))
                continue
            others = [int(x) for x in opps.split(',')]
            add(('O', grp), p=devig_n(int(price), others), d=dec(price),
                lab=who, price=int(price), grp=grp, fam=sp,
                sport='OTHER', t=t)
        for grp, rows in _soc.items():
            if len(rows) != 3 or not any(w == 'Draw' for w, *_ in rows):
                # not a recognisable 3-way: refuse to guess, and say so
                print(f"  board: soccer group {grp!r} has {len(rows)} outcomes"
                      " -- not a 3-way, no DC derived, group skipped (rule 8)")
                continue
            dog = max((r for r in rows if r[0] != 'Draw'), key=lambda r: r[1])
            fav = next(r for r in rows if r[0] not in ('Draw', dog[0]))
            p_dc = 1 - devig_n(dog[1], [int(x) for x in dog[2].split(',')])
            d_dc = 1 + 0.85 * (1 / p_dc - 1)
            am = round(-100 / (d_dc - 1)) if d_dc < 2 else round(100 * (d_dc - 1))
            add(('O', grp), p=p_dc, d=d_dc, lab=f"{fav[0]} DC (derived)",
                price=am, grp=grp, fam='SOC', sport='OTHER', t=fav[3])

    # ---- MLB moneylines. Keyed to the same ('GT', game) slot as that game's
    #      totals: a team winning and that game's run total are one process
    #      measured twice, exactly the pair an SGP+ engine reprices hardest,
    #      so a solver may take at most one of them.
    if book == 'FanDuel':
        _badcode = set()
        for line in MLBML_RAW.strip().splitlines():
            if not line.strip():
                continue
            t, g, who, price, opp = line.split('|')
            code = who.replace(' ML', '')
            # TEAM3.get(code) is None on ANY spelling drift in the odds feed, and
            # MODEL_P.get(None) is then also None -- so a renamed club looks
            # identical to "this game isn't on the slate". Separate the two: a name
            # the map doesn't know is reported, a known name that simply isn't on
            # today's slate is not.
            if code not in TEAM3:
                _badcode.add(code)
            add(('GT', g), p=devig(int(price), int(opp)), d=dec(price),
                lab=who, price=int(price), grp=g, fam='ML',
                sport='MLB', t=t, mp=model_p(code, g, t))
        if _badcode:
            print(f"  board: {len(_badcode)} moneyline team name(s) not in TEAM3 -- "
                  f"{sorted(_badcode)}. Those legs carry no model opinion.")

    # FEED AGE IS MEASURED BEFORE THE FILTERS, NOT AFTER. It used to be measured
    # after, which meant the one message that says "these prices are days old"
    # was computed over a pool the cutoff had already emptied -- so passing --now,
    # the correct thing to do, SUPPRESSED the warning entirely and left "no ticket
    # meets these constraints" as the only output. That reads as "the board is
    # thin today". It is not: it is that every file in this package is stale.
    # How old the feed is has nothing to do with which price floor a solver asked
    # for, so it is measured over the raw pool.
    _now = _utcnow()
    # 'Z' is the sentinel t for a K leg whose game has no START entry -- not a
    # timestamp. It string-compares greater than any real one, so it would count
    # as "in the future" and hide a dead board. Excluded from the age maths.
    _all_t = sorted(o['t'] for v in markets.values() for o in v if o['t'] != 'Z')
    _live_t = [t for t in _all_t if t > _now]

    for k in list(markets):
        markets[k] = [o for o in markets[k]
                      if o['p'] > 1e-9 and o['d'] > 1.0
                      and not (no_plus and o['price'] > 0)
                      and not (min_price and o['price'] > -min_price)
                      and not (max_price and o['price'] < -max_price)
                      and o['grp'] not in drop
                      and o['fam'] not in drop_fam
                      and not any(x.lower() in o['lab'].lower()
                                  for x in drop_lab)
                      and not (cutoff and o['t'] <= cutoff)
                      # A bare date is padded to the END of that day, not the
                      # start of it: --by=2026-08-09 has to mean "through
                      # Sunday", and '2026-08-09T15:00Z' > '2026-08-09' is True
                      # for every kickoff on the day, so the unpadded compare
                      # deletes the whole horizon date. The K sentinel 'Z' is
                      # greater than any real stamp and would be dropped here,
                      # which is the right answer -- a leg with no known start
                      # cannot be shown to land inside a horizon.
                      and not (horizon and o['t'] > (horizon if len(horizon) > 10
                                                    else horizon + 'T23:59Z'))]
        if not markets[k]:
            del markets[k]

    # STALENESS. Every raw feed in this package (mlbml.py, totals.py, f5.py,
    # mma.py, other.py, times.py) is a hand-pasted snapshot with a date in its
    # docstring and nothing that expires. With the cutoff off, the solver will
    # happily build a 25-leg ticket entirely out of games that finished days ago
    # and report a hit probability for it, because from the DP's point of view
    # nothing is wrong: the prices are real, the de-vig is real, the arithmetic
    # is right. It is answering a question about last Friday.
    global FEED_DEAD
    FEED_DEAD = bool(_all_t) and not _live_t
    if FEED_DEAD:
        # NOT A WARNING. A board on which nothing at all is still to come is not
        # a thin board, it is a dead feed, and the distinction is the difference
        # between "try a lower target" and "repaste the files". Said at feed level
        # so it fires whether or not a cutoff was passed.
        print(f"  board: THE FEED IS DEAD -- all {len(_all_t)} candidate legs "
              f"started before now ({_now}). Newest event on the board is "
              f"{_all_t[-1]}, {_age_h(_all_t[-1], _now)} ago. Every raw file here "
              f"is a hand-pasted snapshot with no expiry: mlbml.py, totals.py, "
              f"f5.py, mma.py, other.py, times.py. Nothing below is bettable at "
              f"the posted price. Repaste the feeds.")
    elif not cutoff and len(_live_t) < len(_all_t):
        print(f"  board: {len(_all_t) - len(_live_t)} of {len(_all_t)} candidate "
              f"legs have ALREADY STARTED (now {_now}, newest event on the board "
              f"{_all_t[-1]}). These are not bettable and the cutoff is OFF -- "
              f"they can appear on the ticket. Drop --anytime to exclude them.")
    return markets


# ---------------------------------------------------------------- selftest
def selftest():
    """python3 board.py --selftest -- checks the MODEL-OPINION plumbing only.

    Every check here is a bug that was live in production on 2026-08-03 and that
    failed SILENTLY: no exception, no warning, just a filter quietly doing the
    opposite of what its docstring promised.
    """
    ok = [0, 0]

    def chk(c, msg):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    global MODEL_P
    _save = MODEL_P
    MODEL_P = {('2026-08-03', 'STL@NYY'): 0.675,
               ('2026-08-03', 'PIT@MIL'): 0.547,
               ('2026-08-02', 'STL@NYY'): 0.400}

    # 23:08Z is 7:08pm ET the SAME day; 01:41Z is 9:41pm ET the PREVIOUS day.
    chk(_et_date("2026-08-03T23:08Z") == "2026-08-03", "an evening UTC start keeps its ET date")
    chk(_et_date("2026-08-04T01:41Z") == "2026-08-03",
        "a post-midnight UTC start belongs to the PREVIOUS ET slate date")

    p = model_p('New York Yankees', 'STL@NYY', '2026-08-03T23:08Z')
    chk(p == 0.675, f"the home side gets p_home ({p})")
    p = model_p('St. Louis Cardinals', 'STL@NYY', '2026-08-03T23:08Z')
    chk(abs(p - 0.325) < 1e-12, f"the away side gets 1 - p_home ({p})")

    # THE BUG. A team-keyed map returned today's number for a game days old.
    chk(model_p('New York Yankees', 'STL@NYY', '2026-07-31T23:08Z') is None,
        "the same matchup on a date the model has no slate for gets NO opinion")

    # THE OTHER HALF OF THE BUG. Same teams, different day of the series -> the
    # OTHER day's number, not today's.
    chk(model_p('New York Yankees', 'STL@NYY', '2026-08-02T23:08Z') == 0.400,
        "a different day of the same series reads that day's number, not today's")

    # doubleheader / second-meeting suffix is a feed disambiguator, not a club code
    chk(model_p('Milwaukee Brewers', 'PIT@MIL2', '2026-08-03T23:08Z') == 0.547,
        "a trailing digit on the game key is stripped, not treated as a team")

    # a leg whose team is not in the matchup is a feed error, not an opinion
    chk(model_p('Chicago Cubs', 'STL@NYY', '2026-08-03T23:08Z') is None,
        "a team not in the matchup gets no opinion")
    chk(model_p('Fake Team', 'STL@NYY', '2026-08-03T23:08Z') is None,
        "an unknown club name gets no opinion, not a crash")

    # the veto-vs-abstain contract solve2 depends on
    keep = lambda mp: mp is None or mp > 0.5
    chk(keep(None) and keep(0.6) and not keep(0.4),
        "--mlagree contract: None abstains, >0.5 keeps, <0.5 vetoes")
    chk(not ((None or 0) > 0.5),
        "and the old expression `(mp or 0) > 0.5` really did veto a None (this is the bug)")

    MODEL_P = _save
    chk(all(isinstance(k, tuple) and len(k) == 2 for k in MODEL_P),
        "the live MODEL_P is keyed by (date, matchup), never by bare team code")

    # ---- FEED AGE. The second silent-production-bug family in this package.
    # A hand-pasted snapshot with no expiry produces a complete, confident ticket
    # made of games that finished days ago, and the only thing that ever stood
    # between that and the screen was remembering to type --now.
    chk(_age_h("2026-08-03T12:00Z", "2026-08-03T20:00Z") == "8h",
        "an eight-hour-old board reads as hours")
    chk(_age_h("2026-07-31T20:00Z", "2026-08-03T20:00Z") == "3.0d",
        "a three-day-old board reads as DAYS, not as 72h nobody converts")
    chk(_age_h("2026-08-01T22:00Z", "2026-08-03T20:00Z") == "46h"
        and _age_h("2026-08-01T19:00Z", "2026-08-03T20:00Z") == "2.0d",
        "and the hour/day switch is at 48h, not at a calendar boundary "
        "(46h stays hours, 49h becomes days)")

    # 'Z' is the sentinel t for a K leg whose game has no START entry. It string-
    # compares greater than every real timestamp, so counting it as a live leg
    # would mask a dead board -- one unmatched pitcher would keep FEED_DEAD False
    # forever. This is the exact shape of the comparison build() makes.
    _now = "2026-08-03T20:00Z"
    chk('Z' > _now, "the K sentinel really does compare as 'in the future' "
                    "(which is why it has to be excluded, not relied on)")
    _ts = ["2026-08-01T22:00Z", "Z", "2026-08-02T03:00Z"]
    chk([t for t in _ts if t != 'Z' and t > _now] == [],
        "a pool of finished legs plus one sentinel counts as ZERO live legs")
    _ts2 = _ts + ["2026-08-04T00:00Z"]
    chk([t for t in _ts2 if t != 'Z' and t > _now] == ["2026-08-04T00:00Z"],
        "and one genuinely future leg is enough to make the board live")

    chk(_utcnow() > "2026-01-01T00:00Z" and _utcnow().endswith('Z')
        and len(_utcnow()) == 17,
        "_utcnow() emits the same 17-char shape every leg's t carries, so the "
        "comparison never needs a parse")

    # ---- HORIZON. The mirror of the cutoff, and the newest member of the same
    # family: a leg that is perfectly valid, perfectly priced, and answers a
    # question about October when the question was about tonight.
    def _keep(t, hz):
        return not (hz and t > (hz if len(hz) > 10 else hz + 'T23:59Z'))

    chk(_keep("2026-08-09T15:00Z", "2026-08-09"),
        "a bare --by date includes fixtures ON that date -- the horizon is the "
        "END of the day, not midnight at the start of it")
    chk(not _keep("2026-08-10T00:30Z", "2026-08-09"),
        "and the very next morning is outside it")
    chk(not _keep("2026-10-31T22:00Z", "2026-08-09"),
        "a leg three months out is excluded, which is the whole point -- it is "
        "the heaviest price on the board and the solver wants it")
    chk(_keep("2026-10-31T22:00Z", None),
        "no --by means no horizon: this is opt-in, not a standing rule")
    chk(not _keep('Z', "2026-08-09"),
        "the K sentinel is OUTSIDE every horizon. A leg whose start is unknown "
        "cannot be shown to land inside one, and 'unknown' must not read as 'soon'")
    chk(_keep("2026-08-09T23:30Z", "2026-08-09T23:59Z"),
        "a full UTC stamp is used as given, not padded")

    # ---- et() PRINTS THE DATE. It did not, and three legs on one ticket
    # labelled 'Sat' were three different Saturdays five weeks apart.
    from times import et as _et, ct as _ct
    chk(_et("2026-08-09T00:00Z") == "Sat 8/8 8:00pm",
        "et() carries the date, so two legs on different Saturdays cannot print "
        "identically")
    chk(_et("2026-08-04T01:41Z") == "Mon 8/3 9:41pm",
        "and a post-midnight UTC start still prints as the previous ET evening")
    # ---- RULE 15 IS ABOUT RYAN'S CLOCK, and every display column printed et().
    chk(_ct("2026-08-09T00:00Z") == "Sat 8/8 7:00pm",
        "ct() is the hour Ryan actually reads -- solve2, daily_report and "
        "ceiling print this, not Eastern")
    chk(_ct("2026-08-13T02:00Z") == "Wed 8/12 9:00pm",
        "Chicago at Golden State: 7:00 Pacific at Chase Center is 9:00 Central, "
        "and the board printed 10:00pm all day")
    chk(_et("2026-08-13T02:00Z") != _ct("2026-08-13T02:00Z"),
        "the two clocks are one hour apart and must never be used interchangeably")

    # ---- HOT GAMES. Written 8/12 from the two slips that died on the same
    # shape two nights running: a mid-rung F5 under on the one game whose run
    # environment was extreme. The information existed both nights.
    _lad = [(8.5, -110, -110), (9.5, -180, 150), (15.5, -1800, 900)]
    chk(_mainline(_lad) == 8.5,
        "the MAIN total is the balanced rung, not the deepest one posted "
        "(U15.5 is a ladder top, and quoting it as 'the total' is the 8/11 "
        "post-mortem's own error)")
    chk(_mainline([]) is None, "no rungs -> None, not a crash")

    _main = {'CHC@WSH': 8.5, 'COL@ARI': 9.5, 'MIL@SD': 7.5, 'PIT@MIA': 6.5}
    _adj = {'CHC@WSH': 10.52, 'COL@ARI': 10.47, 'MIL@SD': 8.32, 'PIT@MIA': 8.90}
    _h = _hot(_main, _adj, slate_fresh=True)
    chk('CHC@WSH' in _h and 'COL@ARI' in _h,
        f"the 8/11 slate's two 10+ adj-total games flag hot ({sorted(_h)})")
    chk('PIT@MIA' in _h,
        "a model 2.4 runs above the market's main flags hot even under 10 "
        "(heat the market has not priced)")
    # (first fixture here used BOS@TOR as the quiet game, with its REAL 8/11
    # numbers -- adj 8.19 vs main 6.5, gap 1.7 -- and the check failed because
    # by this rule's own arithmetic that game was NOT quiet. The code caught
    # the label. MIL@SD, gap 0.8 at Petco, is what quiet actually looks like.)
    chk('MIL@SD' not in _h, "a quiet game does not flag")
    _h2 = _hot(_main, _adj, slate_fresh=False)
    chk(_h2 == {},
        "a STALE slate flags nothing on the model arms -- four-day-old heat "
        "is not tonight's heat")
    _h3 = _hot({'X@Y': 11.0}, {}, slate_fresh=False)
    chk('X@Y' in _h3, "with no slate at all, a market main of 10+ still flags")

    # ---- RULE 8 IN CODE. Until 8/12 the pool carried raw 3-way soccer sides
    # -- the exact bet shape that killed a 20-leg slip on a PSV draw -- and
    # only a remembered --nofam=SOC stood between them and a ticket.
    _m = build('FanDuel', min_price=0)
    _soc = [o for v in _m.values() for o in v if o['fam'] == 'SOC']
    _all = [o for v in _m.values() for o in v]
    chk(not any(o['lab'] == 'Draw' for o in _all),
        "no Draw outcome survives into any pool")
    chk(all('DC (derived)' in o['lab'] for o in _soc),
        f"every soccer offer is a derived Double Chance, never a 3-way side "
        f"({len(_soc)} soccer legs)")
    chk(all(0.5 < o['p'] < 0.995 for o in _soc),
        "derived DC probabilities are favourite-shaped, not draw-shaped")
    chk(all(o['d'] < 1 / o['p'] for o in _soc),
        "the synthesized payout keeps LESS than fair -- the 85% shave is on, "
        "so a derived leg can under-promise but never over-promise")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if '--selftest' in sys.argv else 0)

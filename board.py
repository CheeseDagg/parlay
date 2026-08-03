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
sys.path.insert(0, '/root/parlay')
from totals import TOTALS_RAW, GAME_OF
from f5 import F5_RAW
from mma import MMA_RAW
from other import OTHER_RAW
from mlbml import MLBML_RAW
from times import START, FIGHT_START

LAM = {b['pitcher']: b['lam'] for b in json.load(
    open('/root/MLBTool/mlb/data/kprops.json'))['board']}

# Model win probability for the HOME side of each game on today's slate. Used
# only to AGREE OR DISAGREE with the market, never to replace it: the reported
# probability on a moneyline leg stays the de-vigged price, because a model
# number substituted into a parlay quote would be reporting my own opinion back
# to myself as if it were a fact. Saturday games are not on the slate, so they
# simply carry no model opinion and are neither endorsed nor vetoed.
_SL = json.load(open('/root/MLBTool/mlb/data/slate.json'))
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
MODEL_P = {}
for _g in _SL['games']:
    if _g.get('p_home') is None:
        continue
    _h, _a = TEAM3.get(_g['home']), TEAM3.get(_g['away'])
    if _h and _a:
        MODEL_P[_h] = _g['p_home'] / 100.0
        MODEL_P[_a] = 1 - _g['p_home'] / 100.0


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
          drop_fam=(), drop_lab=(), nostack=False):
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
    the payout shown on the slip would not be the payout offered."""
    markets = {}

    def add(key, **kw):
        markets.setdefault(key, []).append(kw)

    # ---- K legs: Poisson off the kprops lambda, one rung per pitcher
    src = ('/root/parlay/fd_k_ladder.txt' if book == 'FanDuel'
           else '/root/parlay/kraw.txt')
    for line in open(src).read().strip().splitlines():
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
            continue
        g = GAME_OF.get(p, '?')
        add((('GT', g) if nostack else ('K', p)),
            p=pois_sf(int(float(pt) - 0.5), LAM[p]), d=dec(price),
            lab=f"{p} {int(float(pt)+0.5)}+ Ks", price=int(price),
            grp=g, fam='K', sport='MLB', t=START.get(g, 'Z'))

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
    if book == 'FanDuel':
        for line in OTHER_RAW.strip().splitlines():
            if not line.strip():
                continue
            sp, grp, who, price, opps, t = line.split('|')
            others = [int(x) for x in opps.split(',')]
            add(('O', grp), p=devig_n(int(price), others), d=dec(price),
                lab=who, price=int(price), grp=grp, fam=sp,
                sport='OTHER', t=t)

    # ---- MLB moneylines. Keyed to the same ('GT', game) slot as that game's
    #      totals: a team winning and that game's run total are one process
    #      measured twice, exactly the pair an SGP+ engine reprices hardest,
    #      so a solver may take at most one of them.
    if book == 'FanDuel':
        for line in MLBML_RAW.strip().splitlines():
            if not line.strip():
                continue
            t, g, who, price, opp = line.split('|')
            code = who.replace(' ML', '')
            add(('GT', g), p=devig(int(price), int(opp)), d=dec(price),
                lab=who, price=int(price), grp=g, fam='ML',
                sport='MLB', t=t, mp=MODEL_P.get(TEAM3.get(code)))

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
                      and not (cutoff and o['t'] <= cutoff)]
        if not markets[k]:
            del markets[k]
    return markets

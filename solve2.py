"""25-leg single-book solver with a cap on how many baseball legs may be used.

  usage: python3 solve2.py FanDuel 21.0 --minprice=200 --maxmlb=12
         python3 solve2.py FanDuel 21.0 --minprice=200 --sweep
         (started legs are excluded by default; --anytime lifts that)

Why this is not just solve.py with a filter: a cap on one sport is a second
knapsack constraint, and bolting it onto the price DP as a third axis costs
26 x 6092 x 26 floats per market snapshot -- gigabytes. But the two pools are
disjoint by construction (fights share no market key with baseball), so the
problem separates: build an exact "exactly n legs, price bucket b" table for
each pool independently, then convolve the two tables over the split.

Price buckets saturate at the target rather than being clamped per-leg. That
matters for the convolution: a pool that on its own already clears the target
must contribute "no further price needed" to the other pool, and saturation
encodes exactly that, whereas per-leg clamping does not compose.

db uses FLOOR, not round, so every leg's price contribution is understated.
The reported price is therefore a lower bound on the true one -- the ticket can
come in above target, never below. The assertion at the end checks it for real.
"""
import math, sys
from collections import Counter
import numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import board
from board import build
from times import ct

BOOK   = sys.argv[1] if len(sys.argv) > 1 else 'FanDuel'
TARGET = float(sys.argv[2]) if len(sys.argv) > 2 else 21.0
STEP, NEG = 0.0005, -1e18

def flag(name, default=None):
    for a in sys.argv:
        if a.startswith(f'--{name}='):
            return a.split('=', 1)[1]
    return default

# Leg count is a real lever, not cosmetics: fewer legs means each one has to buy
# more price to reach the same target, so a shorter ticket forces LIGHTER
# favourites. Shrinking the ticket and tightening the price floor pull opposite
# ways and both cannot be maximised at once.
N_LEGS = int(flag('legs', 25))

# A GAME THAT HAS ALREADY STARTED IS NOT BETTABLE, so excluding it is not an
# option a caller opts into -- it is what "candidate leg" means. This was `if
# '--now' in sys.argv`, and forgetting the flag did not produce an error or an
# empty result: it produced a complete, confident 25-leg ticket with a headline
# price and a hit probability, built entirely out of games that had finished
# days earlier. It looked exactly like a live ticket. That is the same argument
# the -350 floor below already won, so it gets the same treatment: on by
# default, and --anytime lifts it explicitly for the one legitimate use, which
# is pricing a slip that is already running.
CUTOFF = None if '--anytime' in sys.argv else board._utcnow()
# --now is kept as a no-op alias so an old command line does not silently change
# meaning; it now describes what already happens.
# --from=YYYY-MM-DDTHH:MMZ is the mirror of --by on the NEAR side: "events
# starting after X only". CUTOFF already means exactly that -- its default X is
# simply now -- so a window question ("Saturday only") is the same exclusion
# with a later X, not a second filter. max() keeps it monotone: --from can
# postpone the cutoff, never pull it back before now to resurrect a started
# leg. ISO strings compare lexicographically, same as everywhere else here.
_FROM = flag('from', None)
if _FROM:
    CUTOFF = max(CUTOFF, _FROM) if CUTOFF else _FROM
# The -350 floor is a STANDING constraint ("nothing under -350"), so it is the
# default rather than something to remember to type. It was opt-in, which meant
# the difference between a ticket that respects the rule and one that quietly
# does not was a flag on the command line -- and the violating ticket looked
# exactly as legitimate as the compliant one. --minprice=0 lifts it explicitly.
MINPRICE = int(flag('minprice', 350))
# A promo token can cap how heavy each leg may be. That is a per-leg CEILING,
# the exact mirror of the floor, and it has to be applied at pool construction
# for the same reason: filtering afterwards edits the answer, filtering first
# changes what is being optimised.
MAXPRICE = int(flag('maxprice', 0))
# --by=YYYY-MM-DD is the mirror of the cutoff and it is NOT cosmetic. The board
# now spans August to October, the heaviest prices on it are the furthest out,
# and this solver maximises probability at a price with no notion of "soon" --
# so it will happily hand back a ticket whose last leg is Canelo on 2026-10-31
# while every other line reads like tonight. times.et() now prints the date
# alongside the weekday so the far legs are at least VISIBLE, but visible is not
# excluded -- this flag is what excludes them. Applied at
# pool construction rather than to the answer, for the same reason the price
# floor is: filtering afterwards edits a ticket that was optimised for a
# different question. Off by default -- a horizon is a real choice, not a
# standing rule like -350 is.
HORIZON  = flag('by', None)
MAXMLB   = int(flag("maxmlb", N_LEGS))
DROP     = set(filter(None, (flag('drop', '') or '').split(',')))
DROPFAM  = set(filter(None, (flag('nofam', '') or '').split(',')))
DROPLAB  = [x for x in (flag('noleg', '') or '').split(',') if x]
# --mlagree drops moneyline legs the MLB model DISAGREES with. It is a selection
# filter, not a repricing: the leg's quoted probability stays the de-vigged market
# number either way.
#
# "No opinion" is NOT disagreement. board.py attaches mp=MODEL_P.get(...) and
# documents that a game absent from slate.json "carries no model opinion and is
# neither endorsed nor vetoed" -- but the filter here used to read
# `(o.get('mp') or 0) > 0.5`, and (None or 0) > 0.5 is False, so every leg the
# model had nothing to say about was DELETED. That is a veto, the exact opposite
# of the documented contract, and it fails silently in the worst possible
# direction: MODEL_P is keyed by TEAM3's abbreviation vocabulary, so any spelling
# drift in the raw feed makes every mp None and --mlagree quietly throws away the
# entire moneyline pool with no error. mp is None -> abstain, and the count of
# abstentions is printed so a vocabulary mismatch shows up as a number.
MLAGREE  = '--mlagree' in sys.argv
# DE-VIG: inherit board.py's shipped default. This line used to read
#   board.METHOD = 'power' if '--power' in sys.argv else 'mult'
# which hard-reset the board to 'mult' on every run, silently overriding the
# default board.py and slips.py both declare ('power'). The consequence was two
# tools quoting DIFFERENT probabilities for the SAME leg -- a -5000 favourite
# came out 0.9358 here and 0.9656 in slips/ceiling -- and across a 16-leg ticket
# that compounds into a visibly different headline number with no flag set and
# nothing to indicate which one was meant. One board, one de-vig.
#
# --power / --mult are now explicit overrides, and whichever is in force is
# printed, because a de-vig that changes the answer must not be invisible.
if '--power' in sys.argv:
    board.METHOD = 'power'
elif '--mult' in sys.argv:
    board.METHOD = 'mult'
print(f"de-vig: {board.METHOD}"
      + ("" if ('--power' in sys.argv or '--mult' in sys.argv) else " (board default)"))

markets = build(BOOK, no_plus='--allow-plus' not in sys.argv,
                min_price=MINPRICE, cutoff=CUTOFF, drop=DROP,
                max_price=MAXPRICE, drop_fam=DROPFAM, drop_lab=DROPLAB,
                nostack='--nostack' in sys.argv, horizon=HORIZON)

def _ml_keep(o):
    """Keep unless the model has an opinion AND that opinion is against the leg."""
    if o['fam'] != 'ML':
        return True
    mp = o.get('mp')
    return mp is None or mp > 0.5

if MLAGREE:
    _ml = [o for k in markets for o in markets[k] if o['fam'] == 'ML']
    _noop = sum(1 for o in _ml if o.get('mp') is None)
    _vetoed = sum(1 for o in _ml if not _ml_keep(o))
    for k in list(markets):
        markets[k] = [o for o in markets[k] if _ml_keep(o)]
        if not markets[k]:
            del markets[k]
    print(f"--mlagree: {len(_ml)} ML legs, {_vetoed} vetoed (model disagrees), "
          f"{_noop} with no model opinion (kept)")
    if _ml and _noop == len(_ml):
        print("  WARNING: the model has an opinion on NOTHING. Either no MLB game on "
              "this board is in slate.json, or board.MODEL_P's team vocabulary no "
              "longer matches the raw feed's spellings. --mlagree is a no-op.")

# HOT GAMES: on a game whose run environment is extreme (model adj_total >= 10,
# or the model 1.5+ runs above the market's main total), only the TOP rung of
# the F5 ladder is a candidate. This is RULES.md #25 and it is ON BY DEFAULT
# for the same reason the -350 floor is: it was written from two dead slips on
# consecutive nights (NYM@ATL 8/10, CHC@WSH 8/11), and a rule that has to be
# remembered is a rule that will be skipped on the morning it matters.
# --nohot lifts it explicitly.
if '--nohot' not in sys.argv:
    _hot = board.hot_games(BOOK)
    _capped = []
    for k in list(markets):
        v = markets[k]
        # BOTH totals families. The first version of this capped F5 only, and
        # on 8/12 the solver walked straight through the gap: it put a
        # full-game U12.5 on CHC@WSH -- model 10.82, cushion 1.68 -- at the
        # same -350 that bought 3.22 runs of cushion on SEA@NYY. A hot game is
        # hot for nine innings, not five.
        if v and v[0]['fam'] in ('F5', 'FG') and v[0]['grp'] in _hot and len(v) > 1:
            top = min(v, key=lambda o: o['price'])
            markets[k] = [top]
            _capped.append(f"{v[0]['grp']}: F5 held to {top['lab']} ({top['price']})"
                           f" -- {_hot[v[0]['grp']]}")
    for _c in _capped:
        print(f"hot game, {_c}")

NBT = int(math.ceil(math.log(TARGET) / STEP)); NB = NBT + 1
for k in markets:
    for o in markets[k]:
        o['db'] = min(int(math.floor(math.log(o['d']) / STEP)), NBT)

# The split is baseball vs NOT baseball, not baseball vs fights. Once boxing,
# WNBA, tennis, CFL and soccer joined the board the second pool stopped being
# "the MMA card" and became "everything whose price is not driven by a
# run-scoring process" -- which is also exactly the set that is uncorrelated
# with the MLB legs, so the convolution argument is unchanged.
POOLS = {'MLB':   sorted(k for k in markets if markets[k][0]['sport'] == 'MLB'),
         'FIGHT': sorted(k for k in markets if markets[k][0]['sport'] != 'MLB')}


def tables(keys):
    """A[mi] = value after considering the first mi markets.
    A[mi][n, b] = max sum log p using exactly n legs, price bucket b saturating
    at NBT. Snapshots kept so the pick can be reconstructed backwards."""
    A = np.full((N_LEGS + 1, NB), NEG); A[0, 0] = 0.0
    snaps = [A.copy()]
    for k in keys:
        cur = A.copy()
        for o in markets[k]:
            db, lp = o['db'], math.log(o['p'])
            src = A[:-1]
            sh = np.full_like(src, NEG)
            if db == 0:
                sh[:] = src
            else:
                if db < NB:
                    sh[:, db:] = src[:, :NB - db]
                # everything that would land past the target saturates onto it
                sh[:, NBT] = np.maximum(sh[:, NBT], src[:, NB - db:].max(axis=1)
                                        if NB - db < NB else NEG)
            cur[1:] = np.maximum(cur[1:], np.where(sh < NEG / 2, NEG, sh + lp))
        A = cur; snaps.append(A.copy())
    return snaps


def rebuild(keys, snaps, n, b):
    """Walk the snapshots backwards, peeling off one market at a time."""
    pick = []
    for mi in range(len(keys), 0, -1):
        if n == 0:
            break
        if abs(snaps[mi][n, b] - snaps[mi - 1][n, b]) < 1e-9:
            continue
        for o in markets[keys[mi - 1]]:
            db, lp = o['db'], math.log(o['p'])
            lo = b - db if b < NBT else max(0, NBT - db)
            hi = b - db if b < NBT else NBT
            for pb in range(max(0, lo), hi + 1):
                if abs(snaps[mi][n, b] - (lp + snaps[mi - 1][n - 1, pb])) < 1e-9:
                    pick.append(o); n, b = n - 1, pb; break
            else:
                continue
            break
        else:
            sys.exit(f"reconstruction failed at {keys[mi - 1]}")
    return pick


snapM, snapF = tables(POOLS['MLB']), tables(POOLS['FIGHT'])
AM, AF = snapM[-1], snapF[-1]
# suffix max over price so "at least this much price" is one lookup
SM = np.maximum.accumulate(AM[:, ::-1], axis=1)[:, ::-1]

n_fight_markets = len(POOLS['FIGHT'])


def best_for(min_fight):
    best = (NEG, None, None)
    for m in range(min_fight, min(n_fight_markets, N_LEGS) + 1):
        nm = N_LEGS - m
        if nm > len(POOLS['MLB']):
            continue
        for b1 in range(NB):
            v1 = AF[m, b1]
            if v1 < NEG / 2:
                continue
            need = max(0, NBT - b1)
            v = v1 + SM[nm, need]
            if v > best[0]:
                best = (v, m, b1)
    return best


if '--sweep' in sys.argv:
    print(f"{BOOK}  >= {TARGET:g}x, {N_LEGS} legs, all legs -{MINPRICE} or heavier"
          if MINPRICE else f"{BOOK}  >= {TARGET:g}x, {N_LEGS} legs")
    print(f"{'other':>7s} {'baseball':>9s} {'hit prob':>10s}")
    _rows = 0
    for m in range(0, min(n_fight_markets, N_LEGS) + 1):
        nm = N_LEGS - m
        if nm > len(POOLS['MLB']):
            continue
        v = max((AF[m, b1] + SM[nm, max(0, NBT - b1)] for b1 in range(NB)
                 if AF[m, b1] > NEG / 2), default=NEG)
        if v > NEG / 2:
            _rows += 1
            print(f"{m:>7d} {nm:>9d} {math.exp(v)*100:>9.2f}%")
    # A header over zero rows is the same silent failure as everything else in
    # this package: it looks like a sweep that found nothing interesting rather
    # than a sweep with nothing to sweep.
    if not _rows:
        print("  (no split reaches the target)"
              + ("  -- because not one leg in the raw pool is still to come. "
                 "The feed is stale, not the board thin."
                 if board.FEED_DEAD else
                 "  Loosen the target, the leg count, or --minprice."))
    sys.exit()

MIN_FIGHT = max(0, N_LEGS - MAXMLB)
val, m, b1 = best_for(MIN_FIGHT)
if val < NEG / 2:
    sys.exit(f"No {N_LEGS}-leg {BOOK} ticket meets these constraints.\n"
             f"  in force: {N_LEGS} legs, >= {TARGET:g}x, "
             f"every leg -{MINPRICE} or heavier, max {MAXMLB} baseball"
             + (f", started legs excluded (cutoff {CUTOFF})" if CUTOFF
                else ", STARTED LEGS ALLOWED (--anytime)")
             + "\n  A shorter ticket and a heavier price floor pull against each "
               "other; loosen one. --minprice=0 lifts the floor."
             # "No ticket" and "the feed is three days old" are different
             # problems with opposite fixes, and this line is where the two got
             # confused: the board's dead-feed message prints above and then
             # scrolls, and the reader is left with a sentence that reads like a
             # thin board. Say which one it is, here, last.
             + ("\n  BUT FIRST: not one leg in the raw pool is still to come. "
                "This is not a thin board, it is a stale feed -- repaste "
                "mlbml.py / totals.py / f5.py / mma.py / other.py / times.py."
                if board.FEED_DEAD else ""))

need = max(0, NBT - b1)
b2 = int(np.argmax(AM[N_LEGS - m, need:] >= SM[N_LEGS - m, need] - 1e-12)) + need
pick = rebuild(POOLS['FIGHT'], snapF, m, b1) + \
       rebuild(POOLS['MLB'], snapM, N_LEGS - m, b2)

jp = jd = 1.0
for v in pick:
    jp *= v['p']; jd *= v['d']
assert len(pick) == N_LEGS, f"got {len(pick)} legs"
assert abs(math.log(jp) - val) < 1e-6, f"replay {math.log(jp)} != dp {val}"
assert jd >= TARGET, f"price {jd:.3f}x under target"
# A leg is identified by (label, GAME), not by label alone. Two meetings of the
# same series carry the identical label -- "Pittsburgh Pirates ML" is on the board
# for both PIT@CIN and PIT@CIN2 -- and they are two distinct, separately-settling
# bets that FanDuel will happily take together. Asserting on labels alone aborted
# those tickets with "duplicate leg" even though nothing was duplicated. The real
# invariant is that a solver never takes two options out of one market key, which
# the market-key structure already guarantees; this asserts it rather than assuming.
_ids = [(v['lab'], v['grp']) for v in pick]
assert len(set(_ids)) == N_LEGS, \
    "duplicate leg: " + str([x for x in set(_ids) if _ids.count(x) > 1])
if MINPRICE:
    assert all(v['price'] <= -MINPRICE for v in pick), "leg under price floor"
if MAXPRICE:
    assert all(v['price'] >= -MAXPRICE for v in pick), "leg over price ceiling"
assert sum(1 for v in pick if v['sport'] == 'MLB') <= MAXMLB, "mlb cap broken"
if CUTOFF:
    assert all(v['t'] > CUTOFF for v in pick), "started leg on ticket"

pick.sort(key=lambda v: (v['t'], -v['p']))
hdr = f"{BOOK} -- {N_LEGS} legs, >= {TARGET:g}x, max {MAXMLB} baseball"
if MINPRICE:
    hdr += f", every leg -{MINPRICE} or heavier"
if MAXPRICE:
    hdr += f", every leg -{MAXPRICE} or longer"
print(f"{'='*98}\n{hdr}\n{'='*98}")
print(f"{'#':>2}  {'start (CT)':16s} {'leg':36s} {'price':>7s} {'p(hit)':>8s}  fam")
for i, v in enumerate(pick, 1):
    print(f"{i:2d}  {ct(v['t']):16s} {v['lab']:36s} {v['price']:>+7d} {v['p']:8.4f}  {v['fam']}")
print(f"\n  joint hit probability (independent): {jp:.4f} = {jp*100:.2f}%")
print(f"  parlay price: {jd:.2f}x  (+{round((jd-1)*100)})  ->  $100 returns ${jd*100:,.2f}")
c = Counter(v['grp'] for v in pick)
print("  correlated stacks: " + (", ".join(f"{k}({n})" for k, n in sorted(c.items())
      if n > 1 and v and not k.startswith(('UFC', 'PFL', 'REG'))) or "none"))
print("  family mix: " + str(dict(Counter(v['fam'] for v in pick))))
print(f"  sports: {sum(1 for v in pick if v['sport']!='MLB')} non-baseball, "
      f"{sum(1 for v in pick if v['sport']=='MLB')} baseball")

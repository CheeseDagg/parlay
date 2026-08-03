#!/usr/bin/env python3
"""Grade a set of open parlay slips -- individually and, more importantly,
TOGETHER.

WHY THIS FILE EXISTS.

Slips were being graded by throwaway scripts (/tmp/four.py, /tmp/joint.py,
/tmp/joint2.py, /tmp/last.py), each of which reimplemented the de-vig from
scratch. That is fine once. It is not fine as a habit, because the single most
useful number these scripts ever produced was a CROSS-slip number: on
2026-08-01 five open tickets shared six legs, and the arithmetic said -- before
it happened -- that one fighter losing would kill all five at once. A number
that only exists in a scratch file cannot be checked before the next bet.

WHAT IT ANSWERS.

  1. What is each slip's honest probability of cashing.
  2. Which slips CANNOT both win (opposite sides of the same market).
  3. Which slips are strictly dominated (every leg of A is also on B, so B
     cannot cash unless A does -- A is the same bet with extra risk removed).
  4. P(at least one slip cashes), computed EXACTLY, against the number you
     would get if you wrongly assumed the slips were independent. The gap
     between those two is the whole point.
  5. Which single event is carrying the most tickets -- the expected number of
     slips it kills if it loses. This is the Cepo number.

THE DE-VIG, AND ITS ONE ASSUMPTION.

A slip records the price you took and nothing else, so the opposite side of
each market is usually unknown. Where it is unknown, a typical two-way
overround for that sport is assumed and the synthetic pair is de-vigged. That
assumption is stated, not hidden, and `--sens` re-runs the whole board at
+/-1.5 points of overround so you can see how much it is actually load-bearing.

Power de-vig is the default. Multiplicative de-vig splits the margin in
proportion to implied price, which systematically UNDERSTATES heavy favourites
-- books load more margin on the longshot side. Since these slips are built
almost entirely out of heavy favourites, multiplicative de-vig is biased
against exactly the thing being measured.

Run:
    python3 slips.py                     # grade slips.json
    python3 slips.py <file.json>
    python3 slips.py --sens              # + overround sensitivity
    python3 slips.py --mc                # cross-check the exact math with MC
    python3 slips.py --selftest
"""
import json, math, pathlib, sys
from itertools import combinations

HERE = pathlib.Path(__file__).parent
DEFAULT = HERE / "slips.json"

# Typical two-way overround by sport, used ONLY when a slip does not record the
# opposite side's price. These are round numbers on purpose: pretending to know
# a book's margin to four decimals would be false precision on top of an
# assumption. --sens exists because of that.
MARGIN = {"MMA": 0.045, "BOX": 0.050, "WNBA": 0.038, "NBA": 0.038,
          "MLB": 0.040, "NFL": 0.040, "SOCCER": 0.055, "TENNIS": 0.045,
          "PROP": 0.090}
DEFAULT_MARGIN = 0.050

METHOD = "power"          # power | mult | shin


# ---------------------------------------------------------------- price maths
def dec(american):
    a = float(american)
    if a == 0:
        raise ValueError("0 is not an American price")
    return 1 + (a / 100.0 if a > 0 else 100.0 / -a)


def american(d):
    """Decimal -> American, rounded the way a book prints it."""
    if d <= 1:
        raise ValueError(f"decimal price {d} is not a price")
    return round((d - 1) * 100) if d >= 2 else -round(100 / (d - 1))


def _bisect(f, lo, hi, iters=200):
    flo = f(lo)
    if flo == 0:
        return lo
    if flo * f(hi) > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        if flo * f(mid) <= 0:
            hi = mid
        else:
            lo, flo = mid, f(mid)
    return (lo + hi) / 2


def devig(qs, method=None):
    """Split a book of implied probabilities into true probabilities.

    Written longhand rather than pulled from scipy so this module has no
    dependency beyond the standard library -- a grader you cannot run because
    an import broke is a grader you stop running."""
    method = method or METHOD
    s = sum(qs)
    if s <= 0:
        raise ValueError("empty book")
    if method == "mult" or len(qs) < 2:
        return [q / s for q in qs]
    if method == "power":
        # sum(q^k) = 1. Falls back to multiplicative if any q is not a
        # probability, which happens when a synthetic opposite goes degenerate.
        if any(q <= 0 or q >= 1 for q in qs):
            return [q / s for q in qs]
        k = _bisect(lambda k: sum(q ** k for q in qs) - 1, 1e-3, 40.0)
        return [q / s for q in qs] if k is None else [q ** k for q in qs]
    if method == "shin":
        def f(z):
            return sum((math.sqrt(z * z + 4 * (1 - z) * x * x / s) - z)
                       / (2 * (1 - z)) for x in qs) - 1
        z = _bisect(f, 1e-9, 0.49)
        if z is None:
            return [q / s for q in qs]
        return [(math.sqrt(z * z + 4 * (1 - z) * x * x / s) - z) / (2 * (1 - z))
                for x in qs]
    raise ValueError(f"unknown de-vig method {method!r}")


def leg_prob(price, sport="MMA", opp=None, margin=None, method=None):
    """True probability of one leg.

    If the slip records the opposite side (`opp`), that real two-way book is
    de-vigged and no assumption is needed. Otherwise a synthetic opposite is
    built from the sport's typical overround.

    Props (method-of-victory, alt-round, player totals) are NOT two-way markets
    -- the complement of "wins in round 4+" is a dozen other things -- so the
    synthetic-opposite trick is invalid there and they get the plain margin
    haircut instead. That is the neutral treatment: it neither flatters nor
    punishes them, it just declines to pretend."""
    m = MARGIN.get(sport, DEFAULT_MARGIN) if margin is None else margin
    q = 1.0 / dec(price)
    if opp is not None:
        return devig([q, 1.0 / dec(opp)], method)[0]
    if sport == "PROP" or 1 + m - q >= 1.0 or q >= 1.0:
        return min(q / (1 + m), 1.0)
    return devig([q, 1 + m - q], method)[0]


# ---------------------------------------------------------------- slip model
class Leg:
    """One leg. `mkt` names the market it settles in; two legs sharing a `mkt`
    are two claims about the SAME event, so they are not independent -- they
    are either the same claim, one implying the other, or mutually exclusive.
    `implies` names another outcome in the same market that this one entails
    (Stirling-by-points implies Stirling-wins)."""

    __slots__ = ("lab", "price", "sport", "mkt", "out", "opp", "implies", "t",
                 "game")

    def __init__(self, d):
        if isinstance(d, (list, tuple)):
            d = dict(zip(("lab", "price", "sport", "t"), d))
        self.lab = d["lab"]
        self.price = int(d["price"])
        self.sport = d.get("sport", "MMA")
        self.out = d.get("out") or self.lab
        self.mkt = d.get("mkt") or self.out
        self.opp = d.get("opp")
        self.implies = d.get("implies")
        self.t = d.get("t") or ""
        # `mkt` is a LOGICAL grouping: same market -> one outcome entails or
        # excludes the other, which joint() already handles exactly. `game` is a
        # STATISTICAL one: two legs on the same event in DIFFERENT markets (a
        # team ML and that game's total, a fighter ML and the round group) are
        # not logically linked but are certainly not independent, and the product
        # rule quietly prices them as if they were. Defaulting game to mkt makes
        # every unlabelled leg its own group, so nothing changes until a slip
        # actually says two legs share a game.
        self.game = d.get("game") or self.mkt

    def __repr__(self):
        return f"<{self.out} {self.price:+d}>"


class Slip:
    def __init__(self, d):
        self.name = d["name"]
        self.book = d.get("book", "")
        self.legs = [Leg(x) for x in d["legs"]]
        self.stake = d.get("stake")
        # A book's printed parlay price is authoritative; it is not always the
        # product of the legs (FanDuel FLOORS each contribution, and SGP+
        # reprices correlated legs). When the slip records it, use it.
        self.quoted = d.get("price")

    @property
    def decimal(self):
        if self.quoted is not None:
            return 1 + float(self.quoted) / 100 if float(self.quoted) > 0 \
                else 1 + 100 / -float(self.quoted)
        d = 1.0
        for l in self.legs:
            d *= dec(l.price)
        return d


# ------------------------------------------------- consensus outcome pricing
def consensus(slips, method=None, margins=None):
    """One probability per distinct outcome, averaged over every slip that
    priced it.

    This matters. The same fighter appears on four tickets at -335, -331, -375
    and -355. Grading each ticket off its own number and then combining them
    would have the same event happening at four different rates inside one
    calculation, which is not a model of anything. The consensus table is the
    single source of truth for probability; each slip's own quoted price stays
    the source of truth for PAYOUT, where it is a fact rather than an estimate.
    """
    seen = {}
    for s in slips:
        for l in s.legs:
            mg = None if margins is None else margins.get(l.sport)
            p = leg_prob(l.price, l.sport, l.opp, mg, method)
            seen.setdefault(l.out, {"ps": [], "prices": [], "leg": l})
            seen[l.out]["ps"].append(p)
            seen[l.out]["prices"].append(l.price)
    return {k: {"p": sum(v["ps"]) / len(v["ps"]),
                "spread": (max(v["ps"]) - min(v["ps"])),
                "prices": v["prices"], "leg": v["leg"]}
            for k, v in seen.items()}


def implication_map(slips):
    """outcome -> the outcome it entails (transitively closed one level at a
    time), plus outcome -> market."""
    imp, mkt = {}, {}
    for s in slips:
        for l in s.legs:
            mkt[l.out] = l.mkt
            if l.implies:
                imp[l.out] = l.implies
    return imp, mkt


def game_map(slips):
    """outcome -> the game it settles in (see Leg.game)."""
    return {l.out: l.game for s in slips for l in s.legs}


def _entails(a, b, imp):
    """True if outcome a entails outcome b."""
    seen = set()
    while a is not None and a not in seen:
        if a == b:
            return True
        seen.add(a)
        a = imp.get(a)
    return False


def joint(outcomes, cons, imp, mkt):
    """P(all of these outcomes are true). Exact, not simulated.

    Outcomes in DIFFERENT markets are treated as independent -- that is the
    standing assumption of every parlay price and is not this module's to
    overturn. Outcomes in the SAME market are handled properly: either one
    entails the others (probability = the narrowest one), or they are disjoint
    and the intersection is empty."""
    by_mkt = {}
    for o in outcomes:
        by_mkt.setdefault(mkt.get(o, o), []).append(o)
    p = 1.0
    for group in by_mkt.values():
        if len(group) == 1:
            p *= cons[group[0]]["p"]
            continue
        narrow = next((g for g in group
                       if all(_entails(g, h, imp) for h in group)), None)
        if narrow is None:
            return 0.0          # mutually exclusive; this set cannot happen
        p *= cons[narrow]["p"]
    return p


def slip_prob(slip, cons, imp, mkt):
    return joint([l.out for l in slip.legs], cons, imp, mkt)


def frechet_band(outcomes, cons, imp, mkt, game):
    """(lo, indep, hi) for P(all outcomes true), without assuming anything about
    the dependence between legs on the SAME game.

    joint() multiplies across markets. That is the standing assumption of every
    parlay price, and for legs on different events it is close enough to true.
    For two legs on the SAME event it can be badly wrong in either direction:
    a favourite's ML and that game's under are positively correlated (good
    starting pitching drives both), so the product UNDERSTATES the ticket; the
    same ML and the over are negatively correlated, so the product OVERSTATES it.
    A parlay built out of same-game legs is therefore mispriced by the product
    rule and there is no way to know the sign without a joint model of the game.

    What CAN be said exactly is the Frechet-Hoeffding bound. Within a game group
    of probabilities p_1..p_n the intersection satisfies

        max(0, sum(p_i) - (n-1))  <=  P(all)  <=  min(p_i)

    with no distributional assumption whatsoever. Across game groups the product
    rule is kept -- different events really are close to independent. The result
    is a hard interval containing the truth, reported next to the point estimate
    so the size of the unmodelled risk is visible instead of implied.

    Groups of one collapse to p, so a slip with no same-game legs returns
    (p, p, p) and this costs nothing.
    """
    by_game = {}
    for o in outcomes:
        by_game.setdefault(game.get(o, o), []).append(o)
    lo = hi = 1.0
    for outs in by_game.values():
        p_here = joint(outs, cons, imp, mkt)     # exact within-market handling
        if len(outs) == 1 or p_here == 0.0:
            lo *= p_here
            hi *= p_here
            continue
        # collapse each market inside the game to a single probability first, so
        # entailment/exclusion is not double-counted as statistical dependence
        by_mkt = {}
        for o in outs:
            by_mkt.setdefault(mkt.get(o, o), []).append(o)
        ps = [joint(g, cons, imp, mkt) for g in by_mkt.values()]
        lo *= max(0.0, sum(ps) - (len(ps) - 1))
        hi *= min(ps)
    return lo, joint(outcomes, cons, imp, mkt), hi


def same_game_groups(slip, game):
    """[(game, [labels])] for every game this slip hits more than once."""
    by = {}
    for l in slip.legs:
        by.setdefault(l.game, []).append(l.lab)
    return [(g, ls) for g, ls in by.items() if len(ls) > 1]


def any_hits(slips, cons, imp, mkt):
    """P(at least one slip cashes), by inclusion-exclusion over the slips.

    Exact. 2^k - 1 terms for k slips, and every term is a product of small
    numbers, so there is no cancellation problem at the sizes involved. The
    naive alternative -- 1 - prod(1 - p_i) -- assumes independence and is
    reported alongside precisely so the difference is visible."""
    idx = list(range(len(slips)))
    tot = 0.0
    for r in range(1, len(idx) + 1):
        for comb in combinations(idx, r):
            outs = set()
            for i in comb:
                outs |= {l.out for l in slips[i].legs}
            tot += (-1) ** (r + 1) * joint(outs, cons, imp, mkt)
    return tot


def carry(slips, cons, imp, mkt):
    """-> [(outcome, n_slips_on_it, P(it loses), expected slips killed)].

    The number that mattered on 2026-08-01 and was only ever computed by
    accident. A leg on five tickets at 78% is not a 78% problem, it is an
    expected 1.1 tickets destroyed."""
    rows = []
    for o, v in cons.items():
        n = sum(1 for s in slips if any(l.out == o for l in s.legs))
        # a leg also kills a slip that holds an outcome ENTAILING it
        n += sum(1 for s in slips
                 for l in s.legs
                 if l.out != o and _entails(l.out, o, imp))
        if n == 0:
            continue
        pf = 1 - v["p"]
        rows.append((o, n, pf, n * pf))
    return sorted(rows, key=lambda r: -r[3])


def conflicts(slips, cons, imp, mkt):
    """Pairs of slips that cannot both cash."""
    out = []
    for (i, a), (j, b) in combinations(list(enumerate(slips)), 2):
        outs = {l.out for l in a.legs} | {l.out for l in b.legs}
        if joint(outs, cons, imp, mkt) == 0.0:
            # name the market responsible
            bad = []
            for m in {mkt.get(o, o) for o in outs}:
                g = [o for o in outs if mkt.get(o, o) == m]
                if len(g) > 1 and not any(
                        all(_entails(x, y, imp) for y in g) for x in g):
                    bad.append((m, sorted(g)))
            out.append((a.name, b.name, bad))
    return out


def dominated(slips):
    """(A, B) where B's legs are a strict superset of A's: B cannot cash unless
    A does, so B is A plus pure extra risk."""
    out = []
    S = [(s.name, {l.out for l in s.legs}) for s in slips]
    for (na, sa), (nb, sb) in combinations(S, 2):
        if sa < sb:
            out.append((na, nb, sorted(sb - sa)))
        elif sb < sa:
            out.append((nb, na, sorted(sa - sb)))
    return out


def survival(slip, cons):
    """Legs in start-time order with the probability remaining after each.

    A parlay is not one bet, it is a sequence, and the useful question mid-card
    is 'what is this worth if it is still alive at 9pm'."""
    legs = sorted(slip.legs, key=lambda l: (l.t == "", l.t))
    rows, rem = [], 1.0
    for l in legs:
        rem *= cons[l.out]["p"]
    run = rem
    for l in legs:
        run /= cons[l.out]["p"]
        rows.append((l, cons[l.out]["p"], run))
    return rows


# ---------------------------------------------------------------- reporting
def report(path=DEFAULT, sens=False, mc=False, seq=False, method=None):
    J = json.loads(pathlib.Path(path).read_text())
    slips = [Slip(d) for d in J["slips"] if not d.get("settled")]
    if not slips:
        print("no open slips in " + str(path))
        return 0
    cons = consensus(slips, method)
    imp, mkt = implication_map(slips)
    game = game_map(slips)

    print(f"{'slip':30s} {'legs':>4s} {'price':>10s} {'p(hit)':>8s} "
          f"{'true odds':>11s} {'fair':>8s}")
    sg_any = False
    for s in slips:
        p = slip_prob(s, cons, imp, mkt)
        d = s.decimal
        fair = f"+{american(1/p)}" if p > 0 else "-"
        print(f"{s.name:30s} {len(s.legs):4d} {d:9.2f}x {p*100:7.2f}% "
              f"{('%.0f-1' % (1/p - 1)) if p > 0 else '-':>11s} {fair:>8s}")
        # the point estimate above multiplies across markets. Where a slip hits
        # one game twice that is an assumption, not arithmetic — show the hard
        # bound around it rather than letting the single number stand alone.
        grp = same_game_groups(s, game)
        if grp:
            sg_any = True
            lo, _, hi = frechet_band([l.out for l in s.legs], cons, imp, mkt, game)
            print(f"{'':30s} {'':4s} {'':10s} "
                  f"[{lo*100:5.2f}% .. {hi*100:5.2f}%] correlation band")
            for g, labs in grp:
                print(f"{'':32s} same game '{g}': {', '.join(labs)}")
    if sg_any:
        print("  the band is Frechet-exact: it assumes NOTHING about how the "
              "same-game legs move together.\n  The point estimate assumes they "
              "are independent, which is the one thing they are not.")

    # ---- the cross-slip block: the reason this file exists
    if len(slips) > 1:
        exact = any_hits(slips, cons, imp, mkt)
        ps = [slip_prob(s, cons, imp, mkt) for s in slips]
        indep = 1 - math.prod(1 - p for p in ps)
        print(f"\n  at least one cashes        {exact*100:6.2f}%")
        print(f"  if the slips were independent {indep*100:6.2f}%   "
              f"<- they are not; they share legs")
        print(f"  expected slips won         {sum(ps):.3f}")

        cf = conflicts(slips, cons, imp, mkt)
        if cf:
            print("\n  CANNOT BOTH CASH:")
            for a, b, bad in cf:
                why = "; ".join(f"{m}: {' vs '.join(g)}" for m, g in bad)
                print(f"    {a}  x  {b}   ({why})")

        dm = dominated(slips)
        if dm:
            print("\n  DOMINATED (the second cannot cash unless the first does):")
            for a, b, extra in dm:
                print(f"    {a}  <  {b}   extra legs: {', '.join(extra)}")

        rows = carry(slips, cons, imp, mkt)
        multi = [r for r in rows if r[1] > 1]
        if multi:
            print(f"\n  {'leg carrying the most tickets':32s} {'on':>3s} "
                  f"{'P(loses)':>9s} {'E[slips killed]':>16s}")
            for o, n, pf, e in multi[:8]:
                print(f"    {o:30s} {n:3d} {pf*100:8.1f}% {e:16.2f}")

    # ---- per-slip sequencing (opt-in; it is long)
    if seq:
        for s in slips:
            rows = survival(s, cons)
            print(f"\n  {s.name} -- in order:")
            print(f"    {'leg':30s} {'odds':>7s} {'when':>12s} {'p':>7s} "
                  f"{'still needed after':>19s}")
            for l, p, rem in rows:
                print(f"    {l.lab:30s} {l.price:+7d} {l.t:>12s} {p*100:6.1f}% "
                      f"{rem*100:18.1f}%")

    # ---- where the assumption is doing work
    wide = [(k, v) for k, v in cons.items() if v["spread"] > 0.03]
    if wide:
        print("\n  same event priced very differently across slips:")
        for k, v in sorted(wide, key=lambda x: -x[1]["spread"]):
            print(f"    {k:30s} {v['prices']}  spread {v['spread']*100:.1f}pts")

    if sens:
        print("\noverround sensitivity (every sport shifted together):")
        for d in (-0.015, 0.0, 0.015):
            mg = {k: v + d for k, v in MARGIN.items()}
            c2 = consensus(slips, method, mg)
            ps = [slip_prob(s, c2, imp, mkt) for s in slips]
            a = any_hits(slips, c2, imp, mkt)
            print(f"  {d:+.3f}  " + "  ".join(f"{p*100:5.2f}%" for p in ps)
                  + f"   | any {a*100:5.2f}%")

    if mc:
        print("\nMonte-Carlo cross-check of the exact arithmetic:")
        est = _mc(slips, cons, imp, mkt)
        for s, e in zip(slips, est["slips"]):
            print(f"  {s.name:30s} exact {slip_prob(s,cons,imp,mkt)*100:6.3f}%"
                  f"   mc {e*100:6.3f}%")
        print(f"  {'at least one':30s} exact "
              f"{any_hits(slips,cons,imp,mkt)*100:6.3f}%   mc {est['any']*100:6.3f}%")
    return 0


def _intervals(cons, imp, mkt):
    """Lay each market's outcomes out on [0,1) so that ONE uniform draw settles
    the whole market consistently.

    Sibling outcomes of a market are mutually exclusive, so they get disjoint
    stretches. A nested outcome sits INSIDE its parent's stretch, anchored at
    the same left edge, which makes "by points" automatically a subset of "wins
    the fight" rather than a second independent coin. Rolling one coin per
    outcome -- the obvious implementation -- silently lets a fighter both win
    and lose the same fight, which is how a simulation ends up more optimistic
    than the arithmetic it is supposed to be checking."""
    markets = {}
    for o in cons:
        markets.setdefault(mkt.get(o, o), []).append(o)
    span, over = {}, []
    for m, outs in markets.items():
        def root(o):
            seen = set()
            while imp.get(o) in cons and o not in seen:
                seen.add(o)
                o = imp[o]
            return o
        roots = sorted({root(o) for o in outs}, key=lambda o: -cons[o]["p"])
        start, c = {}, 0.0
        for r in roots:
            start[r] = c
            c += cons[r]["p"]
        if c > 1 + 1e-9:
            over.append((m, round(c, 4)))
        for o in outs:
            span[o] = (start[root(o)], start[root(o)] + cons[o]["p"])
    return span, over


def _mc(slips, cons, imp, mkt, n=400_000, seed=20260803):
    """Independent simulation, used only to prove the closed form."""
    import random
    rng = random.Random(seed)
    span, over = _intervals(cons, imp, mkt)
    for m, c in over:
        print(f"    ! market {m!r} outcomes sum to {c} across slips -- the "
              f"books disagree; MC clips, the exact maths does not")
    markets = {}
    for o in cons:
        markets.setdefault(mkt.get(o, o), []).append(o)
    hits, anyh = [0] * len(slips), 0
    legsets = [{l.out for l in s.legs} for s in slips]
    for _ in range(n):
        w = {}
        for m, outs in markets.items():
            u = rng.random()
            for o in outs:
                lo, hi = span[o]
                w[o] = lo <= u < hi
        got = [all(w[o] for o in ls) for ls in legsets]
        for i, g in enumerate(got):
            hits[i] += g
        anyh += any(got)
    return {"slips": [h / n for h in hits], "any": anyh / n}


# ---------------------------------------------------------------- selftest
def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(abs(dec(-200) - 1.5) < 1e-12, "-200 is 1.50x")
    chk(abs(dec(+150) - 2.5) < 1e-12, "+150 is 2.50x")
    chk(american(2.5) == 150 and american(1.5) == -200, "American round-trips")

    # a matched book de-vigs to something summing to exactly 1
    for meth in ("mult", "power", "shin"):
        got = devig([1 / dec(-200), 1 / dec(+170)], meth)
        chk(abs(sum(got) - 1) < 1e-9, f"{meth} de-vig sums to 1")

    # the favourite-longshot direction: power must be kinder to the favourite
    # than multiplicative. This is the whole reason power is the default.
    pm = devig([1 / dec(-5000), 1 / dec(+1400)], "mult")[0]
    pp = devig([1 / dec(-5000), 1 / dec(+1400)], "power")[0]
    chk(pp > pm, f"power favours the heavy favourite over mult ({pp:.4f}>{pm:.4f})")

    # a real opposite price must override the assumed overround
    a = leg_prob(-200, "MMA", opp=+170)
    b = leg_prob(-200, "MMA")
    chk(a != b, "a recorded opposite price is used instead of the assumption")

    # props take the haircut, never a synthetic two-way
    chk(abs(leg_prob(+1100, "PROP") - (1 / dec(1100)) / 1.09) < 1e-12,
        "a prop leg gets the plain margin haircut")
    chk(leg_prob(-5000, "BOX") < 1.0, "a huge favourite stays below 1")

    # ---- the joint machinery
    S = [Slip({"name": "A", "legs": [
             {"lab": "X", "price": -200}, {"lab": "Y", "price": -300}]}),
         Slip({"name": "B", "legs": [
             {"lab": "X", "price": -200}, {"lab": "Z", "price": -400}]})]
    cons = consensus(S)
    imp, mkt = implication_map(S)
    pA, pB = slip_prob(S[0], cons, imp, mkt), slip_prob(S[1], cons, imp, mkt)
    chk(abs(pA - cons["X"]["p"] * cons["Y"]["p"]) < 1e-12,
        "a slip is the product of its legs")
    ex = any_hits(S, cons, imp, mkt)
    want = cons["X"]["p"] * (1 - (1 - cons["Y"]["p"]) * (1 - cons["Z"]["p"]))
    chk(abs(ex - want) < 1e-12, "shared-leg union is exact, not 1-prod(1-p)")
    chk(ex < 1 - (1 - pA) * (1 - pB),
        "sharing a leg makes at-least-one WORSE than independence implies")

    # mutual exclusion
    C = [Slip({"name": "A", "legs": [
             {"lab": "medic", "mkt": "MR", "price": -200}]}),
         Slip({"name": "B", "legs": [
             {"lab": "rodriguez", "mkt": "MR", "price": +160}]})]
    cons2 = consensus(C)
    imp2, mkt2 = implication_map(C)
    chk(joint(["medic", "rodriguez"], cons2, imp2, mkt2) == 0.0,
        "two outcomes of one market cannot both happen")
    chk(len(conflicts(C, cons2, imp2, mkt2)) == 1,
        "the conflicting pair is reported")

    # nesting: by-points implies the win, so both together = by-points
    N = [Slip({"name": "A", "legs": [
        {"lab": "win", "price": -300, "mkt": "F"},
        {"lab": "pts", "price": +105, "mkt": "F", "sport": "PROP",
         "implies": "win"}]})]
    cn = consensus(N)
    im, mk = implication_map(N)
    chk(abs(joint(["win", "pts"], cn, im, mk) - cn["pts"]["p"]) < 1e-12,
        "a nested outcome absorbs its parent instead of multiplying by it")

    # domination
    D = [Slip({"name": "small", "legs": [{"lab": "X", "price": -200}]}),
         Slip({"name": "big", "legs": [{"lab": "X", "price": -200},
                                       {"lab": "Y", "price": -200}]})]
    dm = dominated(D)
    chk(dm and dm[0][0] == "small" and dm[0][1] == "big",
        "a strict superset slip is flagged as dominated")

    # carry: a leg on both slips has E[killed] = 2*(1-p)
    cd = consensus(D)
    idd, mkd = implication_map(D)
    row = [r for r in carry(D, cd, idd, mkd) if r[0] == "X"][0]
    chk(row[1] == 2 and abs(row[3] - 2 * (1 - cd["X"]["p"])) < 1e-12,
        "the shared leg's expected kill count is n*(1-p)")

    # ---- closed form vs simulation, on a board with nesting AND exclusion
    W = {"lab": "win", "price": -300, "mkt": "F", "opp": 220}
    M = [Slip({"name": "T1", "legs": [
             {"lab": "a", "price": -300}, {"lab": "b", "price": -250},
             {"lab": "pts", "price": +105, "mkt": "F", "sport": "PROP",
              "implies": "win"}, dict(W)]}),
         Slip({"name": "T2", "legs": [
             {"lab": "a", "price": -300}, {"lab": "c", "price": -400},
             dict(W)]}),
         Slip({"name": "T3", "legs": [
             {"lab": "b", "price": -250},
             {"lab": "lose", "mkt": "F", "price": 220, "opp": -300}]})]
    cm = consensus(M)
    imm, mkm = implication_map(M)
    est = _mc(M, cm, imm, mkm, n=300_000, seed=11)
    exact = [slip_prob(s, cm, imm, mkm) for s in M]
    for s, e, x in zip(M, est["slips"], exact):
        chk(abs(e - x) < 0.004, f"MC matches exact for {s.name} "
                                f"({e*100:.2f}% vs {x*100:.2f}%)")
    chk(abs(est["any"] - any_hits(M, cm, imm, mkm)) < 0.005,
        f"MC matches exact for at-least-one "
        f"({est['any']*100:.2f}% vs {any_hits(M,cm,imm,mkm)*100:.2f}%)")
    chk(joint(["win", "lose"], cm, imm, mkm) == 0.0,
        "opposite sides of the same fight are exclusive across slips")

    # ---- regression: the 2026-08-01 'last hope' slip must reprice to what the
    # throwaway script said, so folding those scripts in changed no number.
    LAST = {"name": "16-leg last hope", "price": 1319, "legs": [
        {"lab": "Rakic ML", "price": -390, "sport": "MMA"},
        {"lab": "Pattinson ML", "price": -380, "sport": "BOX"},
        {"lab": "Stirling BY POINTS", "price": 105, "sport": "PROP"},
        {"lab": "Barney-Smith ML", "price": -650, "sport": "BOX"},
        {"lab": "Medic ML", "price": -400, "sport": "MMA"},
        {"lab": "Kaleiopu ML", "price": -3000, "sport": "BOX"},
        {"lab": "Cabrera ML", "price": -5000, "sport": "BOX"},
        {"lab": "Guzman ML", "price": -1600, "sport": "BOX"},
        {"lab": "Capetillo ML", "price": -4500, "sport": "BOX"},
        {"lab": "Iriarte ML", "price": -5000, "sport": "BOX"},
        {"lab": "Conwell ML", "price": -650, "sport": "BOX"},
        {"lab": "Curiel ML", "price": -1300, "sport": "BOX"},
        {"lab": "Muratalla ML", "price": -1300, "sport": "BOX"},
        {"lab": "Minnesota Lynx ML", "price": -220, "sport": "WNBA"},
        {"lab": "Dallas Wings ML", "price": -650, "sport": "WNBA"},
        {"lab": "Golden St Valkyries ML", "price": -650, "sport": "WNBA"}]}
    L = [Slip(LAST)]
    cl = consensus(L)
    il, ml_ = implication_map(L)
    p = slip_prob(L[0], cl, il, ml_)
    chk(abs(p * 100 - 5.19) < 0.02,
        f"the 2026-08-01 16-leg slip still grades 5.19% (got {p*100:.2f}%)")
    chk(abs(L[0].decimal - 14.19) < 0.02,
        f"and still prices 14.19x (got {L[0].decimal:.2f}x)")

    # ---- Frechet-Hoeffding same-game band
    # (a) COST NOTHING when nothing is labelled. Every leg above defaults game=mkt,
    # so each is its own group and the band must collapse onto the point estimate.
    gl = game_map(L)
    lo, ind, hi = frechet_band([l.out for l in L[0].legs], cl, il, ml_, gl)
    chk(abs(lo - p) < 1e-12 and abs(ind - p) < 1e-12 and abs(hi - p) < 1e-12,
        "with no same-game labels the band collapses to the point estimate")
    chk(same_game_groups(L[0], gl) == [],
        "and no same-game group is reported")

    # (b) two legs on ONE game in DIFFERENT markets: the band must be the exact
    # Frechet interval and must strictly contain the independence product.
    G = [Slip({"name": "SGP", "legs": [
        {"lab": "Team ML", "price": -300, "mkt": "ml", "game": "g1"},
        {"lab": "Under 44.5", "price": -110, "mkt": "tot", "game": "g1"}]})]
    cg = consensus(G)
    ig, mg = implication_map(G)
    gg = game_map(G)
    p1 = cg["Team ML"]["p"]; p2 = cg["Under 44.5"]["p"]
    lo, ind, hi = frechet_band(["Team ML", "Under 44.5"], cg, ig, mg, gg)
    chk(abs(lo - max(0.0, p1 + p2 - 1)) < 1e-12,
        f"lower bound is max(0, p1+p2-1) ({lo:.4f})")
    chk(abs(hi - min(p1, p2)) < 1e-12, f"upper bound is min(p1,p2) ({hi:.4f})")
    chk(abs(ind - p1 * p2) < 1e-12, "the middle value is still the product rule")
    chk(lo < ind < hi, f"and the product sits strictly inside ({lo:.4f} < "
                       f"{ind:.4f} < {hi:.4f})")
    chk([g for g, _ in same_game_groups(G[0], gg)] == ["g1"],
        "the same-game group is reported by name")

    # (c) same game, SAME market, opposite sides: exclusion wins before any
    # bound is taken. A band of [0,0] is the only correct answer here — the old
    # product rule would have quoted a positive number.
    X = [Slip({"name": "impossible", "legs": [
        {"lab": "home ML", "price": -150, "mkt": "g1ml", "game": "g1"},
        {"lab": "away ML", "price": +130, "mkt": "g1ml", "game": "g1"}]})]
    cx = consensus(X)
    ix, mx = implication_map(X)
    gx = game_map(X)
    lo, ind, hi = frechet_band(["home ML", "away ML"], cx, ix, mx, gx)
    chk(lo == 0.0 and ind == 0.0 and hi == 0.0,
        "two sides of one market band to exactly [0,0], not a product")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    src = next((x for x in a if not x.startswith("-")), DEFAULT)
    sys.exit(report(src, sens="--sens" in a, mc="--mc" in a,
                    seq="--seq" in a))

"""fights.py — method-of-victory pricing that cannot repeat 8/11.

That night I overrode de-vigged fight prices by 10+ points four times, off
career tallies read from search snippets, and went 1-for-4. The market's
number beat mine on Kunneman, on the Hasan round-1 fade, and on the
Escarrega decision fade. This module is the mechanical form of the rules
written from that (RULES.md 23 and 27):

  * If a METHOD MARKET EXISTS, its de-vigged price IS the probability.
    from_quote() is the only sanctioned reading of it.
  * If no market exists, the fallback is the divisional base rate SHRUNK
    toward the fighter's career split — never the raw career tally. A 6-KO
    -in-8 record at flyweight is eight fights of signal, not a 75% truth.
  * Any hand override of a market number passes through clamp(), which caps
    it at five points. The 8/11 tally says my overrides past five points
    carry no information.

Self-contained on purpose: board.py's power de-vig is for the two-way board;
method props arrive as single quoted prices from the app, usually with no
opposing side to pair against.
"""
import sys

def dec(am):
    am = float(am)
    return 1 + (am / 100.0 if am > 0 else 100.0 / -am)

def from_quote(am, overround=0.02):
    """A single-sided method quote -> probability. The 2% haircut is the
    typical one-sided share of a method market's overround; without the
    opposing prices there is nothing better to anchor to, and pretending the
    raw implied is clean flatters every leg."""
    return (1.0 / dec(am)) / (1 + overround)

def clamp(market_p, my_p, cap=0.05):
    """RULES.md #23. Research adjusts a de-vigged price by five points at
    most. Beyond that, the 8/11 ledger says the market was right and I was
    loud."""
    lo, hi = market_p - cap, market_p + cap
    return max(lo, min(hi, my_p))

# Method-of-victory split OF WINS (ko, sub, dec) by division. Coarse UFC-era
# base rates: finish likelihood rises with weight, decisions dominate the
# small divisions. These are PRIORS for when no market exists — nothing here
# outranks a posted price.
PRIOR = {
    'HW':  (0.58, 0.12, 0.30),
    'LHW': (0.50, 0.14, 0.36),
    'MW':  (0.42, 0.16, 0.42),
    'WW':  (0.34, 0.17, 0.49),
    'LW':  (0.29, 0.18, 0.53),
    'FW':  (0.27, 0.17, 0.56),
    'BW':  (0.24, 0.18, 0.58),
    'FLW': (0.21, 0.19, 0.60),
    'W':   (0.14, 0.16, 0.70),   # women's rows pooled: decisions dominate
}

def method_split(division, career=None):
    """(p_ko, p_sub, p_dec) GIVEN a win. career=(ko, sub, dec) counts.

    Shrinkage weight n/(n+8): a debutant is all prior, eight fights is an
    even blend, twenty fights mostly speaks for itself. Eight is one career
    of the kind that reaches a Contender Series card — exactly the sample
    size that fooled me on 8/11, which is why it only ever gets half a vote.
    """
    pk, ps, pd = PRIOR[division]
    if not career or sum(career) == 0:
        return (pk, ps, pd)
    n = sum(career)
    w = n / (n + 8.0)
    ck, cs, cd = (c / n for c in career)
    out = (w * ck + (1 - w) * pk,
           w * cs + (1 - w) * ps,
           w * cd + (1 - w) * pd)
    s = sum(out)
    return tuple(x / s for x in out)

def p_method(win_p, division, career=None):
    """{'ko','sub','dec'} -> outright probability of winner-by-that-method,
    for when NO method market is posted. win_p is the de-vigged moneyline."""
    k, s, d = method_split(division, career)
    return {'ko': win_p * k, 'sub': win_p * s, 'dec': win_p * d}


def selftest():
    ok = [0, 0]
    def chk(c, msg):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    p = from_quote(-425)
    chk(abs(p - 0.7937) < 0.001,
        f"the 8/11 Hasan-by-KO quote (-425) reads {p:.4f} -- the market's "
        "number, which was RIGHT (KO round 1)")
    chk(abs(from_quote(150) - 0.3922) < 0.001,
        "a plus quote de-vigs through the same single haircut")

    chk(abs(clamp(0.70, 0.50) - 0.65) < 1e-9 and abs(clamp(0.70, 0.90) - 0.75) < 1e-9,
        "a ten-plus-point override is held to five, both directions")
    chk(clamp(0.70, 0.72) == 0.72, "inside the cap, the estimate stands")

    chk(PRIOR['HW'][0] > PRIOR['MW'][0] > PRIOR['LW'][0] > PRIOR['FLW'][0],
        "KO share falls with weight class, monotone through the divisions")
    chk(all(abs(sum(v) - 1) < 1e-9 for v in PRIOR.values()),
        "every divisional split sums to 1")

    chk(method_split('FLW', (0, 0, 0)) == PRIOR['FLW'],
        "a debutant is all prior")
    k8 = method_split('FLW', (6, 1, 1))[0]
    chk(abs(k8 - 0.5 * (0.75 + 0.21)) < 1e-9,
        f"Hasan's actual 8-fight career (6 KO) blends to {k8:.2f} KO-given-win "
        "-- NOT the 0.75 raw tally I treated as truth, and NOT the 0.60 I "
        "flip-flopped to. Eight fights, half a vote.")
    k30 = method_split('FLW', (22, 4, 4))[0]
    chk(k30 > k8, "a thirty-fight career outranks the prior more than an "
                  "eight-fight one")

    pm = p_method(0.966, 'HW', (4, 1, 1))
    chk(abs(sum(pm.values()) - 0.966) < 1e-9,
        "method probabilities partition the win probability exactly")
    chk(pm['ko'] < 0.667,
        f"Wint-by-KO off his real record prices {pm['ko']:.2f} -- the -200 "
        "round-1-KO leg (66.7% implied) was unbettable even BEFORE the "
        "round restriction")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest())

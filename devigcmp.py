"""Is the hit-probability comparison itself biased against heavy favourites?

Multiplicative de-vig splits the overround in proportion to implied price. That
is known to be wrong in a specific direction: books load more margin onto the
longshot side (favourite-longshot bias), so a -7000 favourite's true win rate is
HIGHER than proportional de-vig says. Every heavy leg on the placed ticket is
therefore understated, and every light leg on the capped tickets is barely
touched -- the distortion is largest exactly where the two tickets differ.

So the comparison gets redone under two de-vig methods that correct for it:

  power  : find k with sum(q_i^k) = 1, p_i = q_i^k. Raising a number below 1 to
           a power > 1 shrinks it, and shrinks the SMALL numbers proportionally
           more, so margin comes off the longshot first.
  Shin   : models the overround as the book protecting itself against insiders,
           solving for the insider fraction z. Standard correction for exactly
           this bias and generally the more aggressive of the two on big prices.

Nothing here is about expected value. All three methods answer one question:
what is P(every leg wins).
"""
import math
from scipy.optimize import brentq

def D(a):
    a = float(a); return 1 + (a/100 if a > 0 else 100/-a)

def mult(prices):
    q = [1/D(a) for a in prices]; s = sum(q)
    return [x/s for x in q]

def power(prices):
    q = [1/D(a) for a in prices]
    k = brentq(lambda k: sum(x**k for x in q) - 1, 0.2, 5.0)
    return [x**k for x in q]

def shin(prices):
    q = [1/D(a) for a in prices]; s = sum(q)
    def f(z):
        return sum((math.sqrt(z*z + 4*(1-z)*x*x/s) - z) / (2*(1-z))
                   for x in q) - 1
    lo, hi = 1e-9, 0.49
    if f(lo)*f(hi) > 0:
        return mult(prices)
    z = brentq(f, lo, hi)
    return [(math.sqrt(z*z + 4*(1-z)*x*x/s) - z)/(2*(1-z)) for x in q]

# ---- the tickets, as matched books. Selection is always the first price.
PLACED = [(-700,470),(-350,265),(-700,470),(-335,265),(-3500,1400),(-7000,2200),
          (-560,400),(-340,260),(-520,380),(-335,270),(-5000,1400),(-3000,890),
          (-5000,1400),(-750,520),(-450,350),(-360,285),(-350,270),(-335,270),
          (-650,400),(-1300,860)]
A = [(-162,136),(-154,126),(-120,102),(-200,168),(-158,134),(-132,114)]
D6 = [(-184,170),(-142,132),(-128,120),(-160,148),(-126,118),(-184,170)]
F6 = [(-184,170),(-128,120),(-128,120),(-200,168),(-158,134),(-132,114)]

def joint(book, method):
    p = 1.0
    for pair in book:
        p *= method(list(pair))[0]
    return p

print(f"{'ticket':34s} {'legs':>4s} {'multipl.':>9s} {'power':>9s} {'Shin':>9s}")
for name, bk in [("placed +2050, 20 heavy favourites", PLACED),
                 ("A  6 legs, zero baseball", A),
                 ("D  6 legs, all moneyline", D6),
                 ("F  6 legs, mixed", F6)]:
    print(f"{name:34s} {len(bk):>4d} "
          f"{joint(bk,mult)*100:>8.2f}% {joint(bk,power)*100:>8.2f}% "
          f"{joint(bk,shin)*100:>8.2f}%")

print("\nper-leg detail on the four heaviest legs of the placed ticket:")
for pair in [(-7000,2200),(-5000,1400),(-3500,1400),(-1300,860)]:
    print(f"  {pair[0]:>+6d} : mult {mult(list(pair))[0]:.4f}   "
          f"power {power(list(pair))[0]:.4f}   Shin {shin(list(pair))[0]:.4f}")
print("per-leg detail on the light legs:")
for pair in [(-184,170),(-160,148),(-128,120)]:
    print(f"  {pair[0]:>+6d} : mult {mult(list(pair))[0]:.4f}   "
          f"power {power(list(pair))[0]:.4f}   Shin {shin(list(pair))[0]:.4f}")

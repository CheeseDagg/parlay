#!/usr/bin/env python3
"""calib.py -- turn a projection into a probability, the way the data says to.

    python3 calib.py --selftest
    from calib import Model; m = Model(rows); m.p(stat, proj, vol, bar, side, opp, pos)

WHY THIS EXISTS, AND WHAT IT REPLACES.

Every prop I handed Ryan for two weeks was priced with the same two moves: take
the player's own hit rate at the posted number, then cut it down if the opposing
defence looked stingy at that number. Both moves are wrong, and five seasons of
out-of-sample testing says so at every bar.

1. A PLAYER'S OWN HIT RATE OVER-PREDICTS, and worst exactly where we bet. At a
   trailing volume of 4-6 targets it runs +5.8 points hot; at 6-8, +8.2; at 8+,
   +11.8. Juwan Johnson read 77% on his own 13 games against a 61.5% price and
   the honest number was 61%. Brock Purdy read 42% over two seasons against a
   33.6% price and his career was 24%.

2. THE DEFENSIVE MATCHUP IS WORTH 15% OF ITS FACE VALUE, not 100%. Tested as
   adj = cal * (1 + alpha * (defence_rate/league_rate - 1)), the Brier score
   bottoms out at alpha=0.15 for receiving and 0.30 for rushing, and at
   alpha=1.0 -- which is what "rank on the weaker of form and matchup" amounts
   to -- it is substantially WORSE than ignoring the defence altogether
   (0.1477 against 0.1373 at receptions 3.5). Every "Cincinnati has let 15 of
   20 receivers clear this" line I ever quoted deserved a seventh of the weight
   I gave it.

WHAT WORKS INSTEAD. Project the stat as trailing volume x trailing efficiency,
then read the probability off what actually happened to every comparable
projection in the league, then correct that bucket for its bias in the player's
volume band, then nudge it 15% toward the matchup. Scores by Brier, five
seasons, leave-one-player-out:

    receptions 3.5   own .1451   cal .1373   shrunk .1388   cal+bias .1371
    rec yards 69.5   own .0789   cal .0735   shrunk .0747   cal+bias .0734
    rush yds  87.5   own .0817   cal .0820   shrunk  --     cal+bias .0814

Shrinking the own-rate toward the calibration is WORSE than dropping it
entirely, which is the part I would not have guessed: the player's own history
adds nothing once his projection is known.
"""
import bisect, sys
from collections import defaultdict

ALPHA = {"rushing_yards": 0.30, "carries": 0.30}   # everything else:
ALPHA_DEFAULT = 0.15
WIN = 0.15          # +/- 15% of the projection defines "comparable"
MIN_BUCKET = 30     # below this the bucket cannot speak
MIN_DEF = 10        # games before a defence's own rate is usable


class Model:
    """Built from rows of (player, projection, volume, outcome, opp, pos, season)."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r[1])
        self.projs = [r[1] for r in self.rows]
        vols = sorted(r[2] for r in self.rows)
        self.qs = [vols[int(len(vols) * f)] for f in (0.25, 0.5, 0.75, 0.90)] if vols else []

    def vbucket(self, vol):
        return sum(1 for q in self.qs if vol >= q)

    def _bucket(self, proj, bar, drop_player=None):
        lo = bisect.bisect_left(self.projs, proj * (1 - WIN))
        hi = bisect.bisect_right(self.projs, proj * (1 + WIN))
        sel = [r for r in self.rows[lo:hi] if r[0] != drop_player]
        if len(sel) < MIN_BUCKET:
            return None, 0
        h = sum(1 for r in sel if r[3] > bar)
        return h / len(sel), len(sel)

    def bias(self, stat, bar):
        """How much the raw bucket over-predicts, per volume band."""
        acc = defaultdict(lambda: [0.0, 0])
        for r in self.rows:
            cal, n = self._bucket(r[1], bar, drop_player=r[0])
            if cal is None:
                continue
            b = acc[self.vbucket(r[2])]
            b[0] += cal - (1.0 if r[3] > bar else 0.0)
            b[1] += 1
        return {k: (v[0] / v[1] if v[1] else 0.0) for k, v in acc.items()}

    def defence(self, bar):
        """(season, opponent, position) -> its own rate at this bar, and the
        league rate to measure it against."""
        s = defaultdict(float); n = defaultdict(int)
        for r in self.rows:
            k = (r[6], r[4], r[5])
            s[k] += 1.0 if r[3] > bar else 0.0
            n[k] += 1
        league = sum(1 for r in self.rows if r[3] > bar) / max(1, len(self.rows))
        return {k: s[k] / n[k] for k in n if n[k] >= MIN_DEF}, league

    def p(self, stat, proj, vol, bar, side="Over", bias=None, defn=None,
          league=None, opp=None, pos=None, drop_player=None):
        """Probability this clears (or stays under) the bar. None if unknowable."""
        cal, n = self._bucket(proj, bar, drop_player=drop_player)
        if cal is None:
            return None, 0
        if bias is not None:
            cal = cal - bias.get(self.vbucket(vol), 0.0)
        if defn is not None and league and opp and pos and (opp, pos):
            dr = defn.get((None, opp, pos))
            if dr is None:
                # caller may key by season; try any season for this pair
                cands = [v for k, v in defn.items() if k[1] == opp and k[2] == pos]
                dr = sum(cands) / len(cands) if cands else None
            if dr is not None:
                a = ALPHA.get(stat, ALPHA_DEFAULT)
                cal = cal * (1 + a * (dr / max(1e-9, league) - 1))
        cal = min(0.99, max(0.01, cal))
        return (cal if side == "Over" else 1.0 - cal), n


def selftest():
    f = 0

    def ck(c, m):
        nonlocal f
        if not c:
            print(f"  FAIL {m}"); f += 1

    # a bucket of 100 rows, 60 of them over the bar
    rows = [(f"p{i}", 10.0, 5.0, 12.0 if i < 60 else 3.0, "XXX", "WR", 2026)
            for i in range(100)]
    m = Model(rows)
    p, n = m.p("receptions", 10.0, 5.0, 5.0)
    ck(abs(p - 0.60) < 0.02 and n >= 99, f"bare bucket {p} {n}")
    pu, _ = m.p("receptions", 10.0, 5.0, 5.0, side="Under")
    ck(abs(pu - 0.40) < 0.02, f"under is the complement: {pu}")

    # a projection far from every row must refuse rather than guess
    p2, n2 = m.p("receptions", 1000.0, 5.0, 5.0)
    ck(p2 is None, f"no comparable bucket must return None, got {p2}")

    # leave-one-out actually drops the player
    rows2 = rows + [("solo", 10.0, 5.0, 99.0, "XXX", "WR", 2026)]
    m2 = Model(rows2)
    a, _ = m2.p("receptions", 10.0, 5.0, 5.0)
    b, _ = m2.p("receptions", 10.0, 5.0, 5.0, drop_player="solo")
    ck(a != b, "dropping a player must change the bucket")

    # the bias correction must move the answer DOWN when the bucket runs hot
    bias = {m.vbucket(5.0): 0.10}
    p3, _ = m.p("receptions", 10.0, 5.0, 5.0, bias=bias)
    ck(abs(p3 - 0.50) < 0.02, f"bias of +0.10 must subtract: {p3}")

    # the opponent nudge must be 15% of the way, not the whole way
    defn = {(2026, "SOFT", "WR"): 0.90}
    p4, _ = m.p("receptions", 10.0, 5.0, 5.0, defn=defn, league=0.60,
                opp="SOFT", pos="WR")
    want = 0.60 * (1 + 0.15 * (0.90 / 0.60 - 1))
    ck(abs(p4 - want) < 0.01, f"alpha must be 0.15: got {p4}, want {want}")
    ck(p4 < 0.70, "a 50%-more-generous defence must not move it 50%")
    # rushing gets a bigger alpha, and that must be visible
    p5, _ = m.p("rushing_yards", 10.0, 5.0, 5.0, defn=defn, league=0.60,
                opp="SOFT", pos="WR")
    ck(p5 > p4, f"rushing alpha 0.30 must move further than 0.15: {p5} vs {p4}")
    # ...and a stingy defence must move it the other way
    defn2 = {(2026, "HARD", "WR"): 0.30}
    p6, _ = m.p("receptions", 10.0, 5.0, 5.0, defn=defn2, league=0.60,
                opp="HARD", pos="WR")
    ck(p6 < 0.60, f"a stingy defence must reduce it: {p6}")
    # probabilities stay in bounds even with an absurd defence
    defn3 = {(2026, "MAD", "WR"): 1.0}
    p7, _ = m.p("receptions", 10.0, 5.0, 5.0, defn=defn3, league=0.01,
                opp="MAD", pos="WR")
    ck(0.0 < p7 <= 0.99, f"must stay a probability: {p7}")
    print("calib selftest:", "ok" if f == 0 else f"{f} FAILURES")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else selftest())

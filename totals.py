"""Alternate game-total legs, FanDuel, 2026-08-03 slate.

Pulled from the-odds-api (markets=alternate_totals, bookmakers=fanduel) on
2026-08-03 ~21:45Z. FanDuel only this time -- see the note in mlbml.py, but the
short version is that Ryan cannot put legs from two books on one parlay, so a
DraftKings price on this board is not a candidate leg, it is a distraction that
makes the pool look twice as deep as it is.

Both sides of every point are recorded on purpose. A one-sided price is a price
with the vig still in it; a matched Over/Under pair de-vigs to a probability
without needing a run-scoring model of my own, and the market's total is better
calibrated than anything I could fit this afternoon.

Every ladder below passed the monotonicity check that runs at the bottom of
this file: as the point rises, the Over must get longer and the Under shorter,
with no reversals. That check is here rather than in a comment because the
channel these prices came through has been caught fabricating rows, and a
fabricated ladder almost always breaks monotonicity somewhere. Every matched
pair also sums to 1.047-1.063 implied probability, which is a normal FanDuel
alternate-totals hold.
"""

# game | book | point | Over price | Under price
TOTALS_RAW = """
WSH@PHI|FanDuel|7.5|-205|158
WSH@PHI|FanDuel|8.5|-148|116
WSH@PHI|FanDuel|9.0|-115|-105
WSH@PHI|FanDuel|9.5|108|-138
WSH@PHI|FanDuel|10.5|144|-186
WSH@PHI|FanDuel|11.5|215|-290
WSH@PHI|FanDuel|12.5|280|-390
WSH@PHI|FanDuel|13.5|390|-590
WSH@PHI|FanDuel|14.5|500|-850
WSH@PHI|FanDuel|15.5|680|-1400
STL@NYY|FanDuel|5.5|-320|235
STL@NYY|FanDuel|6.5|-215|164
STL@NYY|FanDuel|7.5|-125|-102
STL@NYY|FanDuel|8.0|-102|-120
STL@NYY|FanDuel|8.5|116|-148
STL@NYY|FanDuel|9.5|176|-230
STL@NYY|FanDuel|10.5|240|-330
STL@NYY|FanDuel|11.5|350|-520
STL@NYY|FanDuel|12.5|480|-770
STL@NYY|FanDuel|13.5|680|-1400
PIT@MIL|FanDuel|6.5|-250|190
PIT@MIL|FanDuel|7.5|-146|114
PIT@MIL|FanDuel|8.5|-104|-118
PIT@MIL|FanDuel|9.5|148|-194
PIT@MIL|FanDuel|10.5|200|-265
PIT@MIL|FanDuel|11.5|300|-430
PIT@MIL|FanDuel|12.5|390|-590
PIT@MIL|FanDuel|13.5|560|-1000
PIT@MIL|FanDuel|14.5|750|-1600
LAD@CHC|FanDuel|6.5|-240|182
LAD@CHC|FanDuel|7.5|-140|110
LAD@CHC|FanDuel|8.0|-115|-105
LAD@CHC|FanDuel|8.5|100|-128
LAD@CHC|FanDuel|9.5|158|-205
LAD@CHC|FanDuel|10.5|215|-290
LAD@CHC|FanDuel|11.5|310|-440
LAD@CHC|FanDuel|12.5|420|-650
LAD@CHC|FanDuel|13.5|560|-1000
LAD@CHC|FanDuel|14.5|750|-1600
SF@TEX|FanDuel|6.5|-225|172
SF@TEX|FanDuel|7.5|-136|106
SF@TEX|FanDuel|8.0|-112|-108
SF@TEX|FanDuel|8.5|102|-130
SF@TEX|FanDuel|9.5|158|-205
SF@TEX|FanDuel|10.5|210|-280
SF@TEX|FanDuel|11.5|300|-430
SF@TEX|FanDuel|12.5|390|-590
SF@TEX|FanDuel|13.5|560|-1000
SF@TEX|FanDuel|14.5|750|-1600
TOR@HOU|FanDuel|7.5|-200|154
TOR@HOU|FanDuel|8.5|-146|114
TOR@HOU|FanDuel|9.0|-112|-108
TOR@HOU|FanDuel|9.5|110|-140
TOR@HOU|FanDuel|10.5|144|-186
TOR@HOU|FanDuel|11.5|220|-295
TOR@HOU|FanDuel|12.5|285|-400
TOR@HOU|FanDuel|13.5|400|-620
TOR@HOU|FanDuel|14.5|520|-900
TOR@HOU|FanDuel|15.5|750|-1600
TB@COL|FanDuel|9.5|-200|154
TB@COL|FanDuel|10.5|-148|116
TB@COL|FanDuel|11.5|-102|-120
TB@COL|FanDuel|12.5|128|-164
TB@COL|FanDuel|13.5|176|-230
TB@COL|FanDuel|14.5|230|-310
TB@COL|FanDuel|15.5|300|-430
TB@COL|FanDuel|16.5|390|-590
TB@COL|FanDuel|17.5|500|-850
SD@ARI|FanDuel|6.5|-310|230
SD@ARI|FanDuel|7.5|-180|140
SD@ARI|FanDuel|8.5|-130|102
SD@ARI|FanDuel|9.0|-102|-120
SD@ARI|FanDuel|9.5|122|-156
SD@ARI|FanDuel|10.5|158|-205
SD@ARI|FanDuel|11.5|230|-310
SD@ARI|FanDuel|12.5|300|-430
SD@ARI|FanDuel|13.5|430|-670
SD@ARI|FanDuel|14.5|560|-1000
"""

# EMPTY ON PURPOSE, and this is the whole point of writing it down rather than
# deleting the name. GAME_OF maps a pitcher to his game so a strikeout leg can
# inherit a start time and a correlation group. There are no strikeout legs on
# this board: "no pitcher/hitter props" is a standing instruction, so
# fd_k_ladder.txt is deliberately empty and the K family is deliberately zero.
#
# An empty dict here is therefore CORRECT, not stale. Left as a bare {} with no
# comment, the next reader sees a K family of size zero, assumes the mapping
# fell out, and repopulates it -- which is how a prop that was excluded on
# purpose comes back onto a ticket. If K legs are ever wanted again, rebuild
# this from each pitcher's OPPONENT in kprops.json rather than from memory of
# who plays where: pairing on "A's opponent is B's team" closes every game with
# no leftovers, which is the check that it is right. Doing it from memory put
# Wacha in the wrong game the first time this file was written.
GAME_OF = {}


# --- monotonicity check, run at import ------------------------------------
# A ladder is the one market family where correctness is checkable without a
# second source: the book cannot price Over 10.5 shorter than Over 9.5 without
# offering free money. So a ladder that reverses is not a suspicious price, it
# is a transcription error or a fabrication, and it should stop the import
# rather than quietly seed a solver. This is cheap and it runs every time.
def _dec(a):
    a = int(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _check_monotone(raw=None):
    from collections import defaultdict
    lad = defaultdict(list)
    for _l in (raw or TOTALS_RAW).strip().splitlines():
        if not _l.strip():
            continue
        _g, _bk, _pt, _ov, _un = _l.split('|')
        lad[(_g, _bk)].append((float(_pt), _dec(_ov), _dec(_un)))
    bad = []
    for _k, rungs in lad.items():
        rungs.sort()
        for (p0, o0, u0), (p1, o1, u1) in zip(rungs, rungs[1:]):
            if o1 <= o0:
                bad.append(f"{_k[0]} {_k[1]}: Over {p1} is not longer than Over {p0}")
            if u1 >= u0:
                bad.append(f"{_k[0]} {_k[1]}: Under {p1} is not shorter than Under {p0}")
    return bad


_bad = _check_monotone()
assert not _bad, ("totals.py ladder is not monotone -- these prices cannot all be "
                  "real:\n  " + "\n  ".join(_bad))

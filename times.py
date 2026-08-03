"""Scheduled start times, UTC, pulled from the-odds-api on 2026-08-03.

Derived from the SAME fetches that produced mlbml.py / totals.py / mma.py /
other.py, in the same pass, so the two cannot drift. That matters: when this
file was a separately typed snapshot, a game could carry last week's start time
next to today's price, and the ticket would sort itself into an order that never
happens.

Note what "chronological" does and does not mean here. A leg's START time is
not its SETTLE time: a first-five total settles about 90 minutes into a game, a
strikeout prop settles whenever the pitcher is pulled, a full-game total settles
last. Ordering by start is the honest version -- it tells you when you can start
watching a leg, not when you will know.

Only the 2026-08-03 MLB slate is here. The 08-04 and 08-05 games were in the
feed and are DELIBERATELY ABSENT: their AWAY@HOME keys collide with today's
(Nationals@Phillies and Pirates@Brewers are the same series two nights running),
and board.py keys totals by game, so tomorrow's line would merge into today's
ladder and a solver could take both halves of what it thinks is one market.
Same key, different game, is the exact shape of bug this package keeps finding.
"""

START = {
    # MLB, 2026-08-03 slate (ET). Every game named in totals.py must appear
    # here -- board.py does START[g], not START.get(g), on purpose: a totals
    # line for a game with no known start is a leg that cannot be time-filtered,
    # and the cutoff is the only thing between the solver and a finished game.
    "WSH@PHI": "2026-08-03T22:41Z",
    "STL@NYY": "2026-08-03T23:06Z",
    "PIT@MIL": "2026-08-03T23:41Z",
    "LAD@CHC": "2026-08-04T00:06Z",
    "SF@TEX":  "2026-08-04T00:06Z",
    "TOR@HOU": "2026-08-04T00:10Z",
    "TB@COL":  "2026-08-04T00:41Z",
    "SD@ARI":  "2026-08-04T01:41Z",
}

# Fights are per-bout, not per-card. Keyed by the fighter named in mma.py's
# `who` column ONLY -- board.py builds both sides of a bout off one line, so the
# opponent inherits this same start and must not get his own entry. Two entries
# would mean two market keys for one bout, and a solver could take both men.
FIGHT_START = {
    "Louie Sutherland":      "2026-08-08T18:00Z",
    "Alexia Thainara":       "2026-08-09T00:00Z",
    "Ty Miller":             "2026-08-09T00:00Z",
    "Carlos Diego Ferreira": "2026-08-09T00:00Z",
    "Diyar Nurgozhay":       "2026-08-09T00:00Z",
    "Yadier DelValle":       "2026-08-09T00:00Z",
    "Steven Asplund":        "2026-08-09T00:00Z",
    "Juliana Miller":        "2026-08-09T00:00Z",
    "Manoel Sousa":          "2026-08-09T00:00Z",
    "Quillan Salkilld":      "2026-08-09T00:00Z",
}

def et(utc):
    """UTC string -> Eastern wall clock, WITH THE DATE. Fixed -4 offset; the
    whole board is inside a single EDT window so there is no DST edge to get
    wrong here.

    The date used to be omitted -- output was 'Sat 11:00pm' and nothing else.
    That was fine when every leg on the board was tonight. It stopped being fine
    the moment boxing joined: the board now runs to 2026-10-31, the solver likes
    the far legs because they carry the heaviest prices, and a ticket containing
    a September fight and an October one printed as a column of weekday names
    that read like this weekend. Three 'Sat's on one ticket can be three
    different Saturdays. Nine characters of date is a cheap price for not
    discovering that after the slip is placed."""
    from datetime import datetime, timedelta
    d = datetime.strptime(utc, "%Y-%m-%dT%H:%MZ") - timedelta(hours=4)
    return d.strftime("%a %-m/%-d %-I:%M%p").replace("AM", "am").replace("PM", "pm")

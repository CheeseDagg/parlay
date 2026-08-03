"""Scheduled start times, UTC, pulled from the-odds-api events endpoints
2026-07-31. Used only to order the ticket the way it will actually resolve.

Note what "chronological" does and does not mean here. A leg's START time is
not its SETTLE time: a first-five total settles about 90 minutes into a game, a
strikeout prop settles whenever the pitcher is pulled, a full-game total settles
last. Ordering by start is the honest version -- it tells you when you can start
watching a leg, not when you will know.
"""

START = {
    # MLB, 2026-07-31 slate
    "NYY@CHC": "2026-07-31T18:21Z",
    "PIT@CIN": "2026-07-31T22:11Z",
    "PHI@BAL": "2026-07-31T23:06Z",
    "STL@TOR": "2026-07-31T23:08Z",
    "ARI@CLE": "2026-07-31T23:11Z",
    "CWS@TB":  "2026-07-31T23:11Z",
    "MIA@NYM": "2026-07-31T23:11Z",
    "WSH@ATL": "2026-07-31T23:16Z",
    "TEX@HOU": "2026-08-01T00:16Z",
    "KC@COL":  "2026-08-01T00:41Z",
    "MIL@LAA": "2026-08-01T01:39Z",
    "DET@ATH": "2026-08-01T01:41Z",
    "SF@SD":   "2026-08-01T01:46Z",
    "BOS@LAD": "2026-08-01T02:11Z",
    "MIN@SEA": "2026-08-01T02:11Z",
}

# fights are per-bout, not per-card
FIGHT_START = {
    "Levan Khabalaev":      "2026-07-31T20:45Z",
    "Tatiana Postarnakova": "2026-07-31T21:10Z",
    "Jonathan Piersma":     "2026-07-31T21:40Z",
    "Sean Gauci":           "2026-07-31T22:10Z",
    "Lazaro Dayron":        "2026-07-31T22:40Z",
    "Moustapha Diakhate":   "2026-07-31T23:15Z",
    "Amru Magomedov":       "2026-07-31T23:40Z",
    "Dakota Ditcheva":      "2026-08-01T00:10Z",
    "Usman Nurmagomedov":   "2026-08-01T00:40Z",
    "Borislav Nikolic":     "2026-08-01T14:00Z",
    "Nina Milosevic":       "2026-08-01T14:00Z",
    "Stephanie Luciano":    "2026-08-01T14:00Z",
    "Noah Gugnon":          "2026-08-01T17:00Z",
    "Aleksandar Rakic":     "2026-08-01T22:00Z",
    "Jovan Leka":           "2026-08-01T22:00Z",
    "Bogdan Grad":          "2026-08-01T22:00Z",
    "Uros Medic":           "2026-08-01T22:00Z",
    "Robert Valentin":      "2026-08-01T22:00Z",
    "Vlasto Cepo":          "2026-08-01T22:00Z",
    "Navajo Stirling":      "2026-08-01T22:00Z",
    "Mateusz Rebecki":      "2026-08-01T22:00Z",
    "Ludovit Klein":        "2026-08-01T22:00Z",
    "Michael Oliveira":     "2026-08-01T22:00Z",
}

def et(utc):
    """UTC string -> Eastern wall clock. Fixed -4 offset; the whole board is
    inside a single EDT window so there is no DST edge to get wrong here."""
    from datetime import datetime, timedelta
    d = datetime.strptime(utc, "%Y-%m-%dT%H:%MZ") - timedelta(hours=4)
    return d.strftime("%a %-I:%M%p").replace("AM", "am").replace("PM", "pm")

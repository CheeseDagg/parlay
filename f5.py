"""FanDuel first-five-innings totals. EMPTY FOR 2026-08-03, and the reason is
the whole content of this file.

FanDuel posts NO first-five totals through the-odds-api for this slate. Not
"none that were good" -- none at all. Verified three ways before writing this:

  1. `markets=totals_h1,alternate_totals_h1` combined with the full-game call
     returned every full-game rung and not one h1 rung, for all eight games.
  2. Three dedicated h1-only probes (WSH@PHI, TOR@HOU, MIN@KC) each came back
     with "bookmakers": [] -- an empty list, not an error, not a 404, not a
     rate limit. FanDuel simply is not in the h1 book for these events.
  3. The same key on the same day returns full ladders for alternate_totals,
     so this is not an entitlement problem with the key or the plan.

WHY THIS FILE IS NOT JUST DELETED. F5 unders are half of the standing
instruction -- "f5 unders and fighters only" -- so their absence is the single
most consequential fact about tonight's board. If this file were removed,
board.py would still import cleanly, the solver would still build a ticket, and
the output would look exactly like a normal night on which no F5 leg happened
to make the cut. That is the defect this entire package was audited to
eliminate: a failure that renders identically to a legitimate empty result.
An empty F5_RAW with this docstring attached is the failure made visible.

WHAT TO DO ABOUT IT. The market exists in the FanDuel app; it is the API feed
that does not carry it. So an F5 leg tonight has to be read off the app by hand
and pasted in below, in the format `GAME|POINT|OVER|UNDER`, using the same
AWAY@HOME keys as times.py. Nothing else in the package needs to change --
board.py reads this file whenever book == 'FanDuel' and prices it exactly as it
prices a full-game rung.

Format: GAME|POINT|OVER|UNDER
"""

F5_RAW = """
"""

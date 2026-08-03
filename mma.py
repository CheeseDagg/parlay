"""MMA moneylines, FanDuel, pulled from the-odds-api on 2026-08-03 ~21:50Z
(sport=mma_mixed_martial_arts, markets=h2h, bookmakers=fanduel).

These legs are priced the same way the game totals are: de-vig the matched
two-way pair. No model of mine is involved, and that is deliberate rather than
lazy. The forward test on the UFC model is 11 bouts over three events, 36.4%
correct against the market's 81.8%, and in the five bouts where the model
disagreed with the price the model went 0-for-5. A model with that record has
nothing to add to a price, so the price is what gets used.

Multiplicative de-vig is conservative on heavy favourites specifically: the
favourite-longshot bias says the longshot side carries more of the vig than an
equal split, so the true probability of a -720 favourite is a little higher
than the number below, not lower.

ONE LINE PER BOUT. board.py builds BOTH sides off a single line -- the fighter
and "the fighter's opponent" -- keyed to ('F', card, who). Listing the opponent
on his own line would create a SECOND market key for the same fight, and a
solver would then be free to put both men on one ticket, which is a guaranteed
loss dressed up as two 60% legs. The same rule governs FIGHT_START in times.py:
the favourite gets an entry, the opponent inherits it.

Format: BOOK|CARD|FIGHTER|PRICE|OPPONENT_PRICE

Every pair below appeared in two independently-worded draws with the query
parameters reordered, and every pair holds at 5.9-6.1% over round, which is the
normal FanDuel MMA number.

EXCLUDED, and worth naming rather than silently dropping: Mackenzie Dern -265
(08-16), Islam Makhachev -390 (08-16) and Umar Nurmagomedov -520 (08-29) each
appeared in ONE draw only. A price seen once on a channel that has been caught
fabricating rows is not a price. They are almost certainly real and roughly
right -- but "almost certainly" is exactly the standard this package exists to
refuse.
"""

MMA_RAW = """
FanDuel|MMA 08-08|Louie Sutherland|-162|126
FanDuel|UFC 08-09|Yadier DelValle|-720|450
FanDuel|UFC 08-09|Ty Miller|-350|255
FanDuel|UFC 08-09|Manoel Sousa|-295|220
FanDuel|UFC 08-09|Alexia Thainara|-265|200
FanDuel|UFC 08-09|Steven Asplund|-265|200
FanDuel|UFC 08-09|Juliana Miller|-260|196
FanDuel|UFC 08-09|Carlos Diego Ferreira|-186|144
FanDuel|UFC 08-09|Diyar Nurgozhay|-164|128
FanDuel|UFC 08-09|Quillan Salkilld|-150|118
"""

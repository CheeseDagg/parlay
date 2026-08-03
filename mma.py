"""MMA moneylines, pulled verbatim from the-odds-api on 2026-07-31
(sport=mma_mixed_martial_arts, markets=h2h, bookmakers=fanduel,draftkings).

These legs are priced the same way the game totals are: de-vig the matched
two-way pair. No model of mine is involved. That is deliberate -- production's
UFC p1 is mis-scaled (build_site.py computes sigma(s1 - s2) off model_score,
SD 0.421, so it emits ~0.5 for nearly every fight), so the model has nothing
trustworthy to say here and the market does.

Multiplicative de-vig is conservative on heavy favourites specifically: the
favourite-longshot bias says the longshot side carries more of the vig than an
equal split, so the true probability of a -7000 favourite is a little higher
than the number below, not lower.

Cards included run through Sunday 2026-08-02. Not every bout is UFC -- the
2026-07-31 block is PFL and the 2026-08-01T14:00Z block is a European regional
card. The 22:00Z block is the UFC card. The book does not care which promotion
a leg comes from; it is flagged only so the card is legible.

Fights on 2026-08-16 and 2026-08-29 are in the feed and are EXCLUDED: a leg
four weeks out holds the whole ticket open for a month, and none of them
de-vigged above .80 anyway (Makhachev .766, Umar .791).

Format: BOOK|CARD|FIGHTER|PRICE|OPPONENT_PRICE
"""

MMA_RAW = """
FanDuel|PFL 07-31|Levan Khabalaev|-700|500
FanDuel|PFL 07-31|Tatiana Postarnakova|-240|198
FanDuel|PFL 07-31|Jonathan Piersma|-172|144
FanDuel|PFL 07-31|Sean Gauci|-260|215
FanDuel|PFL 07-31|Lazaro Dayron|-162|136
FanDuel|PFL 07-31|Moustapha Diakhate|-350|280
FanDuel|PFL 07-31|Amru Magomedov|-3500|1400
FanDuel|PFL 08-01|Dakota Ditcheva|-7000|2000
FanDuel|PFL 08-01|Usman Nurmagomedov|-560|420
FanDuel|REG 08-01|Borislav Nikolic|-190|160
FanDuel|REG 08-01|Nina Milosevic|-520|390
FanDuel|REG 08-01|Stephanie Luciano|-335|270
FanDuel|REG 08-01|Noah Gugnon|-120|102
FanDuel|UFC 08-01|Aleksandar Rakic|-390|310
FanDuel|UFC 08-01|Jovan Leka|-235|194
FanDuel|UFC 08-01|Bogdan Grad|-200|168
FanDuel|UFC 08-01|Uros Medic|-450|350
FanDuel|UFC 08-01|Robert Valentin|-158|134
FanDuel|UFC 08-01|Vlasto Cepo|-360|285
FanDuel|UFC 08-01|Navajo Stirling|-335|270
FanDuel|UFC 08-01|Mateusz Rebecki|-750|530
FanDuel|UFC 08-01|Ludovit Klein|-255|210
FanDuel|UFC 08-01|Michael Oliveira|-350|280
DraftKings|REG 08-01|Borislav Nikolic|-192|160
DraftKings|REG 08-01|Nina Milosevic|-500|380
DraftKings|REG 08-01|Stephanie Luciano|-325|260
DraftKings|REG 08-01|Noah Gugnon|-120|100
DraftKings|UFC 08-01|Aleksandar Rakic|-360|285
DraftKings|UFC 08-01|Jovan Leka|-258|210
DraftKings|UFC 08-01|Bogdan Grad|-192|160
DraftKings|UFC 08-01|Uros Medic|-395|310
DraftKings|UFC 08-01|Robert Valentin|-155|130
DraftKings|UFC 08-01|Vlasto Cepo|-355|280
DraftKings|UFC 08-01|Navajo Stirling|-325|260
DraftKings|UFC 08-01|Mateusz Rebecki|-700|500
DraftKings|UFC 08-01|Ludovit Klein|-270|220
DraftKings|UFC 08-01|Michael Oliveira|-360|285
"""

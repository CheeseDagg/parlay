"""Non-baseball, non-MMA moneylines pulled from FanDuel for the 2026-07-31 ->
2026-08-02 weekend window. Boxing, WNBA, tennis, CFL, soccer.

Why this file exists: the fight board alone is 23 bouts, of which only six sit
at -500 or heavier, so "less baseball" ran out of legs long before it ran out
of target price. Boxing turned out to be the missing vein -- a Saturday card
posts -650 to -5000 favourites, which is exactly the shape the MLB first-five
unders were being used to supply.

Format:  SPORT|GROUP|SELECTION|PRICE|OTHER_PRICES|UTC
OTHER_PRICES is comma separated: one entry for a two-way market, two for a
soccer three-way (opponent, then the draw). Every outcome of a market is
listed on its own line, so the de-vig sees the complete book and a solver
cannot take two outcomes of the same market.

Markets FanDuel did not price at all in this feed are simply absent: AFL and
NRL come back with an empty bookmaker list, DFB-Pokal has no weekend fixtures,
and five boxing undercard bouts have no posted line.
"""

OTHER_RAW = """
BOX|Kaleiopu-Castillo|Dalis Kaleiopu|-3000|890|2026-08-01T21:00Z
BOX|Kaleiopu-Castillo|Yeyery Castillo|890|-3000|2026-08-01T21:00Z
BOX|Capetillo-Becerril|Dylan Capetillo|-4500|1080|2026-08-01T21:00Z
BOX|Capetillo-Becerril|Juan Carlos Becerril|1080|-4500|2026-08-01T21:00Z
BOX|Cabrera-Pedroza|Gael Cabrera|-5000|1400|2026-08-01T21:00Z
BOX|Cabrera-Pedroza|Francisco Pedroza|1400|-5000|2026-08-01T21:00Z
BOX|Iriarte-Lagunas|Joel Iriarte|-5000|1400|2026-08-01T22:00Z
BOX|Iriarte-Lagunas|Jorge Lagunas Valencia|1400|-5000|2026-08-01T22:00Z
BOX|Conwell-Kroll|Charles Conwell|-650|400|2026-08-02T00:05Z
BOX|Conwell-Kroll|Paul Kroll|400|-650|2026-08-02T00:05Z
BOX|Curiel-Randall|Raul Curiel|-1300|580|2026-08-02T01:00Z
BOX|Curiel-Randall|Quinton Randall|580|-1300|2026-08-02T01:00Z
BOX|Muratalla-Conceicao|Raymond Muratalla|-1300|860|2026-08-02T02:00Z
BOX|Muratalla-Conceicao|Robson Conceicao|860|-1300|2026-08-02T02:00Z
BOX|Dalton-Crocker|Ben Crocker|-116|-116|2026-08-01T20:00Z
BOX|Dalton-Crocker|Bobby Dalton|-116|-116|2026-08-01T20:00Z
BOX|Roach-Zepeda|Lamont Roach|-132|114|2026-08-02T03:00Z
BOX|Roach-Zepeda|William Zepeda|114|-132|2026-08-02T03:00Z
WNBA|SEA@ATL|Atlanta Dream ML|-700|470|2026-07-31T23:30Z
WNBA|SEA@ATL|Seattle Storm ML|470|-700|2026-07-31T23:30Z
WNBA|DAL@WSH|Dallas Wings ML|-154|126|2026-07-31T23:30Z
WNBA|DAL@WSH|Washington Mystics ML|126|-154|2026-07-31T23:30Z
WNBA|IND@POR|Indiana Fever ML|-340|260|2026-08-01T02:00Z
WNBA|IND@POR|Portland Fire ML|260|-340|2026-08-01T02:00Z
WNBA|LV@CHI|Las Vegas Aces ML|-290|225|2026-08-01T17:00Z
WNBA|LV@CHI|Chicago Sky ML|225|-290|2026-08-01T17:00Z
WNBA|NYL@PHX|New York Liberty ML|-142|116|2026-08-01T19:00Z
WNBA|NYL@PHX|Phoenix Mercury ML|116|-142|2026-08-01T19:00Z
TEN|Fritz-Michelsen|Taylor Fritz|-260|205|2026-07-31T20:00Z
TEN|Fritz-Michelsen|Alex Michelsen|205|-260|2026-07-31T20:00Z
TEN|Jodar-Musetti|Rafael Jodar|-178|144|2026-07-31T22:00Z
TEN|Jodar-Musetti|Lorenzo Musetti|144|-178|2026-07-31T22:00Z
TEN|Shelton-Tabilo|Ben Shelton|-330|250|2026-08-01T00:00Z
TEN|Shelton-Tabilo|Alejandro Tabilo|250|-330|2026-08-01T00:00Z
TEN|Shnaider-Samsonova|Diana Shnaider|-110|-110|2026-07-31T20:00Z
TEN|Shnaider-Samsonova|Liudmila Samsonova|-110|-110|2026-07-31T20:00Z
TEN|Svitolina-Eala|Elina Svitolina|-160|130|2026-07-31T22:30Z
TEN|Svitolina-Eala|Alexandra Eala|130|-160|2026-07-31T22:30Z
CFL|MTL@OTT|Montreal Alouettes ML|-335|265|2026-07-31T23:30Z
CFL|MTL@OTT|Ottawa Redblacks ML|265|-335|2026-07-31T23:30Z
CFL|CGY@HAM|Calgary Stampeders ML|-255|205|2026-08-01T19:00Z
CFL|CGY@HAM|Hamilton Tiger-Cats ML|205|-255|2026-08-01T19:00Z
CFL|SSK@EDM|Saskatchewan Roughriders ML|-126|105|2026-08-01T23:00Z
CFL|SSK@EDM|Edmonton Elks ML|105|-126|2026-08-01T23:00Z
SOC|Puebla-Guadalajara|Guadalajara|-210|460,360|2026-08-01T01:00Z
SOC|Queretaro-Tigres|Tigres|-120|280,260|2026-08-01T23:00Z
SOC|CruzAzul-Atlante|Cruz Azul|-350|700,450|2026-08-02T03:00Z
SOC|America-Santos|America|-270|600,380|2026-08-02T23:00Z
SOC|Toluca-Necaxa|Toluca|-210|450,350|2026-08-03T01:05Z
SOC|NYCFC-TOR|New York City FC|-165|390,290|2026-07-31T23:30Z
SOC|PHI-ATL|Philadelphia Union|-150|340,310|2026-08-01T23:30Z
SOC|MIA-CLB|Inter Miami CF|-165|360,340|2026-08-01T23:30Z
SOC|CHI-CLT|Chicago Fire|-180|410,330|2026-08-02T00:30Z
SOC|COL-ATX|Colorado Rapids|-145|330,300|2026-08-02T01:30Z
"""

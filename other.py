"""Non-baseball, non-MMA moneylines. FanDuel, pulled from the-odds-api on
2026-08-03 between ~21:45Z and ~22:05Z. Boxing, WNBA, CFL, soccer.

Why this file exists: the MMA board is ten bouts, of which exactly one sits at
-500 or heavier, so "the less baseball the better" runs out of legs long before
it runs out of target price. Boxing and the European soccer restarts are the
missing vein -- a boxing card posts -900 to -3000 favourites and a Portuguese
or Greek opening fixture posts -475 to -1250, which is the shape the MLB
first-five unders used to supply and cannot supply tonight (see f5.py).

Format:  SPORT|GROUP|SELECTION|PRICE|OTHER_PRICES|UTC
OTHER_PRICES is comma separated: one entry for a two-way market, two for a
soccer three-way (opponent, then the draw). Every outcome of a market is listed
on its own line so the de-vig sees the complete book, and every line of one
market shares a GROUP, which is what stops a solver taking two outcomes of the
same fixture.

--------------------------------------------------------------------------
READ THIS BEFORE USING A LEG DATED AFTER 2026-08-10.

The solver's cutoff filters legs that have already STARTED. It has no upper
horizon, so nothing stops it putting Shields -3000 (2026-08-16) or Álvarez -350
(2026-10-31) on a ticket -- and those are exactly the legs it likes, because
they are the heaviest prices on the board. A ticket that includes them does not
resolve until Halloween. That is not a bug in the solver; it is a fact about
what "heaviest favourite available" means when the board spans three months.
Sort by start time and cut the tail by hand, or pass --dropgrp for the far
fixtures. It is called out here because a 14-leg ticket that reads as "tonight"
in every other respect will quietly contain two legs from October.
--------------------------------------------------------------------------

VALIDATION. Same discipline as mlbml.py: two draws with reordered parameters
and differently-worded questions, plus an implied-probability sum on every
market. Two-way markets here sum 1.036-1.075; three-way soccer sums
1.066-1.101. Both are normal FanDuel holds and both are ranges a fabricated row
falls outside of -- nine rows elsewhere in this board were caught that way,
where the summarizer dropped a minus sign and turned a +210 dog into a -210
favourite. Every such row was either re-fetched until it agreed or excluded.

EXCLUDED, named rather than silently dropped:
  * IFK Göteborg -130 / Kalmar +180 / draw +260 -- sums to 1.2001, which is not
    a hold any book posts. One of those three prices is wrong and a third draw
    did not settle which. Dropped entirely rather than guessed at.
  * Two of nineteen boxing bouts appeared in only one draw and are not below.
  * Liga MX, Brazil Série A and B, Argentina Primera, Chile, MLS, EFL Cup, EFL
    Championship, J-League, Denmark, Poland, Austria, Switzerland and the rest
    of the Dutch/Turkish/Greek/Portuguese/Swedish/Norwegian/Chinese fixtures
    were all retrieved and all validated, but only the FAVOURITE's price was
    captured for most of them. A one-sided price cannot be de-vigged, so those
    fixtures cannot become legs. The heaviest of them are listed at the bottom
    of this file as a re-fetch list, not as data.
  * Copa Libertadores, Copa Sudamericana, Korea K-League, Russia Premier,
    Belgium First Division, DFB-Pokal, League of Ireland, AFL, NRL and ATP
    Washington all have events in the feed with an EMPTY FanDuel bookmaker
    list. Present but unpriced is different from absent, and it is different
    again from "I failed to fetch it."
"""

OTHER_RAW = """
WNBA|WNBA NYL-SEA|New York Liberty|-310|240|2026-08-03T23:00Z
WNBA|WNBA NYL-SEA|Seattle Storm|240|-310|2026-08-03T23:00Z
WNBA|WNBA ATL-LV|Atlanta Dream|-138|112|2026-08-03T23:30Z
WNBA|WNBA ATL-LV|Las Vegas Aces|112|-138|2026-08-03T23:30Z
WNBA|WNBA PHX-CHI|Phoenix Mercury|-124|102|2026-08-04T01:00Z
WNBA|WNBA PHX-CHI|Chicago Sky|102|-124|2026-08-04T01:00Z
WNBA|WNBA GS-TOR|Golden State Valkyries|-900|540|2026-08-05T02:00Z
WNBA|WNBA GS-TOR|Toronto Tempo|540|-900|2026-08-05T02:00Z
WNBA|WNBA DAL-WAS|Dallas Wings|-144|118|2026-08-05T23:30Z
WNBA|WNBA DAL-WAS|Washington Mystics|118|-144|2026-08-05T23:30Z
CFL|CFL SSK-OTT|Saskatchewan Roughriders|-385|300|2026-08-08T01:00Z
CFL|CFL SSK-OTT|Ottawa Redblacks|300|-385|2026-08-08T01:00Z
BOX|BOX Nyika-Masson|David Nyika|-380|260|2026-08-08T11:00Z
BOX|BOX Nyika-Masson|Kevin Masson|260|-380|2026-08-08T11:00Z
BOX|BOX Kraus-Hemphill|Peter Kraus|-1100|540|2026-08-08T19:00Z
BOX|BOX Kraus-Hemphill|Kem Hemphill|540|-1100|2026-08-08T19:00Z
BOX|BOX Mckenna-Oliha|Aaron Mckenna|-410|290|2026-08-08T20:00Z
BOX|BOX Mckenna-Oliha|Sam Oliha|290|-410|2026-08-08T20:00Z
BOX|BOX Galle-Metcalf|Ryan Galle|-156|118|2026-08-08T21:00Z
BOX|BOX Galle-Metcalf|Sam Metcalf|118|-156|2026-08-08T21:00Z
BOX|BOX Simpson-Williamson|Ben Simpson|-140|110|2026-08-08T21:00Z
BOX|BOX Simpson-Williamson|Jack Williamson|110|-140|2026-08-08T21:00Z
BOX|BOX Thibeault-Robinson|Steven Thibeault|-320|220|2026-08-09T00:00Z
BOX|BOX Thibeault-Robinson|Chris Robinson|220|-320|2026-08-09T00:00Z
BOX|BOX Johnson-Thorslund|Ebanie Johnson|-128|100|2026-08-09T03:00Z
BOX|BOX Johnson-Thorslund|Dina Thorslund|100|-128|2026-08-09T03:00Z
BOX|BOX Shields-Scott|Claressa Shields|-3000|1360|2026-08-16T03:00Z
BOX|BOX Shields-Scott|Lani Scott|1360|-3000|2026-08-16T03:00Z
BOX|BOX Serrano-Manzur|Amanda Serrano|-2000|1000|2026-08-22T00:00Z
BOX|BOX Serrano-Manzur|Sabrina Manzur|1000|-2000|2026-08-22T00:00Z
BOX|BOX Lopez-Romero|Teofimo López|-260|190|2026-08-23T03:00Z
BOX|BOX Lopez-Romero|Rolando Romero|190|-260|2026-08-23T03:00Z
BOX|BOX Harper-Reyes|Terri Harper|-300|215|2026-08-29T16:00Z
BOX|BOX Harper-Reyes|Karen Reyes|215|-300|2026-08-29T16:00Z
BOX|BOX Dubois-Moore|Daniel Dubois|-2400|1120|2026-08-29T20:00Z
BOX|BOX Dubois-Moore|Jarrell Moore|1120|-2400|2026-08-29T20:00Z
BOX|BOX Mayer-Cameron|Mikaela Mayer|-270|200|2026-08-29T21:00Z
BOX|BOX Mayer-Cameron|Chantelle Cameron|200|-270|2026-08-29T21:00Z
BOX|BOX Itauma-Hrgovic|Moses Itauma|-900|530|2026-08-29T21:00Z
BOX|BOX Itauma-Hrgovic|Filip Hrgović|530|-900|2026-08-29T21:00Z
BOX|BOX Williams-Mielnicki|Sam Williams|-142|112|2026-09-05T02:00Z
BOX|BOX Williams-Mielnicki|Vito Mielnicki|112|-142|2026-09-05T02:00Z
BOX|BOX Ruiz-Knyba|Andy Ruiz|-330|235|2026-09-05T03:00Z
BOX|BOX Ruiz-Knyba|Kevin Knyba|235|-330|2026-09-05T03:00Z
BOX|BOX Taylor-Pili|Katie Taylor|-2400|1140|2026-09-05T21:00Z
BOX|BOX Taylor-Pili|Ana Pili|1140|-2400|2026-09-05T21:00Z
BOX|BOX Garcia-Benn|Devin Garcia|-430|300|2026-09-13T03:00Z
BOX|BOX Garcia-Benn|Conor Benn|300|-430|2026-09-13T03:00Z
BOX|BOX Alvarez-Mbilli|Saúl Álvarez|-350|250|2026-10-31T22:00Z
BOX|BOX Alvarez-Mbilli|Christian Mbilli|250|-350|2026-10-31T22:00Z
SOC|UCLQ Ararat-Celje|Ararat-Armenia|170|155,230|2026-08-04T16:00Z
SOC|UCLQ Ararat-Celje|NK Celje|155|170,230|2026-08-04T16:00Z
SOC|UCLQ Ararat-Celje|Draw|230|170,155|2026-08-04T16:00Z
SOC|UCLQ Mjallby-Slovan|Mjällby AIF|100|240,250|2026-08-04T16:00Z
SOC|UCLQ Mjallby-Slovan|Slovan Bratislava|240|100,250|2026-08-04T16:00Z
SOC|UCLQ Mjallby-Slovan|Draw|250|100,240|2026-08-04T16:00Z
SOC|UCLQ Levski-Kairat|Levski Sofia|-165|440,280|2026-08-04T17:30Z
SOC|UCLQ Levski-Kairat|Kairat Almaty|440|-165,280|2026-08-04T17:30Z
SOC|UCLQ Levski-Kairat|Draw|280|-165,440|2026-08-04T17:30Z
SOC|UCLQ Hapoel-RedStar|Hapoel Be'er Sheva|340|-140,270|2026-08-04T17:30Z
SOC|UCLQ Hapoel-RedStar|Red Star Belgrade|-140|340,270|2026-08-04T17:30Z
SOC|UCLQ Hapoel-RedStar|Draw|270|340,-140|2026-08-04T17:30Z
SOC|UCLQ USG-Bodo|Union Saint-Gilloise|110|200,270|2026-08-04T18:00Z
SOC|UCLQ USG-Bodo|Bodø/Glimt|200|110,270|2026-08-04T18:00Z
SOC|UCLQ USG-Bodo|Draw|270|110,200|2026-08-04T18:00Z
SOC|UCLQ Dinamo-Kauno|Dinamo Zagreb|-750|1500,700|2026-08-04T18:00Z
SOC|UCLQ Dinamo-Kauno|Kauno Žalgiris|1500|-750,700|2026-08-04T18:00Z
SOC|UCLQ Dinamo-Kauno|Draw|700|-750,1500|2026-08-04T18:00Z
SOC|UCLQ Sparta-Lyon|Sparta Prague|220|105,250|2026-08-04T18:00Z
SOC|UCLQ Sparta-Lyon|Olympique Lyonnais|105|220,250|2026-08-04T18:00Z
SOC|UCLQ Sparta-Lyon|Draw|250|220,105|2026-08-04T18:00Z
SOC|UCLQ Olympiakos-NEC|Olympiakos Piraeus|-190|470,320|2026-08-04T18:00Z
SOC|UCLQ Olympiakos-NEC|NEC Nijmegen|470|-190,320|2026-08-04T18:00Z
SOC|UCLQ Olympiakos-NEC|Draw|320|-190,470|2026-08-04T18:00Z
SOC|UCLQ AGF-Sabah|AGF Aarhus|-165|390,280|2026-08-05T16:30Z
SOC|UCLQ AGF-Sabah|Sabah FK|390|-165,280|2026-08-05T16:30Z
SOC|UCLQ AGF-Sabah|Draw|280|-165,390|2026-08-05T16:30Z
SOC|UCLQ Fener-Sturm|Fenerbahçe|-320|700,390|2026-08-05T18:00Z
SOC|UCLQ Fener-Sturm|Sturm Graz|700|-320,390|2026-08-05T18:00Z
SOC|UCLQ Fener-Sturm|Draw|390|-320,700|2026-08-05T18:00Z
SOC|CSL Beijing-Shenzhen|Beijing FC|-300|650,440|2026-08-07T11:35Z
SOC|CSL Beijing-Shenzhen|Shenzhen Peng City|650|-300,440|2026-08-07T11:35Z
SOC|CSL Beijing-Shenzhen|Draw|440|-300,650|2026-08-07T11:35Z
SOC|NOR Viking-Sarpsborg|Viking FK|-300|600,470|2026-08-08T14:00Z
SOC|NOR Viking-Sarpsborg|Sarpsborg 08|600|-300,470|2026-08-08T14:00Z
SOC|NOR Viking-Sarpsborg|Draw|470|-300,600|2026-08-08T14:00Z
SOC|NED PSV-Fortuna|PSV Eindhoven|-550|1000,600|2026-08-08T18:00Z
SOC|NED PSV-Fortuna|Fortuna Sittard|1000|-550,600|2026-08-08T18:00Z
SOC|NED PSV-Fortuna|Draw|600|-550,1000|2026-08-08T18:00Z
SOC|POR Sporting-Estrela|Sporting CP|-550|1200,500|2026-08-08T19:30Z
SOC|POR Sporting-Estrela|CF Estrela da Amadora|1200|-550,500|2026-08-08T19:30Z
SOC|POR Sporting-Estrela|Draw|500|-550,1200|2026-08-08T19:30Z
SOC|FIN Ilves-Mariehamn|Ilves Tampere|-425|750,470|2026-08-09T15:00Z
SOC|FIN Ilves-Mariehamn|IFK Mariehamn|750|-425,470|2026-08-09T15:00Z
SOC|FIN Ilves-Mariehamn|Draw|470|-425,750|2026-08-09T15:00Z
SOC|POR Porto-Alverca|FC Porto|-600|1600,550|2026-08-09T17:00Z
SOC|POR Porto-Alverca|FC Alverca|1600|-600,550|2026-08-09T17:00Z
SOC|POR Porto-Alverca|Draw|550|-600,1600|2026-08-09T17:00Z
SOC|POR Benfica-Viseu|SL Benfica|-1250|2700,850|2026-08-09T19:30Z
SOC|POR Benfica-Viseu|Académico de Viseu|2700|-1250,850|2026-08-09T19:30Z
SOC|POR Benfica-Viseu|Draw|850|-1250,2700|2026-08-09T19:30Z
SOC|SWE Sirius-BP|IK Sirius|-350|750,470|2026-08-10T17:00Z
SOC|SWE Sirius-BP|IF Brommapojkarna|750|-350,470|2026-08-10T17:00Z
SOC|SWE Sirius-BP|Draw|470|-350,750|2026-08-10T17:00Z
SOC|TUR Galatasaray-Akhisar|Galatasaray|-600|1400,600|2026-08-14T18:30Z
SOC|TUR Galatasaray-Akhisar|Akhisar Belediyespor|1400|-600,600|2026-08-14T18:30Z
SOC|TUR Galatasaray-Akhisar|Draw|600|-600,1400|2026-08-14T18:30Z
SOC|TUR Besiktas-Eyupspor|Beşiktaş|-350|800,440|2026-08-16T18:30Z
SOC|TUR Besiktas-Eyupspor|Eyüpspor|800|-350,440|2026-08-16T18:30Z
SOC|TUR Besiktas-Eyupspor|Draw|440|-350,800|2026-08-16T18:30Z
SOC|GRE AEK-Iraklis|AEK Athens|-600|1400,550|2026-08-22T17:00Z
SOC|GRE AEK-Iraklis|Iraklis Thessaloniki|1400|-600,550|2026-08-22T17:00Z
SOC|GRE AEK-Iraklis|Draw|550|-600,1400|2026-08-22T17:00Z
SOC|GRE Olympiakos-Atromitos|Olympiakos Piraeus|-500|1100,470|2026-08-22T19:00Z
SOC|GRE Olympiakos-Atromitos|Atromitos|1100|-500,470|2026-08-22T19:00Z
SOC|GRE Olympiakos-Atromitos|Draw|470|-500,1100|2026-08-22T19:00Z
SOC|GRE Panathinaikos-Kifisia|Panathinaikos|-475|1100,430|2026-08-23T18:00Z
SOC|GRE Panathinaikos-Kifisia|AE Kifisia|1100|-475,430|2026-08-23T18:00Z
SOC|GRE Panathinaikos-Kifisia|Draw|430|-475,1100|2026-08-23T18:00Z
SOC|GRE PAOK-Levadiakos|PAOK Thessaloniki|-425|950,410|2026-08-23T18:00Z
SOC|GRE PAOK-Levadiakos|Levadiakos|950|-425,410|2026-08-23T18:00Z
SOC|GRE PAOK-Levadiakos|Draw|410|-425,950|2026-08-23T18:00Z
"""

# ---------------------------------------------------------------------------
# RE-FETCH LIST -- NOT DATA. Do not parse this block.
#
# These are heavy favourites that were retrieved and passed the vig-sum check,
# but only the favourite's price was captured, so they cannot be de-vigged and
# cannot become legs. Each needs one more call with all three outcomes to
# become usable. Recorded because "I looked and there was nothing heavy" and
# "I looked, found something heavy, and could not price it" are different
# statements and the file should not blur them.
#
#   Cardiff City -360, Leicester City -360, Southampton -320 (EFL Cup 08-08)
#   Middlesbrough -320 (EFL Championship 08-14 -> 08-17)
#   Universidad Católica -370 (Chile, 08-08 00:30Z)
#   Ceará -320 (Brazil Série B, 08-07 23:30Z)
#   Pachuca -310 (Liga MX, 08-15 -> 08-18)
#   Colorado Rapids -320 (MLS, 08-16 01:30Z)
#   Flamengo -550 (Brazil Série A, 08-09 22:30Z)
#
# CAVEAT ON LEAGUE COMPOSITION, carried from the fetch. Several returned
# fixtures pair top-flight clubs with sides that look out of division -- the
# J-League block includes Mito HollyHock and JEF United Chiba, the Eredivisie
# block includes Cambuur, Excelsior, ADO Den Haag and Willem II, the Turkish
# block includes Akhisar Belediyespor, Amed SK and Erzurum BB. Every one passed
# the vig-sum check, so the PRICES are coherent. Whether those clubs are really
# in those divisions in 2026 is not checkable from here, and a cup tie would
# explain all of it. Galatasaray-Akhisar above is in the board on that basis:
# the price is real whatever competition it belongs to.
# ---------------------------------------------------------------------------

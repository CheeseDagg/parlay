"""Alternate game-total legs, pulled verbatim from the-odds-api on 2026-07-31
(markets=alternate_totals, bookmakers=draftkings,fanduel).

Both sides of every point are recorded on purpose. A one-sided price is a price
with the vig still in it; a matched Over/Under pair de-vigs to a probability
without needing a run-scoring model of my own, and the market's total is better
calibrated than anything I could fit this afternoon.
"""

# game | book | Over price | Under price, keyed by point
TOTALS_RAW = """
NYY@CHC|FanDuel|12.5|300|-430
NYY@CHC|FanDuel|13.5|420|-650
NYY@CHC|FanDuel|14.5|540|-950
NYY@CHC|FanDuel|15.5|750|-1600
NYY@CHC|DraftKings|12.0|249|-349
NYY@CHC|DraftKings|12.5|267|-380
NYY@CHC|DraftKings|13.0|349|-530
NYY@CHC|DraftKings|13.5|373|-579
PIT@CIN|FanDuel|12.5|420|-650
PIT@CIN|FanDuel|13.5|600|-1100
PIT@CIN|DraftKings|12.5|400|-640
PHI@BAL|FanDuel|12.5|340|-500
PHI@BAL|FanDuel|13.5|480|-800
PHI@BAL|FanDuel|14.5|630|-1200
PHI@BAL|DraftKings|12.0|303|-443
PHI@BAL|DraftKings|12.5|322|-479
PHI@BAL|DraftKings|13.0|441|-730
PHI@BAL|DraftKings|13.5|470|-800
STL@TOR|FanDuel|12.5|450|-720
STL@TOR|FanDuel|13.5|630|-1200
STL@TOR|DraftKings|12.0|488|-840
STL@TOR|DraftKings|12.5|508|-900
ARI@CLE|FanDuel|12.5|330|-480
ARI@CLE|FanDuel|13.5|460|-750
ARI@CLE|FanDuel|14.5|600|-1100
ARI@CLE|DraftKings|12.0|306|-450
ARI@CLE|DraftKings|12.5|325|-484
ARI@CLE|DraftKings|13.0|435|-720
ARI@CLE|DraftKings|13.5|461|-780
MIA@NYM|FanDuel|12.5|390|-590
MIA@NYM|FanDuel|13.5|560|-1000
MIA@NYM|FanDuel|14.5|750|-1600
MIA@NYM|DraftKings|12.0|355|-542
MIA@NYM|DraftKings|12.5|374|-581
WSH@ATL|FanDuel|12.5|280|-390
WSH@ATL|FanDuel|13.5|390|-590
WSH@ATL|FanDuel|14.5|480|-800
WSH@ATL|FanDuel|15.5|700|-1400
WSH@ATL|DraftKings|12.0|238|-331
WSH@ATL|DraftKings|12.5|254|-359
WSH@ATL|DraftKings|13.0|334|-501
WSH@ATL|DraftKings|13.5|359|-550
TEX@HOU|FanDuel|12.5|460|-750
TEX@HOU|FanDuel|13.5|680|-1400
TEX@HOU|FanDuel|14.5|900|-2500
TEX@HOU|DraftKings|12.0|422|-690
TEX@HOU|DraftKings|12.5|441|-730
KC@COL|FanDuel|14.5|240|-330
KC@COL|FanDuel|15.5|330|-480
KC@COL|FanDuel|16.5|420|-650
KC@COL|FanDuel|17.5|560|-1000
KC@COL|DraftKings|14.0|216|-297
KC@COL|DraftKings|14.5|232|-322
KC@COL|DraftKings|15.0|294|-428
KC@COL|DraftKings|15.5|316|-468
MIL@LAA|FanDuel|12.5|285|-400
MIL@LAA|FanDuel|13.5|400|-620
MIL@LAA|FanDuel|14.5|520|-900
MIL@LAA|DraftKings|12.0|270|-386
MIL@LAA|DraftKings|12.5|290|-419
MIL@LAA|DraftKings|13.0|392|-620
MIL@LAA|DraftKings|13.5|420|-680
DET@ATH|FanDuel|13.5|210|-280
DET@ATH|FanDuel|14.5|265|-370
DET@ATH|FanDuel|15.5|360|-530
DET@ATH|FanDuel|16.5|450|-720
DET@ATH|DraftKings|14.0|241|-337
DET@ATH|DraftKings|14.5|257|-364
DET@ATH|DraftKings|15.0|329|-491
DET@ATH|DraftKings|15.5|351|-534
SF@SD|FanDuel|11.5|255|-350
SF@SD|FanDuel|12.5|340|-500
SF@SD|FanDuel|13.5|480|-800
SF@SD|FanDuel|14.5|630|-1200
SF@SD|DraftKings|11.0|224|-309
SF@SD|DraftKings|11.5|250|-351
SF@SD|DraftKings|12.0|307|-451
SF@SD|DraftKings|12.5|326|-486
SF@SD|DraftKings|13.0|436|-720
BOS@LAD|FanDuel|11.5|290|-410
BOS@LAD|FanDuel|12.5|360|-530
BOS@LAD|FanDuel|13.5|520|-900
BOS@LAD|DraftKings|11.0|240|-335
BOS@LAD|DraftKings|11.5|266|-378
BOS@LAD|DraftKings|12.0|329|-491
BOS@LAD|DraftKings|12.5|348|-528
BOS@LAD|DraftKings|13.0|463|-780
MIN@SEA|FanDuel|11.5|390|-590
MIN@SEA|FanDuel|12.5|500|-850
MIN@SEA|FanDuel|13.5|750|-1600
MIN@SEA|DraftKings|11.0|329|-493
MIN@SEA|DraftKings|11.5|357|-546
MIN@SEA|DraftKings|12.0|441|-730
MIN@SEA|DraftKings|12.5|459|-770
CWS@TB|FanDuel|11.5|300|-430
CWS@TB|FanDuel|12.5|400|-620
CWS@TB|FanDuel|13.5|560|-1000
CWS@TB|FanDuel|14.5|750|-1600
CWS@TB|DraftKings|11.0|283|-409
CWS@TB|DraftKings|11.5|314|-464
CWS@TB|DraftKings|12.0|388|-610
CWS@TB|DraftKings|12.5|407|-650
DET@ATH|FanDuel|16.5|450|-720
"""

# Which starter pitches in which game -- so a K leg and a total leg from the same
# game can be flagged. They are positively correlated (a low-scoring game and a
# high-strikeout start are the same afternoon seen from two angles), which raises
# the true joint above the independence product and lowers what the book will
# actually pay. Both books reprice a multi-leg same-game combination as an SGP+.
#
# Derived from each pitcher's OPPONENT in kprops.json, not from memory of who
# plays where -- a first pass at this assigned Wacha to STL@TOR and Sugano to
# BOS@LAD, and both were wrong. Pairing on "A's opponent is B's team" closes all
# 15 games with no leftovers, which is the check that it is right.
GAME_OF = {
    "Paul Skenes": "PIT@CIN", "Hunter Greene": "PIT@CIN",
    "Nathan Eovaldi": "TEX@HOU", "Hunter Brown": "TEX@HOU",
    "Shota Imanaga": "NYY@CHC", "Will Warren": "NYY@CHC",
    "Bryce Miller": "MIN@SEA", "Zebby Matthews": "MIN@SEA",
    "Shane Drohan": "MIL@LAA", "Ryan Johnson": "MIL@LAA",
    "Freddy Peralta": "MIA@NYM", "Janson Junk": "MIA@NYM",
    "Casey Mize": "DET@ATH", "Jeffrey Springs": "DET@ATH",
    "Foster Griffin": "WSH@ATL", "Bryce Elder": "WSH@ATL",
    "Ranger Suarez": "BOS@LAD", "Edgardo Henriquez": "BOS@LAD",
    "Kyle Leahy": "STL@TOR", "Dylan Cease": "STL@TOR",
    "Michael Wacha": "KC@COL", "Tomoyuki Sugano": "KC@COL",
    "Carson Whisenhunt": "SF@SD", "Bradgley Rodriguez": "SF@SD",
    "Nick Martinez": "CWS@TB", "Erick Fedde": "CWS@TB",
    "Tanner Bibee": "ARI@CLE", "Mitch Bratt": "ARI@CLE",
    "Brandon Young": "PHI@BAL",   # Phillies starter not posted
}

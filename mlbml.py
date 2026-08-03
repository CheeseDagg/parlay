"""FanDuel MLB moneylines for the 2026-07-31 -> 2026-08-01 slates.

Why this file exists: a -200 per-leg ceiling deletes every heavy favourite on
the board, so the question stops being "what is the heaviest leg" and becomes
"which light leg is least overpriced." Vig is what separates those two, and a
matched MLB moneyline pair is the lowest-vig market FanDuel posts all weekend
-- a -116/+106 pair books at about 2.3% over round, against roughly 4% for an
MMA pair and far worse for boxing. Ten cheap legs beat six expensive ones when
every leg has to be light anyway.

Format: UTC|AWAY@HOME|TEAM|PRICE|OPP_PRICE
Both sides listed so the de-vig sees the whole book and a solver cannot take
both teams in one game.
"""

MLBML_RAW = """
2026-07-31T22:11Z|PIT@CIN|Cincinnati Reds ML|110|-118
2026-07-31T22:11Z|PIT@CIN|Pittsburgh Pirates ML|-118|110
2026-07-31T23:06Z|PHI@BAL|Baltimore Orioles ML|-112|102
2026-07-31T23:06Z|PHI@BAL|Philadelphia Phillies ML|102|-112
2026-07-31T23:08Z|STL@TOR|Toronto Blue Jays ML|-184|170
2026-07-31T23:08Z|STL@TOR|St. Louis Cardinals ML|170|-184
2026-07-31T23:11Z|ARI@CLE|Cleveland Guardians ML|-138|126
2026-07-31T23:11Z|ARI@CLE|Arizona Diamondbacks ML|126|-138
2026-07-31T23:11Z|CWS@TB|Tampa Bay Rays ML|-128|120
2026-07-31T23:11Z|CWS@TB|Chicago White Sox ML|120|-128
2026-07-31T23:11Z|MIA@NYM|New York Mets ML|-112|102
2026-07-31T23:11Z|MIA@NYM|Miami Marlins ML|102|-112
2026-07-31T23:16Z|WSH@ATL|Atlanta Braves ML|-116|106
2026-07-31T23:16Z|WSH@ATL|Washington Nationals ML|106|-116
2026-08-01T00:16Z|TEX@HOU|Houston Astros ML|-122|112
2026-08-01T00:16Z|TEX@HOU|Texas Rangers ML|112|-122
2026-08-01T01:39Z|MIL@LAA|Milwaukee Brewers ML|-156|144
2026-08-01T01:39Z|MIL@LAA|Los Angeles Angels ML|144|-156
2026-08-01T01:41Z|DET@ATH|Detroit Tigers ML|-132|122
2026-08-01T01:41Z|DET@ATH|Athletics ML|122|-132
2026-08-01T01:46Z|SF@SD|San Diego Padres ML|-142|132
2026-08-01T01:46Z|SF@SD|San Francisco Giants ML|132|-142
2026-08-01T02:11Z|BOS@LAD|Los Angeles Dodgers ML|-128|120
2026-08-01T02:11Z|BOS@LAD|Boston Red Sox ML|120|-128
2026-08-01T02:11Z|MIN@SEA|Seattle Mariners ML|-160|148
2026-08-01T02:11Z|MIN@SEA|Minnesota Twins ML|148|-160
2026-08-01T19:08Z|STL@TOR2|Toronto Blue Jays ML|-130|120
2026-08-01T19:08Z|STL@TOR2|St. Louis Cardinals ML|120|-130
2026-08-01T20:11Z|CWS@TB2|Tampa Bay Rays ML|-160|148
2026-08-01T20:11Z|CWS@TB2|Chicago White Sox ML|148|-160
2026-08-01T20:11Z|MIA@NYM2|New York Mets ML|-126|118
2026-08-01T20:11Z|MIA@NYM2|Miami Marlins ML|118|-126
2026-08-01T20:11Z|MIN@SEA2|Seattle Mariners ML|-156|144
2026-08-01T20:11Z|MIN@SEA2|Minnesota Twins ML|144|-156
2026-08-01T22:41Z|PIT@CIN2|Pittsburgh Pirates ML|-112|102
2026-08-01T22:41Z|PIT@CIN2|Cincinnati Reds ML|102|-112
2026-08-01T23:06Z|PHI@BAL2|Philadelphia Phillies ML|-130|120
2026-08-01T23:06Z|PHI@BAL2|Baltimore Orioles ML|120|-130
2026-08-01T23:11Z|TEX@HOU2|Texas Rangers ML|-122|114
2026-08-01T23:11Z|TEX@HOU2|Houston Astros ML|114|-122
2026-08-01T23:16Z|ARI@CLE2|Cleveland Guardians ML|-154|142
2026-08-01T23:16Z|ARI@CLE2|Arizona Diamondbacks ML|142|-154
2026-08-01T23:16Z|WSH@ATL2|Atlanta Braves ML|-184|170
2026-08-01T23:16Z|WSH@ATL2|Washington Nationals ML|170|-184
2026-08-01T23:16Z|NYY@CHC2|New York Yankees ML|-124|114
2026-08-01T23:16Z|NYY@CHC2|Chicago Cubs ML|114|-124
2026-08-02T00:11Z|KC@COL2|Colorado Rockies ML|-114|104
2026-08-02T00:11Z|KC@COL2|Kansas City Royals ML|104|-114
2026-08-02T01:11Z|BOS@LAD2|Los Angeles Dodgers ML|-154|142
2026-08-02T01:11Z|BOS@LAD2|Boston Red Sox ML|142|-154
2026-08-02T01:39Z|MIL@LAA2|Milwaukee Brewers ML|-114|106
2026-08-02T01:39Z|MIL@LAA2|Los Angeles Angels ML|106|-114
2026-08-02T01:41Z|DET@ATH2|Detroit Tigers ML|-132|122
2026-08-02T01:41Z|DET@ATH2|Athletics ML|122|-132
"""

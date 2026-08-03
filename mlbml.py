"""FanDuel MLB moneylines for the 2026-08-03 slate.

Pulled from the-odds-api (sport=baseball_mlb, markets=h2h, bookmakers=fanduel)
on 2026-08-03 ~21:40Z. Two independently-worded draws with the query parameters
in a different order agreed on all 16 prices, and every matched pair holds at
1.6-2.4% over round -- which is what a real MLB two-way book looks like and is
what a fabricated one almost never does. See the note at the bottom of this file
about why that check is not optional on this channel.

Why this file exists: a -200 per-leg ceiling deletes every heavy favourite on
the board, so the question stops being "what is the heaviest leg" and becomes
"which light leg is least overpriced." Vig is what separates those two, and a
matched MLB moneyline pair is the lowest-vig market FanDuel posts all week --
a -146/+136 pair books at about 1.9% over round, against roughly 6% for an MMA
pair and far worse for boxing.

STANDING INSTRUCTION, recorded here so a future reader does not "fix" the fact
that these legs never appear on a ticket: no moneylining baseball teams. The
legs are loaded anyway because the de-vig needs them -- the moneyline pair is
what tells the totals ladder which side of the game the market actually likes,
and dropping them from the file would make that opinion unavailable rather than
merely unused. Filter them out at solve time (--dropfam=ML), not here.

Format: UTC|AWAY@HOME|TEAM|PRICE|OPP_PRICE
Both sides listed so the de-vig sees the whole book and a solver cannot take
both teams in one game.

The 08-04 and 08-05 games were in the feed with no FanDuel h2h posted yet
(empty bookmaker list, not an error), so there is nothing here to record for
them. That is a genuine absence, not a fetch that failed.
"""

MLBML_RAW = """
2026-08-03T22:41Z|WSH@PHI|Philadelphia Phillies ML|-146|136
2026-08-03T22:41Z|WSH@PHI|Washington Nationals ML|136|-146
2026-08-03T23:06Z|STL@NYY|New York Yankees ML|-205|190
2026-08-03T23:06Z|STL@NYY|St. Louis Cardinals ML|190|-205
2026-08-03T23:41Z|PIT@MIL|Milwaukee Brewers ML|-146|136
2026-08-03T23:41Z|PIT@MIL|Pittsburgh Pirates ML|136|-146
2026-08-04T00:06Z|LAD@CHC|Los Angeles Dodgers ML|-120|110
2026-08-04T00:06Z|LAD@CHC|Chicago Cubs ML|110|-120
2026-08-04T00:06Z|SF@TEX|Texas Rangers ML|-122|114
2026-08-04T00:06Z|SF@TEX|San Francisco Giants ML|114|-122
2026-08-04T00:10Z|TOR@HOU|Houston Astros ML|-128|120
2026-08-04T00:10Z|TOR@HOU|Toronto Blue Jays ML|120|-128
2026-08-04T00:41Z|TB@COL|Tampa Bay Rays ML|-172|158
2026-08-04T00:41Z|TB@COL|Colorado Rockies ML|158|-172
2026-08-04T01:41Z|SD@ARI|Arizona Diamondbacks ML|-110|100
2026-08-04T01:41Z|SD@ARI|San Diego Padres ML|100|-110
"""

# ---------------------------------------------------------------------------
# HOW THESE PRICES GOT HERE, AND WHY EVERY ONE WAS CHECKED TWICE
#
# Direct HTTPS to api.the-odds-api.com is blocked from this container (the
# egress proxy allowlist returns 403; api.github.com and pypi.org return 200,
# so it is the host, not the network). The only channel that reaches the API is
# WebFetch -- and WebFetch pipes the response through a small summarizing model
# before I ever see it. That model CONFABULATES when asked for a verbatim dump.
# Two separate prompts of the form "output the raw JSON exactly" each returned
# a complete, plausible, internally consistent MLB slate dated 2026-07-31 ->
# 2026-08-02: games that had already been played, prices that were never in the
# response. A question-shaped prompt ("how many events, and what price does
# FanDuel post on each?") reads correctly. It was also caught DROPPING MINUS
# SIGNS -- a +175 dog rendered as a -175 favourite, which is the single worst
# error this file could carry, because it survives every sanity check a human
# would apply by eye.
#
# So nothing here is trusted on its face. Three structural instruments, none of
# which depend on believing the channel:
#
#   1. TWO DRAWS, parameters reordered (the API caches 15 minutes per URL, so
#      reordering busts it) and the question worded differently. Require exact
#      agreement. Rows that appeared in only one draw are excluded, not
#      averaged.
#   2. IMPLIED-PROBABILITY SUM. -p -> p/(p+100), +p -> 100/(p+100). A real
#      two-way market sums 1.02-1.10. Every pair above sums 1.016-1.024. A
#      flipped sign blows this up immediately -- that is how the nine bad rows
#      elsewhere in this board were found.
#   3. LADDER MONOTONICITY, in totals.py: as the point rises, Over must get
#      longer and Under shorter, with no reversals.
#
# The failure mode this whole package exists to catch is a number that is wrong
# in a way that looks exactly like a number that is right. A confabulated price
# is the purest instance of it. Check the ticket against the FanDuel app before
# placing it -- not because the checks above are weak, but because they are
# structural, and a self-consistent fabrication passes structural checks.
# ---------------------------------------------------------------------------

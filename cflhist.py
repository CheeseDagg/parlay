#!/usr/bin/env python3
"""cflhist.py — CFL base rates from Wikipedia per-team season pages.

    python3 cflhist.py                 # fetch + build cflhist.json / .txt
    python3 cflhist.py --selftest

CFL legs show up on FanDuel's Thursday/Friday boards with no empirical
grounding at all — the only sport on the board where a pick would be pure
hunch. srcprobe rounds 4-4c mapped the reachable inventory: ESPN 403s,
fixturedownload has nothing, the league season pages carry standings only.
What exists is the per-team season articles (9/9 for 2024 and 2025), whose
Schedule wikitable was dumped by round 4c before this parser was written:

    Week | Game | Date | Kickoff | Opponent | Results(Score|Record) | ...
    1 | 1 | Thu, June 5 | 7:00 p.m. CST | vs. Ottawa Redblacks | W 31-26 | 1-0 | ...

Odds history is MEASURED-ABSENT on every probed route, so this file grounds
what results alone can ground: home edge and the totals distribution against
the rung ladder. No de-vig calibration pretends to happen here.

TRUST, because a scraper that guesses is worse than no scraper:
  * home/away comes from the vs./at prefix; the page's own W/L letter must
    agree with the score order or the row is refused;
  * every game sits on TWO team pages (home's and away's) — rows are joined
    on (date, home, away) and the scores must agree flipped; disagreements
    are excluded LOUDLY, singletons are counted as unverified;
  * the playoff table shares the Schedule heading but lacks the Week column
    — recognized by its header row, not by table order;
  * a season whose page drifts from the dumped shape fails ITS validation
    line in the output instead of silently contributing zero games.
"""
import json, os, re, sys, time, urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, 'cflhist.json')
OUT_TXT = os.path.join(HERE, 'cflhist.txt')
BUA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TEAMS = ["Saskatchewan Roughriders", "Hamilton Tiger-Cats", "Winnipeg Blue Bombers",
         "Montreal Alouettes", "BC Lions", "Calgary Stampeders", "Edmonton Elks",
         "Ottawa Redblacks", "Toronto Argonauts"]
SEASONS = [2022, 2023, 2024, 2025]
# Wikipedia abbreviates the long months and is not even consistent about it:
# round 4d saw "Aug 2", "Sept 6" and "Sep 27" on the SAME page. Every form
# observed or plausible gets a key; the date regex stops at periods anyway.
MONTHS = {m: i + 1 for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'])}
MONTHS.update({'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'Jun': 6, 'Jul': 7,
               'Aug': 8, 'Sep': 9, 'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12})
RUNGS = [41.5, 43.5, 45.5, 47.5, 49.5, 51.5, 53.5, 55.5]


class Tables(HTMLParser):
    """Every <table class=wikitable> on a page as rows of cell texts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.t, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table' and 'wikitable' in (a.get('class') or ''):
            self.t = []
        elif self.t is not None and tag == 'tr':
            self.row = []
        elif self.row is not None and tag in ('td', 'th'):
            self.cell = []

    def handle_endtag(self, tag):
        if tag == 'table' and self.t is not None:
            self.out.append(self.t); self.t = None
        elif tag == 'tr' and self.row is not None:
            if self.row:
                self.t.append(self.row)
            self.row = None
        elif tag in ('td', 'th') and self.cell is not None:
            self.row.append(re.sub(r'\s+', ' ', ' '.join(self.cell)).strip())
            self.cell = None

    def handle_data(self, d):
        if self.cell is not None:
            self.cell.append(d)


def parse_schedule(html, team, year):
    """Regular-season game rows for one team page. Refuses what it cannot
    prove: rows failing the W/L-vs-score check come back in `bad`; neutral-
    site rows (no vs./at prefix -- Touchdown Atlantic) come back counted in
    `neutral` rather than being guessed a home side."""
    p = Tables(); p.feed(html)
    games, bad, neutral = [], [], 0
    for t in p.out:
        if not t or not t[0]:
            continue
        # the regular-season log: Week first, then Date/Opponent among headers.
        # The PRESEASON table has identical headers but letters its weeks
        # (A/B/C, round 4d) -- the numeric-week test below is what drops it.
        h = [c.lower() for c in t[0]]
        if h[0] != 'week' or 'opponent' not in h or 'date' not in h:
            continue
        for row in t:
            if len(row) < 7 or not row[0].isdigit():
                continue              # header / subheader / bye / preseason
            m_date = re.match(r'\w{3},\s*(\w+)\s+(\d{1,2})', row[2])
            m_sc = re.search(r'([WLT])\s*(\d+)\s*[–-]\s*(\d+)', row[5])
            mo = MONTHS.get(m_date.group(1)) if m_date else None
            if not (m_date and m_sc and mo):
                continue
            m_opp = re.match(r'(vs\.?|at)\s+(.+)', row[4])
            if not m_opp:
                neutral += 1          # a real game, but neither side is home
                continue
            wlt, pf, pa = m_sc.group(1), int(m_sc.group(2)), int(m_sc.group(3))
            if (wlt == 'W' and pf <= pa) or (wlt == 'L' and pf >= pa) \
               or (wlt == 'T' and pf != pa):
                bad.append(f"{team} {year}: '{row[5]}' letter disagrees with score")
                continue
            home = m_opp.group(1).startswith('vs')
            games.append({'date': f"{year}-{mo:02d}-{int(m_date.group(2)):02d}",
                          'home': team if home else m_opp.group(2).strip(),
                          'away': m_opp.group(2).strip() if home else team,
                          'hs': pf if home else pa, 'as': pa if home else pf})
    return games, bad, neutral


def merge(rows):
    """Join per-page rows into games; both pages must tell the same story.
    -> (games, n_unverified, mismatches)"""
    by = {}
    for g in rows:
        by.setdefault((g['date'], g['home'], g['away']), []).append(g)
    games, unver, mism = [], 0, []
    for k, v in sorted(by.items()):
        scores = {(g['hs'], g['as']) for g in v}
        if len(scores) > 1:
            mism.append(f"{k}: pages disagree {sorted(scores)}")
            continue
        if len(v) == 1:
            unver += 1
        games.append(v[0])
    return games, unver, mism


def stats(games):
    n = len(games)
    hw = sum(1 for g in games if g['hs'] > g['as'])
    ties = sum(1 for g in games if g['hs'] == g['as'])
    tots = sorted(g['hs'] + g['as'] for g in games)
    mean = sum(tots) / n if n else 0
    def wilson(k, n, z=1.96):
        if not n:
            return (0, 0)
        p, z2 = k / n, z * z
        c = (p + z2 / (2 * n)) / (1 + z2 / n)
        w = z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5) / (1 + z2 / n)
        return (c - w, c + w)
    dec = n - ties
    rungs = {}
    for r in RUNGS:
        k = sum(1 for t in tots if t < r)
        lo, hi = wilson(k, n)
        rungs[str(r)] = {'p_under': round(k / n, 4) if n else 0, 'n': n,
                         'lo': round(lo, 4), 'hi': round(hi, 4)}
    return {'n': n, 'home_w': hw, 'ties': ties,
            'home_pct': round(hw / dec, 4) if dec else 0,
            'home_lo_hi': [round(x, 4) for x in wilson(hw, dec)],
            'mean_total': round(mean, 2), 'rungs': rungs}


def main():
    allrows, notes = [], []
    for yr in SEASONS:
        yrows, ybad, misses, yneu = [], [], [], 0
        for t in TEAMS:
            u = f"https://en.wikipedia.org/wiki/{yr}_{t.replace(' ', '_')}_season"
            try:
                r = urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": BUA}), timeout=30)
                g, b, neu = parse_schedule(r.read().decode('utf-8', 'replace'), t, yr)
                if not g:
                    misses.append(t.split()[-1] + ':0 rows')
                yrows += g; ybad += b; yneu += neu
            except Exception as e:
                misses.append(f"{t.split()[-1]}:{type(e).__name__}")
            time.sleep(1)
        # 18 games x 9 teams = 162 rows when every game sits on both pages
        note = f"{yr}: {len(yrows)}/162 page-rows" + \
               (f", {yneu} neutral-site row(s) skipped" if yneu else "") + \
               (f", PROBLEMS {misses}" if misses else "") + \
               (f", {len(ybad)} refused rows" if ybad else "")
        notes.append(note); allrows += yrows
        for b in ybad[:5]:
            notes.append(f"    {b}")
    games, unver, mism = merge(allrows)
    s = stats(games)
    lines = ["CFL history — Wikipedia per-team season pages (results only;",
             "odds history measured-absent on every probed route)", ""]
    lines += notes
    lines += [f"merged: {s['n']} games, {unver} single-page (unverified), "
              f"{len(mism)} cross-page mismatches EXCLUDED"] + \
             [f"    {m}" for m in mism[:8]]
    lines += ["", f"home wins {s['home_pct']*100:.1f}% of decided "
              f"(95% {s['home_lo_hi'][0]*100:.1f}-{s['home_lo_hi'][1]*100:.1f}, "
              f"n={s['n'] - s['ties']}); ties {s['ties']}",
              f"mean total {s['mean_total']}", "", "P(total UNDER line):"]
    for r in RUNGS:
        v = s['rungs'][str(r)]
        lines.append(f"  U{r:<5} {v['p_under']*100:5.1f}%  "
                     f"(95% {v['lo']*100:.1f}-{v['hi']*100:.1f})")
    txt = '\n'.join(lines)
    print(txt)
    json.dump({'built_from': 'wikipedia per-team season pages',
               'seasons': SEASONS, 'stats': s,
               'games': games}, open(OUT_JSON, 'w'), indent=1)
    open(OUT_TXT, 'w').write(txt + '\n')
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    # the round-4c dump, verbatim -- the parser is written against THIS
    page = """
    <table class="wikitable"><tr><th>Week</th><th>Game</th><th>Date</th>
    <th>Kickoff</th><th>Opponent</th><th colspan=2>Results</th><th>TV</th>
    <th>Venue</th><th>Attendance</th></tr>
    <tr><th>Score</th><th>Record</th></tr>
    <tr><td>1</td><td>1</td><td>Thu, June 5</td><td>7:00 p.m. CST</td>
    <td>vs. Ottawa Redblacks</td><td>W 31–26</td><td>1–0</td>
    <td>TSN</td><td>Mosaic Stadium</td><td>25,973</td></tr>
    <tr><td>2</td><td>2</td><td>Fri, June 13</td><td>8:00 p.m. CST</td>
    <td>at Hamilton Tiger-Cats</td><td>L 17–20</td><td>1–1</td>
    <td>TSN</td><td>Hamilton Stadium</td><td>22,000</td></tr>
    <tr><td>A</td><td>Bye</td></tr>
    <tr><td>3</td><td>3</td><td>Fri, June 20</td><td>7:00 p.m. CST</td>
    <td>vs. BC Lions</td><td>W 20–27</td><td>2–1</td>
    <td>TSN</td><td>Mosaic Stadium</td><td>25,000</td></tr></table>
    <table class="wikitable"><tr><th>Game</th><th>Date</th><th>Kickoff</th>
    <th>Opponent</th><th colspan=2>Results</th><th>TV</th><th>Venue</th>
    <th>Attendance</th></tr>
    <tr><td>West Final</td><td>Sat, Nov 8</td><td>5:00 p.m.</td>
    <td>vs. BC Lions</td><td>W 30–10</td><td>1–0</td><td>TSN</td>
    <td>Mosaic Stadium</td><td>30,000</td></tr></table>"""
    g, bad, _ = parse_schedule(page, 'Saskatchewan Roughriders', 2025)
    chk(len(g) == 2,
        f"the dumped shape parses: 2 clean games (got {len(g)}) -- the bye is "
        "skipped and the playoff table (no Week column) is not regular season")
    chk(g[0] == {'date': '2025-06-05', 'home': 'Saskatchewan Roughriders',
                 'away': 'Ottawa Redblacks', 'hs': 31, 'as': 26},
        "'vs. Ottawa Redblacks / W 31-26' is a home win 31-26 on June 5")
    chk(g[1] == {'date': '2025-06-13', 'home': 'Hamilton Tiger-Cats',
                 'away': 'Saskatchewan Roughriders', 'hs': 20, 'as': 17},
        "'at Hamilton / L 17-20' puts Hamilton home 20, Sask away 17")
    chk(len(bad) == 1 and 'W 20–27' in bad[0],
        "a W whose score reads as a loss is REFUSED by name, not guessed at")

    # round 4d verbatim: abbreviated months (three spellings on live pages),
    # letter-week preseason, the ǁ-decorated Game cell, and the prefix-less
    # neutral-site Touchdown Atlantic row
    page2 = """
    <table class="wikitable"><tr><th>Week</th><th>Game</th><th>Date</th>
    <th>Kickoff</th><th>Opponent</th><th colspan=2>Results</th><th>TV</th></tr>
    <tr><th>Score</th><th>Record</th></tr>
    <tr><td>B</td><td>1</td><td>Sat, May 24</td><td>2:00 p.m. CST</td>
    <td>at Winnipeg Blue Bombers</td><td>L 9–15</td><td>0–1</td><td>CFL+</td></tr>
    <tr><td>9</td><td>8</td><td>Sat, Aug 2</td><td>5:00 p.m. CST</td>
    <td>at Montreal Alouettes</td><td>W 34–6</td><td>7–1</td><td>TSN</td></tr>
    <tr><td>13</td><td>ǁ 11 ǁ</td><td>Sun, Aug 31</td><td>5:00 p.m. CST</td>
    <td>vs. Winnipeg Blue Bombers</td><td>W 34–30</td><td>9–2</td><td>TSN</td></tr>
    <tr><td>14</td><td>12</td><td>Sat, Sept 6</td><td>2:00 p.m. CST</td>
    <td>at Winnipeg Blue Bombers</td><td>W 21–13</td><td>10–2</td><td>TSN</td></tr>
    <tr><td>17</td><td>14</td><td>Sat, Sep 27</td><td>5:00 p.m. CST</td>
    <td>at Edmonton Elks</td><td>L 25–27</td><td>10–4</td><td>TSN</td></tr>
    <tr><td>8</td><td>6</td><td>Sat, July 29</td><td>4:00 p.m. EDT</td>
    <td>Saskatchewan Roughriders</td><td>W 31–13</td><td>6–0</td><td>TSN</td></tr>
    </table>"""
    g2, bad2, neu2 = parse_schedule(page2, 'Toronto Argonauts', 2025)
    chk([x['date'] for x in g2] == ['2025-08-02', '2025-08-31',
                                    '2025-09-06', '2025-09-27'],
        "'Aug', 'Sept' and 'Sep' all parse -- the three spellings round 4d "
        "saw on live pages; the season no longer ends in July")
    chk(not any(x['date'].startswith('2025-05') for x in g2),
        "the letter-week preseason row (B) is dropped by the numeric-week "
        "test, so May never contaminates the base again")
    chk(g2[1]['hs'] == 34 and g2[1]['home'] == 'Toronto Argonauts',
        "the decorated Game cell still parses around its markers")
    chk(neu2 == 1 and bad2 == [],
        "the prefix-less Touchdown Atlantic row is counted neutral, not "
        "guessed a home side and not silently dropped")

    h = {'date': '2025-06-05', 'home': 'Saskatchewan Roughriders',
         'away': 'Ottawa Redblacks', 'hs': 31, 'as': 26}
    games, unver, mism = merge([h, dict(h)])
    chk(len(games) == 1 and unver == 0 and not mism,
        "the same game from both team pages merges into one verified row")
    games, unver, mism = merge([h, dict(h, hs=32)])
    chk(not games and len(mism) == 1,
        "pages disagreeing on the score EXCLUDES the game loudly")
    games, unver, _ = merge([h])
    chk(len(games) == 1 and unver == 1,
        "a single-page game is kept but counted unverified")

    s = stats([h, {'date': '2025-06-13', 'home': 'Hamilton Tiger-Cats',
                   'away': 'Saskatchewan Roughriders', 'hs': 20, 'as': 17},
               {'date': '2025-06-20', 'home': 'BC Lions',
                'away': 'Calgary Stampeders', 'hs': 24, 'as': 24}])
    chk(s['n'] == 3 and s['home_w'] == 2 and s['ties'] == 1
        and s['home_pct'] == 1.0,
        "home% is over DECIDED games (2/2), the tie counted separately")
    chk(s['rungs']['41.5']['p_under'] == round(1 / 3, 4),
        "U41.5 sees one of three totals (37) under it")
    chk(s['rungs']['55.5']['lo'] < s['rungs']['55.5']['p_under'],
        "every rung carries its Wilson interval, n=3 wide")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

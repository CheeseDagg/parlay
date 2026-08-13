#!/usr/bin/env python3
"""linelog.py — record the day's posted MLB total lines, because nobody sells the history.

    python3 linelog.py            # snapshot today's board into mlblines.csv
    python3 linelog.py --selftest

srcprobe round 3 (2026-08-13) settled it: sportsbookreviewsonline, the one
known free archive of posted MLB lines, is an affiliate shell now — every
archive path serves the same marketing page, zero files. The rung-x-posted-
line question (is U10.5 at Coors the same bet as U10.5 at a pitcher's park
when the POSTED LINE says the market already knows?) cannot be answered from
anyone else's data. So this file records our own: every FanDuel MLB alt-total
rung the board carries, one row per (event date, game, label), refreshed all
day and frozen at first pitch.

The freeze is the point. parlay-refresh runs many times a day; each pregame
run REPLACES the game's rows so the last snapshot before start — the closest
thing to a closing line — is what survives. Once a game has started the
board shows live re-priced lines, and a live U8.5 quoted in the 6th inning
overwriting the pregame closer would poison the file in exactly the way
rule 17 exists to prevent. Started games never overwrite.

A season of days makes f5hist's rung table conditionable on the line that
was actually posted. Until then the csv just grows quietly with the refresh.
"""
import csv, datetime, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, 'mlblines.csv')
FIELDS = ['date', 'grp', 'fam', 'lab', 'side', 'line', 'price', 'p', 'logged']
CT_UTC_OFFSET = 5      # CDT; the hour only picks the event's local DATE


def event_date(t):
    """The event's CT calendar date from its UTC start '2026-08-13T23:10Z' --
    a 00:40Z first pitch belongs to the previous CT evening."""
    dt = datetime.datetime.strptime(t, '%Y-%m-%dT%H:%MZ')
    return (dt - datetime.timedelta(hours=CT_UTC_OFFSET)).date().isoformat()


def rows_from(markets, now_utc):
    """One row per MLB alt-total leg not yet started, from build()'s markets."""
    out = []
    for legs in markets.values():
        for l in legs:
            if l.get('sport') != 'MLB':
                continue
            m = re.search(r'\b(Over|Under)\s+(\d+(?:\.5)?)\b', l.get('lab', ''))
            if not m:
                continue
            if l.get('t', '') <= now_utc:          # started: frozen, never logged
                continue
            out.append({'date': event_date(l['t']), 'grp': l['grp'],
                        'fam': l.get('fam', ''), 'lab': l['lab'],
                        'side': m.group(1), 'line': m.group(2),
                        'price': l['price'], 'p': round(l['p'], 4),
                        'logged': now_utc})
    return out


def merge(old, new):
    """New pregame rows REPLACE same-key rows; everything else survives.
    Key = (date, grp, lab). new never contains started legs (rows_from)."""
    keep = {(r['date'], r['grp'], r['lab']): r for r in old}
    for r in new:
        keep[(r['date'], r['grp'], r['lab'])] = r
    return [keep[k] for k in sorted(keep)]


def main():
    import board
    markets = board.build('FanDuel', min_price=0)
    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')
    new = rows_from(markets, now)
    old = list(csv.DictReader(open(LOG))) if os.path.exists(LOG) else []
    merged = merge(old, new)
    with open(LOG, 'w', newline='') as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(merged)
    print(f"  mlblines: {len(new)} pregame leg(s) snapshotted, "
          f"{len(merged)} row(s) total ({len(merged) - len(old)} new)")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    mk = {('GT', 'CIN@CWS'): [
        {'p': 0.91, 'lab': 'CIN@CWS Over 13.5', 'price': -4000, 'grp': 'CIN@CWS',
         'fam': 'FG', 'sport': 'MLB', 't': '2026-08-13T23:10Z'},
        {'p': 0.93, 'lab': 'CIN@CWS Under 6.5 (F5)', 'price': -600, 'grp': 'CIN@CWS',
         'fam': 'F5', 'sport': 'MLB', 't': '2026-08-13T23:10Z'},
        {'p': 0.90, 'lab': 'CIN@CWS moneyline junk', 'price': -300, 'grp': 'CIN@CWS',
         'fam': 'ML', 'sport': 'MLB', 't': '2026-08-13T23:10Z'},
        {'p': 0.88, 'lab': 'Hammarby Under 3.5', 'price': -400, 'grp': 'HAM-XX',
         'fam': 'SU', 'sport': 'SOC', 't': '2026-08-13T23:10Z'}]}

    rows = rows_from(mk, '2026-08-13T18:00Z')
    chk(len(rows) == 2 and {r['fam'] for r in rows} == {'FG', 'F5'},
        "only MLB Over/Under rungs are logged -- moneylines and soccer are not "
        "this file's job")
    chk(rows[0]['side'] == 'Over' and rows[0]['line'] == '13.5',
        "side and line parse out of the label")
    chk(rows[0]['date'] == '2026-08-13',
        "a 23:10Z start is the same CT calendar day")
    chk(event_date('2026-08-14T00:40Z') == '2026-08-13',
        "a 00:40Z first pitch belongs to the previous CT evening")

    late = rows_from(mk, '2026-08-13T23:30Z')
    chk(late == [],
        "after first pitch NOTHING is logged -- a live re-priced line must "
        "never overwrite the pregame closer (rule 17's shape)")

    early = [{'date': '2026-08-13', 'grp': 'CIN@CWS', 'fam': 'FG',
              'lab': 'CIN@CWS Over 13.5', 'side': 'Over', 'line': '13.5',
              'price': -3000, 'p': '0.90', 'logged': '2026-08-13T12:00Z'}]
    m2 = merge(early, rows)
    over = [r for r in m2 if r['lab'] == 'CIN@CWS Over 13.5']
    chk(len(over) == 1 and over[0]['price'] == -4000,
        "a later pregame snapshot REPLACES the morning row -- last look "
        "before start is the closing line")
    m3 = merge(m2, [])
    chk(len(m3) == len(m2),
        "a run with nothing new (all games started) keeps every stored row")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

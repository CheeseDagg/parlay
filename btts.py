#!/usr/bin/env python3
"""btts.py — today's soccer BTTS (both teams to score) prices, No vs Yes.

    ODDS_API_KEY=... python3 btts.py     # runner does this; writes btts.json
    python3 btts.py --selftest

Built 8/19 for one question: "which games today have BTTS-No decently
favored over Yes". The board never carried this market because the odds
API serves btts only on the PER-EVENT endpoint -- one credit per event --
so it cannot ride along with the bulk board pull. This script spends
those credits deliberately: FanDuel only (he cannot bet a price another
book posts), today's kicks only, and it prints how many events FanDuel
actually quoted so silence reads as absence, not coverage.

The split is stated de-vig (two-way mult, same as every 2-way ladder in
this repo): pNo = (1/dNo) / (1/dNo + 1/dYes). "Decently favored" is the
CALLER's cut to make -- this file records every quote and takes no view.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'btts.json')

from scores import _get, ODDS_BASE   # same retry/read helper as the scores pull


def _dec(american):
    a = int(american)
    return 1 + (a / 100.0 if a > 0 else 100.0 / -a)


def devig_no(no_price, yes_price):
    """De-vig P(no goal for one side) from the two American prices, mult."""
    ino, iyes = 1.0 / _dec(no_price), 1.0 / _dec(yes_price)
    return ino / (ino + iyes)


def today_window_ct(now_utc):
    """(start, end) UTC bounds for 'the rest of today' in CT (UTC-5, August).

    Hardcoding -5 is wrong half the year; it is right for this file's whole
    purpose window (soccer season restart, August) and the error mode in
    November is a game listed an hour past midnight, not a wrong price."""
    ct = now_utc - timedelta(hours=5)
    end_ct = ct.replace(hour=23, minute=59, second=59)
    return now_utc, end_ct + timedelta(hours=5)


def pull(key):
    """Every layer that can drop a game gets COUNTED AND NAMED. The first run
    swallowed per-league and per-event errors with bare continues, and 'FD
    quoted 16' was indistinguishable from 'the pull half-failed' -- Ryan was
    looking at ~100 games in the app while this reported 31. Never again:
    a game leaves this census only with its exit written down."""
    sports = _get(f"{ODDS_BASE}/sports/?apiKey={key}")
    soccer = [s['key'] for s in sports
              if s.get('group') == 'Soccer' and s.get('active')]
    now = datetime.now(timezone.utc)
    lo, hi = today_window_ct(now)
    rows, unquoted, league_errs, event_errs = [], [], [], 0
    seen = future = 0
    for sp in soccer:
        try:
            evs = _get(f"{ODDS_BASE}/sports/{sp}/events?apiKey={key}")
        except Exception as e:
            league_errs.append(f"{sp}: {type(e).__name__}")
            continue
        for ev in evs:
            t = datetime.fromisoformat(ev['commence_time'].replace('Z', '+00:00'))
            if t > hi:
                future += 1
                continue
            if t < lo:
                continue
            seen += 1
            name = f"{ev.get('home_team')} v {ev.get('away_team')}"
            try:
                od = _get(f"{ODDS_BASE}/sports/{sp}/events/{ev['id']}/odds"
                          f"?apiKey={key}&bookmakers=fanduel&markets=btts"
                          f"&oddsFormat=american")
            except Exception as e:
                event_errs += 1
                unquoted.append(f"{name} [{sp}] -- FETCH {type(e).__name__}")
                continue
            got = False
            for bk in od.get('bookmakers') or []:
                for mk in bk.get('markets') or []:
                    if mk.get('key') != 'btts':
                        continue
                    px = {o.get('name'): o.get('price') for o in mk.get('outcomes') or []}
                    if 'Yes' not in px or 'No' not in px:
                        continue
                    got = True
                    rows.append({
                        'sport': sp, 'league': od.get('sport_title', sp),
                        'home': ev.get('home_team'), 'away': ev.get('away_team'),
                        't': ev['commence_time'],
                        'yes': int(px['Yes']), 'no': int(px['No']),
                        'p_no': round(devig_no(px['No'], px['Yes']), 4)})
            if not got:
                unquoted.append(f"{name} [{od.get('sport_title', sp)}] {ev['commence_time']}")
    rows.sort(key=lambda r: r['t'])
    return {'as_of': now.strftime('%Y-%m-%dT%H:%MZ'),
            'leagues_active': len(soccer), 'league_errors': league_errs,
            'seen_today': seen, 'seen_future': future,
            'event_fetch_errors': event_errs,
            'fd_quoted': len(rows), 'fd_unquoted': unquoted, 'rows': rows}


def selftest():
    ok = 0
    # 1) devig: -150/+120 -> No 57.9-ish, and the pair sums to 1 with its mirror
    p = devig_no(-150, 120)
    assert abs(p - (0.6 / (0.6 + 1 / 2.2))) < 1e-9, p
    assert abs(devig_no(-150, 120) + devig_no(120, -150) - 1.0) < 1e-12
    ok += 1
    # 2) even prices split evenly
    assert abs(devig_no(-110, -110) - 0.5) < 1e-12
    ok += 1
    # 3) decimal conversion both signs
    assert _dec(100) == 2.0 and _dec(-100) == 2.0 and abs(_dec(-250) - 1.4) < 1e-9
    ok += 1
    # 4) window: a 01:00Z kick tomorrow is TONIGHT in CT and must be kept
    now = datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc)
    lo, hi = today_window_ct(now)
    tonight = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
    assert lo <= tonight <= hi and not (lo <= tomorrow <= hi)
    ok += 1
    # 5) rows sort chronologically regardless of arrival order
    rs = [{'t': '2026-08-19T23:00:00Z'}, {'t': '2026-08-19T16:00:00Z'}]
    rs.sort(key=lambda r: r['t'])
    assert rs[0]['t'].endswith('16:00:00Z')
    ok += 1
    print(f"{ok}/5 checks pass")
    return 0


def main():
    key = os.environ.get('ODDS_API_KEY', '')
    if not key:
        print('no ODDS_API_KEY -- this runs on the Actions runner')
        return 1
    doc = pull(key)
    json.dump(doc, open(OUT, 'w'), indent=1)
    print(f"as_of {doc['as_of']} -- {doc['leagues_active']} active soccer leagues on "
          f"the API; {doc['seen_today']} events in today's CT window "
          f"({doc['seen_future']} later this week), FanDuel quoted btts on "
          f"{doc['fd_quoted']}, {len(doc['fd_unquoted'])} unquoted, "
          f"{doc['event_fetch_errors']} fetch errors")
    for le in doc['league_errors']:
        print(f"  !! league fetch failed: {le}")
    if doc['fd_unquoted']:
        print("  -- in-window but NO FanDuel btts quote via the API:")
        for u in doc['fd_unquoted']:
            print(f"     {u}")
    for r in doc['rows']:
        print(f"  {r['t']}  {r['home']} v {r['away']}  "
              f"No {r['no']:+d} / Yes {r['yes']:+d}  pNo={r['p_no']:.3f}  ({r['league']})")
    return 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

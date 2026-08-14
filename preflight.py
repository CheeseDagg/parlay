#!/usr/bin/env python3
"""preflight.py — run every gate a slip must clear, in one command.

    python3 preflight.py "BAL@MIN F5 Under 10.5" "Dallas Wings" ...
    python3 preflight.py --selftest

The rules were never the problem this week. Every loss was a rule that
existed and did not fire: the -350 floor was typed by hand, the hot-game
veto sat unread in a stale slate, the overlap between two slips was
computed AFTER both were placed, and slips.json -- which has done
cross-slip kill analysis since 8/1 -- was fed nothing on either losing
night.

So this is one command, run before money moves, that checks what a machine
can check and says out loud what it cannot:

  FLOOR    every leg -350 or heavier                      (rule 2)
  PLUS     no plus-money legs                             (rule 3)
  SOCCER   no 3-way sides -- derived DC only              (rule 8)
  METHOD   flags single-method fight legs                 (rules 9, 27)
  HOT      no mid-rung total on a hot game                (rule 25)
  TIE      a second leg has its first leg on file          (rule 40)
  STALE    no leg already under way, board is fresh        (rules 17, 18)
  DERIVED  synthesized prices named for confirmation       (rule 8)
  PARK     F5 totals at high-blowup or unknown parks       (f5hist)
  SOCBASE  soccer legs against their own league's history    (sochist)
  FORM     starter HR/9 and F5 form on MLB totals legs      (mlbform)
  OVERLAP  shared legs with every open slip, and the      (rule 28)
           chance one event kills them all
  SHAPE    fewer legs at fixed price, as a bound           (8/13 16-legger)
  SGPPAIR  same-game pairs named -- the book reprices them  (sgplog)
  DH       doubleheader days, where the feed keys one game (coverage)
  LIVE     every leg still ON the board, at the quoted price   (8/14 Mercado)
  LOG      calibration.csv and slips.json entries pending (rules 29, 31)

FAIL blocks. WARN is a judgement call that must be spoken aloud, not
skipped in silence.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# These are matched against the app's OWN wording, so they have to be the
# app's wording. 'on points' was here and 'by points' was not -- and FanDuel
# writes the single-method market as "Islam Makhachev by Points". So on 8/12 a
# slip with TWO single-method main-event legs came back "2 method leg(s), all
# double-chance": the gate saw only the two double chances, whose labels happen
# to contain 'ko/tko', and never saw the legs rule 27 exists to catch.
METHOD_WORDS = ('by ko', 'by tko', 'ko/tko', 'by submission', 'by sub',
                'by decision', 'by points', 'on points', 'by dq',
                'inside the distance', 'goes the distance',
                'by unanimous', 'by split', 'by majority')

def gate_floor(legs, floor=350):
    bad = [l for l in legs if l['price'] > -floor]
    return ('FAIL' if bad else 'PASS',
            f"{len(bad)} leg(s) lighter than -{floor}: "
            + ', '.join(f"{l['lab']} {l['price']:+d}" for l in bad)
            if bad else f"all {len(legs)} legs -{floor} or heavier")

def gate_plus(legs):
    bad = [l for l in legs if l['price'] > 0]
    return ('FAIL' if bad else 'PASS',
            f"plus-money: {', '.join(l['lab'] for l in bad)}" if bad
            else "no plus-money legs")

def gate_soccer(legs):
    bad = [l for l in legs if l.get('fam') == 'SOC' and 'DC' not in l['lab']]
    return ('FAIL' if bad else 'PASS',
            f"raw 3-way soccer: {', '.join(l['lab'] for l in bad)}" if bad
            else "no raw 3-way soccer sides")

def _ufc_rates():
    import json
    try:
        with open(os.path.join(HERE, 'ufchist.json')) as fh:
            return json.load(fh)
    except Exception:
        return None


def gate_method(legs, rates=None):
    """Rules 9 and 27 used to argue from scar tissue; now there is a
    denominator. When a method leg is on the slip, the modern-era base rates
    (ufchist.py, 5599 decided bouts since 2015) ride along, title fights
    split out because five championship rounds end differently."""
    m = [l for l in legs if any(w in l['lab'].lower() for w in METHOD_WORDS)]
    single = [l for l in m if ' or ' not in l['lab'].lower()]
    if not m:
        return 'PASS', "no method-of-victory legs"
    r = rates if rates is not None else _ufc_rates()
    ctx = ''
    if r and r.get('title') and r.get('non_title'):
        t, nt = r['title'], r['non_title']
        ctx = (f" | modern base since {r.get('modern_since','?')}: title "
               f"dec {t['dec']*100:.0f}/ko {t['ko']*100:.0f}/sub {t['sub']*100:.0f}"
               f" -- non-title dec {nt['dec']*100:.0f}/ko {nt['ko']*100:.0f}"
               f"/sub {nt['sub']*100:.0f} (ufchist)")
    else:
        ctx = " | no ufchist base rates readable -- the prop is priced blind"
    if single:
        return ('WARN', f"{len(single)} single-method leg(s) -- rule 27 wants "
                f"ML or a double chance: {', '.join(l['lab'] for l in single)}"
                + ctx)
    return 'PASS', f"{len(m)} method leg(s), all double-chance" + ctx

def gate_hot(legs, hot):
    """A totals leg on a hot game must be that game's TOP rung."""
    bad = []
    for l in legs:
        if l.get('fam') in ('F5', 'FG') and l.get('grp') in hot:
            if not l.get('is_top_rung', False):
                bad.append(f"{l['lab']} ({hot[l['grp']]})")
    if not hot:
        return 'WARN', "no hot-game data -- is MLBTool's slate today's?"
    return ('FAIL' if bad else 'PASS',
            "mid-rung on a HOT game: " + '; '.join(bad) if bad
            else f"{len(hot)} hot game(s), no mid-rungs taken")

def _ties():
    import json
    try:
        with open(os.path.join(HERE, 'ties.json')) as fh:
            return json.load(fh).get('ties', {})
    except Exception:
        return {}


def gate_tie(legs):
    """A second-leg soccer market must have its FIRST LEG on file.

    Rule 40. A 90-minute Double Chance prices the day and is blind to the tie,
    so on 8/13 Hammarby was taken as a routine home favourite when the tie was
    level from a 0-0 first leg -- a must-win, not a coast. 0-1 down with a red
    card it went 85% -> 17%, and the first-leg score had already gone past us
    that morning without being written down.

    The failure mode is silence, so silence is what this gate removes: a leg on
    a match listed in ties.json with no first_leg recorded FAILS. It cannot
    detect a tie nobody has listed -- that is what the WARN is for, and why
    ties.json is the thing to update, not this function.
    """
    ties = _ties()
    if not ties:
        return 'WARN', "ties.json unreadable -- no second-leg context checked"
    blind, ctx = [], []
    for l in legs:
        if l.get('fam') not in ('SOC', 'SOCT') and 'advance' not in l['lab'].lower():
            continue
        grp = (l.get('grp') or '').replace('SOC ', '')
        # BOTH halves of the tie name are checked against the label. A feed
        # leg carries the pair ('SOC Besiktas-Hradec Kralove'); a hand-entered
        # leg usually names only the favourite ('Besiktas to advance'), and
        # matching only the second half let exactly those legs walk past rule
        # 40 -- found by the hand-leg fixture, fixed in the gate.
        hit = next((k for k in ties if k in grp or grp in k
                    or k.split('-')[-1].lower() in l['lab'].lower()
                    or k.split('-')[0].lower() in l['lab'].lower()), None)
        if hit is None:
            continue                       # not a known tie; the sweep's job
        if not ties[hit].get('first_leg'):
            blind.append(f"{l['lab']} ({hit}: first leg NOT on file)")
        else:
            ctx.append(f"{hit} {ties[hit]['standing']}")
    if blind:
        return 'FAIL', "second leg with no first-leg score: " + '; '.join(blind)
    if ctx:
        return 'PASS', f"{len(ctx)} second-leg tie(s) with context: " + '; '.join(sorted(set(ctx)))
    return 'PASS', "no two-legged ties on this slip"


def hand_legs(path=None):
    """App-quoted legs from hand.py, shaped for the gates. These exist for
    the competitions the feed is structurally blind to (UEFA nights); until
    now they bypassed preflight entirely, so the gates covered exactly the
    half of the slip the feed could see and the slip READ as fully checked."""
    import json
    try:
        with open(path or os.path.join(HERE, 'handlegs.json')) as fh:
            d = json.load(fh)
    except Exception:
        return []
    out = []
    for l in d.get('legs', []):
        o = dict(l)
        o.setdefault('fam', 'HAND')
        o.setdefault('grp', o['lab'])
        out.append(o)
    return out


def board_age_min(now=None):
    """Minutes since pull_feeds wrote the feed, from the file's own header."""
    import re
    from datetime import datetime
    import other
    m = re.search(r'Generated (\d{4}-\d\d-\d\d \d\d:\d\d)Z', other.__doc__ or '')
    if not m:
        return None, None
    gen = m.group(1)
    import board
    n = datetime.strptime(now or board._utcnow(), "%Y-%m-%dT%H:%MZ")
    return (n - datetime.strptime(gen, "%Y-%m-%d %H:%M")).total_seconds() / 60, gen


def gate_stale(legs, now=None):
    """Refuse to bless a pregame price on a game that has already started.

    Two separate things went wrong on 8/13 and both look like this. Atlanta was
    quoted at -520 off a board that had since moved it to -550, and CIN@CWS F5
    Under 10.5 was quoted at 97.0% while the game was live at 8 runs in the
    third -- a number that was true at first pitch and worth about half that by
    the time it was said out loud.

    A leg whose event has started is not mispriced, it is UNPRICED: the pregame
    number is gone and live.py is the tool, not the board. So that is a FAIL,
    not a warning. Board age is a WARN because a fifteen-minute-old board is
    usually fine and always worth knowing.
    """
    import board
    n = now or board._utcnow()
    started = [l for l in legs if l.get('t') and l['t'] <= n]
    unk = [l for l in legs if l.get('fam') == 'HAND' and not l.get('t')]
    age, gen = board_age_min(n)
    if started:
        return ('FAIL', f"{len(started)} leg(s) already under way -- pregame price is "
                f"gone, price these with live.py: "
                + ', '.join(f"{l['lab']} (started {l['t']})" for l in started[:4]))
    if unk:
        return ('WARN', f"{len(unk)} app-quoted leg(s) with NO kickoff token -- "
                "add '@ 7:30pm' to the hand.py line, or a started game can "
                "slip through as pregame: "
                + ', '.join(l['lab'] for l in unk[:3]))
    if age is None:
        return 'WARN', "feed carries no generated-at header, so its age is unknown"
    if age > 90:
        return 'WARN', f"board is {age:.0f} min old (generated {gen}Z) -- re-pull before betting"
    return 'PASS', f"board {age:.0f} min old, no leg has started"


def gate_derived(legs):
    """A derived price is our arithmetic, not the book's, and must be confirmed.

    The DC payout is synthesized from the h2h de-vig because the feed carries no
    DC market. On 8/13 Ryan sent two real DC quotes -- the first ever checked
    against -- and both derived prices were 8% generous (-835 vs -900, -479 vs
    -500) and both probabilities ~2 points high. The haircut is recalibrated,
    but a synthesized number is still an estimate wearing a price's clothes, and
    every one of them has to be read off the app before it goes on a slip.
    """
    d = [l for l in legs if '(derived)' in l['lab']]
    if not d:
        return 'PASS', "no derived prices on this slip"
    return ('WARN', f"{len(d)} DERIVED price(s) -- confirm each on the app before "
            f"betting, the number here is our arithmetic: "
            + ', '.join(f"{l['lab']} {l['price']}" for l in d))


def _parks():
    """{game key: (venue, blowup multiplier or None)} from MLBTool + f5hist."""
    import json
    out = {}
    try:
        with open(os.path.join(HERE, 'f5hist.json')) as fh:
            v = json.load(fh).get('venue', {})
    except Exception:
        return out
    import board
    for g in (board._SL.get('games') or []):
        a, h = board.TEAM3.get(g['away']), board.TEAM3.get(g['home'])
        if not (a and h):
            continue
        ven = g.get('venue', '')
        hit = next((k for k in v if k.lower() in ven.lower()
                    or ven.lower() in k.lower()), None)
        out[f"{a}@{h}"] = (ven, v[hit]['mult'] if hit else None)
    return out


def gate_park(legs, hi=1.30):
    """An F5 under is worth what the PARK says, and the board never mentions it.

    Three seasons and 6681 games (f5hist.py): P(F5 total >= 11) runs 14.16% at
    Coors and 2.13% at Rate Field against a 6.21% base -- a 6.6x spread, venue
    dispersion p<0.001. One season could not see it (p=0.126) and the team-level
    version is much weaker (p=0.025), so this is the park, not the clubs.

    A park with NO history is the sharper flag. On 8/13 PHI@MIN was at Field of
    Dreams, a neutral site with no rows in three seasons, and MLBTool's slate
    said 'park neutral [unknown park]' and 'no wx'. Two models abstaining at
    once on a deep under is worth saying out loud rather than defaulting to
    league average, which is what silence does.

    WARN, not FAIL: a hot park is a reason to take a shallower rung or skip the
    game, and that is Ryan's call, not the gate's.
    """
    parks = _parks()
    if not parks:
        return 'WARN', "f5hist.json or the slate is unreadable -- no park context"
    hot, blind, ok = [], [], 0
    for l in legs:
        if l.get('fam') not in ('F5', 'FG'):
            continue
        ven, mult = parks.get(l.get('grp'), (None, None))
        if ven is None:
            continue
        if mult is None:
            blind.append(f"{l['lab']} at {ven} (NO park history)")
        elif mult >= hi:
            hot.append(f"{l['lab']} at {ven} ({mult:.2f}x league blowup rate)")
        else:
            ok += 1
    if not (hot or blind):
        return 'PASS', (f"{ok} totals leg(s), every park at or below "
                        f"{hi:.2f}x blowup" if ok else "no totals legs")
    parts = []
    if hot:
        parts.append("elevated-blowup park: " + '; '.join(hot))
    if blind:
        parts.append("UNKNOWN park: " + '; '.join(blind))
    return 'WARN', ' | '.join(parts)


def _grp_teams(raw=None):
    """{soccer group: [team names]} straight from the feed, so a leg's group
    can be turned back into the two clubs the form table knows."""
    if raw is None:
        try:
            import other
            raw = other.OTHER_RAW
        except Exception:
            return {}
    out = {}
    for line in raw.strip().split('\n'):
        p = line.split('|')
        if len(p) == 6 and p[0] == 'SOC' and p[2] != 'Draw':
            out.setdefault(p[1], [])
            if p[2] not in out[p[1]]:
                out[p[1]].append(p[2])
    return out


def gate_soccer_base(legs, form=None, teams_of=None):
    """Check every soccer leg against ITS OWN league, and say when there is none.

    40347 matches (sochist.py): the draw rate -- the entire content of a Double
    Chance -- runs 27.2% in the Championship and 23.1% in the Eredivisie,
    dispersion p=0.0011, and mean goals runs 2.57 to 3.10. A pooled prior hides
    all of that, and until today the board did not even record which league a
    match was in.

    The absences are the sharper half. Leagues Cup, MLS and every UEFA
    qualifying round have no rows at all -- and those are the competitions the
    money was actually on. This says so out loud instead of borrowing a number,
    because borrowing quietly is how a Championship leg gets priced off
    Eredivisie history and nobody ever finds out.
    """
    try:
        import socbase
    except Exception:
        return 'WARN', "socbase unavailable -- no per-league soccer priors"
    if form is None:
        try:
            import json as _j
            with open(os.path.join(HERE, 'socform.json')) as _fh:
                form = _j.load(_fh)
        except Exception:
            form = {}
    if teams_of is None:
        teams_of = _grp_teams()
    seen, blind, proxied = [], [], []
    cold, forms = [], []
    for l in legs:
        # HAND legs are soccer by construction (hand.py parses nothing else)
        # and skipping them here is how 8/13's screenshot slip took six
        # soccer pairs through preflight with no league and no form check.
        if l.get('fam') not in ('SOC', 'SOCT', 'HAND'):
            continue
        key = l.get('lg')
        if not key:
            blind.append(f"{l['lab']} (no competition recorded)")
        else:
            name, r, note = socbase.rates(key)
            if r is None:
                blind.append(f"{l['lab']} ({note})")
            elif note:
                proxied.append(f"{l['lab']} -> {name} ({note})")
            else:
                seen.append(f"{name} draw {r['result']['draw']*100:.1f}% "
                            f"goals {r['result']['mean_goals']:.2f}")
        # TEAM FORM ON THE TICKET. socform's report was a side channel; the
        # Sparta-Rotterdam shape (0.17 ppg, still priced like last month's
        # team) belongs on the slip itself. Unmatched stays 'unknown' --
        # never bad form, never good.
        tms = list((teams_of or {}).get(l.get('grp'), []))
        if not tms and l.get('mkt'):
            # a hand leg's match never touched the feed, but the paste names
            # both teams itself: 'Besiktas|Hradec Kralove', 'Hearts v Benfica'
            import re as _re
            tms = [t.strip() for t in _re.split(r'\||\s+v\s+', str(l['mkt']))
                   if t.strip()]
        for tm in tms:
            fr = (form.get('teams') or {}).get(tm)
            if not fr:
                # the board-joined view only knows feed teams; the full
                # accumulated table ('all', socform.find) knows the rest
                try:
                    import socform as _sf
                    fr, _how = _sf.find(form.get('all') or {}, tm)
                except Exception:
                    fr = None
            if not fr:
                forms.append(f"{tm}: form unknown")
            else:
                forms.append(f"{tm} {fr['form']} {fr['ppg']}ppg")
                if fr['ppg'] <= 0.6:
                    cold.append(f"{tm} is COLD: {fr['form']} "
                                f"({fr['ppg']} ppg, last {fr['newest']})")
    if not (seen or blind or proxied):
        return 'PASS', "no soccer legs"
    parts = []
    if cold:
        parts.append('; '.join(sorted(set(cold))))
    if blind:
        parts.append(f"{len(blind)} leg(s) with NO league history: " + '; '.join(blind))
    if proxied:
        parts.append(f"{len(proxied)} on a PROXY: " + '; '.join(proxied))
    if seen:
        parts.append("measured: " + '; '.join(sorted(set(seen))))
    if forms:
        parts.append("form: " + '; '.join(sorted(set(forms))))
    return ('WARN' if (blind or proxied or cold) else 'PASS', ' | '.join(parts))


def gate_form(legs, data=None, today=None):
    """Recent starter form on every MLB totals leg -- the measured gopher check.

    'aaron nola is a gopher baller' and 'looks like gopher ballers in lad mil'
    were both vetoes the toolchain could neither confirm nor refute; CIN@CWS
    blew up behind two starters nobody's numbers had looked at. mlbform.py now
    measures it: each probable's last five starts as HR/9, each club's last
    ten games of F5 runs. This gate reads the file and names what it finds.

    WARN only. Five starts is a reason to look harder, never a measurement of
    tonight -- and a missing probable is itself the flag (an opener or a
    bullpen day is exactly when an F5 under means something different).
    """
    import json
    from datetime import date
    if data is None:
        try:
            with open(os.path.join(HERE, 'mlbform.json')) as fh:
                data = json.load(fh)
        except Exception:
            return 'WARN', "mlbform.json unreadable -- starter form UNKNOWN (run mlbform)"
    tod = today or date.today().isoformat()
    if data.get('date') != tod:
        return 'WARN', (f"form data is for {data.get('date')}, today is {tod} "
                        "-- touch experiments/MLBFORM.txt to refresh")
    hi = data.get('hr9_warn', 1.8)
    gopher, blind, ok = [], [], 0
    for l in legs:
        if l.get('fam') not in ('F5', 'FG'):
            continue
        g = (data.get('games') or {}).get(l.get('grp'))
        if not g:
            blind.append(f"{l['lab']} (no form row)")
            continue
        worst = None
        for side in ('away_sp', 'home_sp'):
            sp = g.get(side) or {}
            if sp.get('name') is None:
                blind.append(f"{l['lab']} ({side.split('_')[0]} probable NOT LISTED)")
            h = sp.get('hr9_5')
            if h is not None and (worst is None or h > worst[0]):
                worst = (h, sp.get('name'))
        if worst and worst[0] >= hi:
            gopher.append(f"{l['lab']}: {worst[1]} HR/9 {worst[0]:.2f} last 5 starts")
        else:
            ok += 1
    if not (gopher or blind):
        return 'PASS', (f"{ok} MLB totals leg(s), no starter above HR/9 {hi}"
                        if ok else "no MLB totals legs")
    parts = []
    if gopher:
        parts.append("GOPHER form: " + '; '.join(gopher))
    if blind:
        parts.append('; '.join(blind))
    return 'WARN', ' | '.join(parts)


def gate_overlap(legs, open_slips):
    """open_slips: [(name, [labels], p)] already placed.

    EVENT level, not label level (rule 28's own words). Label equality
    missed Makhachev ML on a new ticket against Makhachev-by-Points on an
    open slip -- one Garry upset kills both, and the gate said "no legs
    shared". Fight legs match by fighter tokens (_fight_key); everything
    else still matches by label."""
    if not open_slips:
        return 'PASS', "no other open slips"
    out = []
    for name, labs, _ in open_slips:
        hits = []
        for l in legs:
            for ol in labs:
                if l['lab'] == ol or (_fight_key(l['lab']) and
                                      _fight_key(l['lab']) & _fight_key(ol)):
                    hits.append(f"{l['lab']} ~ {ol}")
        if hits:
            out.append(f"{name}: {len(hits)} shared EVENT(s) "
                       f"({'; '.join(sorted(set(hits)))}) -- one result can "
                       f"kill both slips")
    return ('WARN' if out else 'PASS',
            "; ".join(out) if out else "no events shared with open slips")

def top_rungs(m):
    """{(game, family): deepest rung's label} over EVERY leg on the board.

    board.py files a game's full-game totals, its F5 totals AND its moneyline
    into ONE market key -- ('GT', g) -- because they are one process measured
    several ways. This used to read v[0] and take min() across that whole mixed
    list, which got both halves wrong: only the first family present (always FG)
    ever got an entry, so EVERY F5 leg on a hot game came back is_top_rung=False
    and the gate FAILed the correct top rung; and the label stored under that FG
    key was the min over F5+FG+ML together, so it was usually an F5 leg filed
    under FG. On 8/12 it blocked a clean ticket over COL@ARI F5 U11.5 and
    CHC@WSH F5 U11.5, both of which ARE their game's deepest F5 rung.

    It survived because the selftest only ever called gate_hot() with hand-built
    legs and an is_top_rung the test set itself -- the gate was covered, the
    thing that FEEDS the gate was not. Hence this function exists separately.
    """
    top = {}
    for v in m.values():
        for o in v:
            if o.get('fam') not in ('F5', 'FG'):
                continue
            k = (o.get('grp'), o['fam'])
            cur = top.get(k)
            if cur is None or o['price'] < cur['price']:
                top[k] = o
    return {k: o['lab'] for k, o in top.items()}

MLB_ABBR = {'Arizona Diamondbacks': 'ARI', 'Atlanta Braves': 'ATL',
            'Baltimore Orioles': 'BAL', 'Boston Red Sox': 'BOS',
            'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS',
            'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE',
            'Colorado Rockies': 'COL', 'Detroit Tigers': 'DET',
            'Houston Astros': 'HOU', 'Kansas City Royals': 'KC',
            'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD',
            'Miami Marlins': 'MIA', 'Milwaukee Brewers': 'MIL',
            'Minnesota Twins': 'MIN', 'New York Mets': 'NYM',
            'New York Yankees': 'NYY', 'Oakland Athletics': 'ATH',
            'Athletics': 'ATH', 'Philadelphia Phillies': 'PHI',
            'Pittsburgh Pirates': 'PIT', 'San Diego Padres': 'SD',
            'San Francisco Giants': 'SF', 'Seattle Mariners': 'SEA',
            'St. Louis Cardinals': 'STL', 'Tampa Bay Rays': 'TB',
            'Texas Rangers': 'TEX', 'Toronto Blue Jays': 'TOR',
            'Washington Nationals': 'WSH'}


def gate_shape(legs, pool=None, floor=-350, slack=1.34):
    """FEWER LEGS AT FIXED PRICE, enforced instead of remembered.

    The 8/13 slip was sixteen legs at +116. The board that morning could
    reach +116 with far fewer floor-legal legs, and every leg past that
    bound was pure added risk bought for zero extra payout -- one of the
    sixteen broke, as one of sixteen usually does. This gate computes the
    heaviest-first bound: sort the pool's floor-eligible legs by decimal
    descending, one per event, multiply until the ticket's price is
    reached. A ticket carrying 34%+ more legs than the bound is WARNED
    with both numbers. The bound is optimistic on purpose (it ignores
    correlation and taste); a ticket that fails an optimistic bound has
    no excuse."""
    if not pool:
        return 'PASS', 'no pool provided -- shape unchecked'
    try:
        want = 1.0
        for l in legs:
            want *= l['d'] if l.get('d') else (
                1 + (l['price'] / 100 if l['price'] > 0 else 100 / -l['price']))
    except (KeyError, TypeError):
        return 'PASS', 'a leg has no price -- shape unchecked'
    elig, seen = [], set()
    for o in sorted(pool, key=lambda x: -(x.get('d') or 0)):
        if not o.get('d') or o.get('price', 0) > floor:
            continue
        g = o.get('grp') or o.get('mkt') or o.get('lab')
        if g in seen:
            continue
        seen.add(g)
        elig.append(o['d'])
    got, n_min = 1.0, 0
    for d in elig:
        if got >= want:
            break
        got *= d
        n_min += 1
    if got < want:
        return 'PASS', (f"the board cannot reach {want:.2f}x inside the floor "
                        f"at all -- this shape is as tight as available")
    if len(legs) > n_min * slack:
        return 'WARN', (f"{len(legs)} legs for {want:.2f}x, but the heaviest-"
                        f"first bound reaches it with {n_min} -- every leg "
                        f"past the bound is added risk for zero added payout "
                        f"(the 8/13 sixteen-legger)")
    return 'PASS', f"{len(legs)} legs vs heaviest-first bound {n_min}"


FIGHT_STOP = {'Under', 'Over', 'Method', 'Victory', 'Double', 'Chance',
              'Submission', 'Decision', 'Points', 'Round', 'Rounds', 'Fight',
              'Goes', 'Distance', 'Inside', 'Wins'}


def _fight_key(lab):
    """Event identity for a FIGHT leg, from the label's proper-noun tokens.
    The feed groups a whole card under one grp ('MMA 08-15'), so grp is a
    CARD key there, not a bout key -- the first live run of SGPPAIR flagged
    Orolbai+Makhachev as a same-game pair on that grp, and OVERLAP missed
    Makhachev ML vs Makhachev-by-Points across slips for the same reason.
    Capitalized 4+ letter tokens minus market words name the fighters; a
    label with none (CIN@CWS F5 Under 9.5) returns empty and callers fall
    back to grp/label matching."""
    import re as _re
    return frozenset(t for t in _re.findall(r'[A-Z][a-z]{3,}', str(lab))
                     if t not in FIGHT_STOP)


def _same_event(a, b):
    """Two legs on one real-world event: same grp when the grp is a real
    match key, or intersecting fighter tokens when both labels carry them."""
    ka, kb = _fight_key(a.get('lab', a) if isinstance(a, dict) else a),              _fight_key(b.get('lab', b) if isinstance(b, dict) else b)
    if ka and kb:
        return bool(ka & kb)
    ga = a.get('grp') if isinstance(a, dict) else None
    gb = b.get('grp') if isinstance(b, dict) else None
    if ga and gb:
        return ga == gb
    la = a.get('lab') if isinstance(a, dict) else a
    lb = b.get('lab') if isinstance(b, dict) else b
    return la == lb


def gate_sgppair(legs):
    """Same-game pairs are priced by the BOOK, not by multiplication.

    A slip's probability multiplies legs as if independent. Same-game
    pairs are not, and the one SGP quote measured so far (8/13, DC + that
    match's under) paid 4% ABOVE the naive product -- the book repricing
    correlation, in the bettor's favour that day, direction unguaranteed.
    This gate names every same-game pair so the app's own quote gets
    fetched and logged (sgplog.py); the naive number is never the slip's
    real price when this gate speaks."""
    # Pairwise event identity, because no single key survives all three
    # shapes: soccer legs share a real match grp, fight legs share only a
    # CARD-level grp and must match by fighter tokens, and a totals leg with
    # no name tokens must still pair with its match's DC by grp.
    pairs = {}
    used = set()
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            if _same_event(legs[i], legs[j]):
                key = (_fight_key(legs[i]['lab']) and
                       min(_fight_key(legs[i]['lab']))) or                     legs[i].get('grp') or legs[i]['lab']
                pairs.setdefault(key, [])
                for k in (i, j):
                    if k not in used:
                        pairs[key].append(legs[k]['lab'])
                        used.add(k)
    if not pairs:
        return 'PASS', 'no same-game pairs'
    named = '; '.join(f"{g}: {' + '.join(ls)}" for g, ls in sorted(pairs.items()))
    return 'WARN', (f"{len(pairs)} same-game pair(s) priced naive-independent "
                    f"-- {named} | get the app's SGP quote and sgplog it "
                    f"(measured once: book paid +4% above naive; n=1 is not "
                    f"a constant)")


def gate_dh(legs, slate=None):
    """Doubleheader days: the feed carries ONE game key per matchup per
    day (coverage.json's own confession), so a total on a twin bill can
    silently be the other game's line. The slate (statsapi) lists both
    games; when a matchup appears twice, any leg on it is WARNED to
    confirm which start time the price belongs to."""
    if slate is None:
        try:
            import json as _j
            p = os.environ.get('MLBTOOL') or os.path.join(HERE, '..', 'MLBTool')
            slate = _j.load(open(os.path.join(p, 'mlb', 'data', 'slate.json')))
        except Exception:
            return 'PASS', 'slate unreadable -- doubleheaders unchecked today'
    from collections import Counter
    c = Counter((g['away'], g['home']) for g in slate.get('games', []))
    dh = {f"{MLB_ABBR.get(a, a)}@{MLB_ABBR.get(h, h)}"
          for (a, h), n in c.items() if n > 1}
    if not dh:
        return 'PASS', 'no doubleheaders on the slate'
    hits = [l['lab'] for l in legs
            if any(d in str(l.get('grp', '')) for d in dh)]
    if not hits:
        return 'PASS', f"doubleheader(s) today ({', '.join(sorted(dh))}), no leg on them"
    return 'WARN', (f"leg(s) on a DOUBLEHEADER matchup: {'; '.join(hits)} -- "
                    f"the feed keys ONE game per day; confirm the line is "
                    f"this start time's game, not the nightcap")


def gate_live(legs, pool=None, now=None):
    """Is every leg STILL on the board, at the price we priced it from?

    8/14, live money: Ernesto Mercado was on the FanDuel board at -3000 and
    sat on the Saturday ticket at 95.6%. Between the 14:27 and 18:07 pulls
    FanDuel took the whole bout down -- Tagoe-Mercado, both sides, gone.
    Nothing noticed. The ticket kept printing a 95.6% leg for a market that
    no longer existed, and it only surfaced because Ryan went looking for
    Mercado on another book. Every other gate here reads the leg as WRITTEN;
    none of them re-read the BOARD.

    Group-level absence is the unambiguous signal and the one this gate
    fails on. A selection missing while its group survives is ordinary --
    the feed carries moneylines, not the method props and app-quoted SGPs
    that legitimately sit on a ticket -- so those are named as unverifiable
    rather than failed. A whole group gone is a market that is gone.

    Price movement is the quieter half. Our p came from the OLD price; a
    leg that moved is a leg whose probability is stale even though its name
    still matches. Any move is named. A move that breaks rule 2 or rule 3
    fails, because the ticket now carries a leg the rules forbid.

    Started legs are excluded from the vanish check and named: STALE
    already fails those, and a live game leaving the board is not the
    failure this gate is about.

    THE FALSE POSITIVE, found on this gate's own first live run and fixed
    before it shipped: Ryan's U5.5 Alverca-Estrela is quoted off his app at
    a rung the feed does not carry, and it is filed under a group named for
    itself, so a naive group lookup called a perfectly live leg vanished.
    An app-quoted leg is therefore checked at FIXTURE level instead -- the
    board still lists Alverca-Estrela, so the leg is confirmed alive with
    the rung named as unfetchable. Only a fixture the board has lost is
    escalated, and to WARN, because feed coverage is a floor and not the
    schedule (board.py says so in three families)."""
    if not pool:
        return 'PASS', 'no pool provided -- board presence unchecked'
    import board
    n = now or board._utcnow()
    by_lab, groups = {}, set()
    for o in pool:
        by_lab.setdefault(o['lab'], []).append(o)
        if o.get('grp'):
            groups.add(o['grp'])

    gone, moved, breaks, unver, started = [], [], [], [], []
    appok, nofix = [], []
    for l in legs:
        lab, grp = l['lab'], l.get('grp')
        if l.get('t') and l['t'] <= n:
            started.append(lab); continue
        here = by_lab.get(lab)
        if here:
            # Same label can sit on two fixtures (19 such labels on the 8/13
            # board). Grade the one we BET -- matched on start time -- and
            # only fall back to the first when the leg carries no time.
            o = next((c for c in here if c.get('t') == l.get('t')), here[0])
            if o['price'] != l['price']:
                moved.append((lab, l['price'], o['price']))
                if o['price'] > -350 or o['price'] > 0:
                    breaks.append((lab, o['price']))
            continue
        if _app_quoted(l):
            fx = _fixture_live(l, pool)
            (appok if fx else nofix).append((lab, fx))
        elif grp and grp not in groups:
            gone.append((lab, grp))
        else:
            unver.append(lab)

    if gone:
        return ('FAIL', f"{len(gone)} leg(s) NO LONGER ON THE BOARD -- the whole "
                f"market is gone, not just the price: "
                + '; '.join(f"{lab} ({grp})" for lab, grp in gone)
                + " | re-pull, and if it is still absent the leg cannot be bet here")
    if breaks:
        return ('FAIL', f"{len(breaks)} leg(s) moved through the rules: "
                + '; '.join(f"{lab} now {pr:+d}" for lab, pr in breaks)
                + " | rule 2/3 fail at the CURRENT price, not the quoted one")
    bits = []
    if moved:
        bits.append(f"{len(moved)} leg(s) MOVED since quoting ("
                    + '; '.join(f"{lab} {a:+d} -> {b:+d}" for lab, a, b in moved)
                    + ") -- p is stale, reprice before betting")
    if nofix:
        bits.append(f"{len(nofix)} app-quoted leg(s) whose FIXTURE is not on the "
                    f"board at all: {', '.join(lab for lab, _ in nofix)} -- "
                    f"confirm the match is still on before betting")
    if appok:
        bits.append(f"{len(appok)} app-quoted leg(s) confirmed at fixture level "
                    f"(rung deeper than the feed carries): "
                    + '; '.join(f"{lab} -> {fx}" for lab, fx in appok))
    if unver:
        bits.append(f"{len(unver)} leg(s) the feed cannot confirm "
                    f"(method props): {', '.join(unver)}")
    if started:
        bits.append(f"{len(started)} started leg(s) skipped -- STALE owns those")
    if moved or nofix:
        return 'WARN', ' | '.join(bits)
    if bits:
        return 'PASS', ' | '.join(bits)
    return 'PASS', f"all {len(legs)} legs still on the board at the quoted price"


_FIXNOISE = {'under', 'over', 'goals', 'draw', 'derived', 'quote', 'both',
             'score', 'team', 'total', 'points', 'chance', 'double'}

def _app_quoted(l):
    """A leg whose PRICE came from Ryan's app, not from the feed. Three
    honest markers, no guessing: hand.py stamps fam='HAND'; a leg built
    from a quote is filed under a group named for itself, which no board
    leg ever is; and the SGP labels say so in words."""
    return (l.get('fam') == 'HAND' or l.get('src') == 'app'
            or not l.get('grp') or l.get('grp') == l['lab']
            or 'app quote' in l['lab'].lower() or l['lab'].lower().startswith('sgp:'))

def _fixtoks(s):
    import re
    return {w for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", str(s).lower())
            if w not in _FIXNOISE}

def _fixture_live(l, pool):
    """Is the app-quoted leg's MATCH still on the board, even though its
    rung is not? Returns the board group that carries it, or None."""
    want = _fixtoks(l.get('match') or l['lab'])
    if not want:
        return None
    for o in pool:
        have = _fixtoks(o.get('match') or '') | _fixtoks(o.get('grp') or '')
        hit = want & have
        if len(hit) >= 2 or any(len(w) >= 5 for w in hit):
            return o.get('grp') or o['lab']
    return None


def run(legs, hot=None, open_slips=None, pool=None):
    hot = hot or {}
    gates = [("FLOOR", gate_floor(legs)), ("PLUS", gate_plus(legs)),
             ("SOCCER", gate_soccer(legs)), ("METHOD", gate_method(legs)),
             ("HOT", gate_hot(legs, hot)), ("TIE", gate_tie(legs)),
             ("STALE", gate_stale(legs)), ("DERIVED", gate_derived(legs)),
             ("PARK", gate_park(legs)),
             ("SOCBASE", gate_soccer_base(legs)),
             ("FORM", gate_form(legs)),
             ("OVERLAP", gate_overlap(legs, open_slips or [])),
             ("SHAPE", gate_shape(legs, pool)),
             ("SGPPAIR", gate_sgppair(legs)),
             ("DH", gate_dh(legs)),
             ("LIVE", gate_live(legs, pool))]
    return gates, any(v == 'FAIL' for _, (v, _) in gates)

def main():
    import board
    from board import build
    want = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not want:
        print(__doc__.strip().splitlines()[2])
        return 2
    # NO CUTOFF HERE, deliberately. build()'s cutoff drops games that have
    # already started, so asking preflight about a live leg used to come back
    # "not on the board (check spelling)" -- which reads as a typo and sent me
    # looking for one on 8/13 while the real answer was that the game was in
    # the third inning. A started leg is a thing the STALE gate must SEE in
    # order to fail it, so the pool is built wide and the gate does the judging.
    m = build('FanDuel', min_price=0)
    # A LABEL IS NOT A LEG. A team that plays twice in the horizon produces two
    # legs with the SAME label and different groups, prices and start times --
    # 19 such labels on the 8/13 board. This was `{o['lab']: o}`, last one wins,
    # so checking tonight's "New York City FC DC (derived)" silently graded
    # SUNDAY's match at -262 instead of tonight's at -493, and FAILed the floor
    # on a game that was never on the ticket. A gate that validates a different
    # fixture than the one being bet is worse than no gate.
    #
    # Earliest future start wins, because that is what "today's ticket" means,
    # and every collision is named so the choice is visible rather than assumed.
    idx, amb = {}, {}
    for v in m.values():
        for o in v:
            cur = idx.get(o['lab'])
            if cur is None:
                idx[o['lab']] = o
            else:
                amb.setdefault(o['lab'], [cur]).append(o)
                if o['t'] < cur['t']:
                    idx[o['lab']] = o
    for _h in hand_legs():
        if _h['lab'] not in idx:
            idx[_h['lab']] = _h
    tops = top_rungs(m)
    legs, missing = [], []
    for w in want:
        o = idx.get(w)
        if not o:
            missing.append(w); continue
        o = dict(o)
        o['is_top_rung'] = tops.get((o.get('grp'), o.get('fam'))) == o['lab']
        legs.append(o)
    if missing:
        print(f"  not on the board (check spelling): {missing}")
    hit = [w for w in want if w in amb]
    if hit:
        from times import ct
        print(f"  AMBIGUOUS label(s) — took the earliest start:")
        for w in hit:
            print(f"    {w}")
            for o in sorted(amb[w], key=lambda o: o['t']):
                mark = "  <- used" if o['t'] == idx[w]['t'] else ""
                print(f"      {ct(o['t']):17} {o['grp']:20} {o['price']:+6d}{mark}")
    pool = [o for v in m.values() for o in v]
    gates, failed = run(legs, board.hot_games('FanDuel'), pool=pool)
    print()
    for name, (v, msg) in gates:
        print(f"  [{v:4}] {name:8} {msg}")
    print(f"\n  {'BLOCKED' if failed else 'CLEAR'} -- {len(legs)} legs checked")
    print("  still yours: log to slips.json (31) and calibration.csv (29)")
    return 1 if failed else 0

def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    L = lambda lab, pr, **kw: dict(lab=lab, price=pr, **kw)

    chk(gate_floor([L('a', -400), L('b', -351)])[0] == 'PASS', "-351 clears the floor")
    chk(gate_floor([L('a', -400), L('b', -340)])[0] == 'FAIL',
        "-340 fails it -- 'it's only one leg' is rule 2's exact wording")
    chk(gate_plus([L('a', 134)])[0] == 'FAIL', "a +134 dog is blocked (rule 3)")

    chk(gate_soccer([L('PSV Eindhoven', -600, fam='SOC')])[0] == 'FAIL',
        "the leg shape that killed Slip A on the PSV draw is blocked by name")
    chk(gate_soccer([L('PSV DC (derived)', -300, fam='SOC')])[0] == 'PASS',
        "a derived Double Chance passes")

    chk(gate_method([L('Escarrega by KO/TKO', -400)])[0] == 'WARN',
        "yesterday's losing leg raises the rule-27 warning")
    chk(gate_method([L('Kunneman by Submission or on Points', 170)])[0] == 'PASS',
        "a double chance does not")
    chk(gate_method([L('Anthony Wint', -1400)])[0] == 'PASS', "a plain ML is fine")
    # ---- THE APP'S OWN WORDING, copied from the 8/12 UFC 330 bet slip.
    # This exact slip returned "all double-chance" while carrying two single
    # method legs, because the word list had 'on points' but not 'by points'.
    chk(gate_method([L('Islam Makhachev by Points', 135)])[0] == 'WARN',
        "FanDuel writes it 'by Points', and that is a single method leg")
    chk(gate_method([L('Ian Machado Garry by Points', 400)])[0] == 'WARN',
        "so is the other side of the same market")
    v, msg = gate_method([L('Kaue Fernandes by KO/TKO or on Points', 185),
                          L('Joel Alvarez by KO/TKO or Submission', -140),
                          L('Mansur Abdul Malik', -650),
                          L('Islam Makhachev by Points', 135)])
    chk(v == 'WARN' and 'by Points' in msg and 'Kaue' not in msg,
        f"and on the real slip it names ONLY the single-method leg, not the "
        f"two double chances sitting beside it ({msg})")

    hot = {'CHC@WSH': 'adj 10.82'}
    mid = [L('CHC@WSH F5 Under 9.5', -1200, fam='F5', grp='CHC@WSH', is_top_rung=False)]
    top = [L('CHC@WSH F5 Under 11.5', -4000, fam='F5', grp='CHC@WSH', is_top_rung=True)]
    chk(gate_hot(mid, hot)[0] == 'FAIL',
        "TUESDAY'S ACTUAL KILLER -- a mid rung on the hottest game -- is blocked")
    chk(gate_hot(top, hot)[0] == 'PASS', "the top rung on the same game passes")
    chk(gate_hot(mid, {})[0] == 'WARN',
        "no hot data is a WARN, never a silent PASS (the 4-day-stale slate)")

    slips = [("20-leg", ["Hasan by KO", "Wint ML"], 0.126)]
    v, msg = gate_overlap([L('Hasan by KO', -500), L('X', -400)], slips)
    chk(v == 'WARN' and 'Hasan by KO' in msg,
        "the 8/11 double-kill leg is named before the second slip goes in")
    chk(gate_overlap([L('X', -400)], slips)[0] == 'PASS', "disjoint slips pass")

    # ---- what FEEDS gate_hot. Every check above hands gate_hot an is_top_rung
    # the test set itself, so the lookup that computes it went uncovered and was
    # wrong from the day it shipped. This is board.py's real shape: one market
    # key per GAME carrying full-game totals, F5 totals and the moneyline.
    mixed = {('GT', 'COL@ARI'): [
        L('COL@ARI Under 14.5', -900, fam='FG', grp='COL@ARI'),
        L('COL@ARI Under 15.5', -1400, fam='FG', grp='COL@ARI'),
        L('COL@ARI F5 Under 10.5', -1600, fam='F5', grp='COL@ARI'),
        L('COL@ARI F5 Under 11.5', -3500, fam='F5', grp='COL@ARI'),
        L('Arizona Diamondbacks ML', -150, fam='ML', grp='COL@ARI')]}
    t = top_rungs(mixed)
    chk(t[('COL@ARI', 'F5')] == 'COL@ARI F5 Under 11.5',
        "the deepest F5 rung is found even though FG legs sit first in the list")
    chk(t[('COL@ARI', 'FG')] == 'COL@ARI Under 15.5',
        "and the FG top is the deepest FG rung -- NOT the -3500 F5 leg that "
        "min() over the mixed list used to file under FG")
    chk(('COL@ARI', 'ML') not in t, "moneylines are not a totals ladder")

    gates, failed = run(mid + [L('y', 120)], hot)
    chk(failed, "any FAIL blocks the whole preflight")
    gates, failed = run(top, hot)
    chk(not failed, "a clean ticket clears")

    # ---- TIE. Rule 40: a second leg whose first leg is not written down is a
    # blind bet, and the way it hides is by looking like an ordinary favourite.
    v, m_ = gate_tie([L('Hammarby DC (derived)', -647, fam='SOC',
                        grp='SOC Rakow-Hammarby')])
    chk(v == 'PASS' and 'level' in m_,
        "a second leg WITH its first leg on file passes, and says the standing")
    v, _ = gate_tie([L('Besiktas to advance', -6000, fam='SOC',
                       grp='SOC Besiktas-Hradec Kralove')])
    chk(v == 'FAIL',
        "a listed tie with first_leg still null FAILS -- silence is the failure "
        "mode this gate exists to remove, so it cannot be a warning")
    v, _ = gate_tie([L('Under 6.5 goals (PU-SL)', -4000, fam='SOCT',
                       grp='SOC PU-SL')])
    chk(v == 'PASS', "a one-off match is not a tie and is not scolded")
    v, _ = gate_tie([L('CHC@WSH F5 Under 10.5', -4500, fam='F5', grp='CHC@WSH')])
    chk(v == 'PASS', "and baseball never touches this gate")

    # ---- STALE. A started leg has no pregame price left, so it cannot pass.
    NOW = '2026-08-13T18:30Z'
    v, m_ = gate_stale([dict(L('CIN@CWS F5 Under 10.5', -4500, fam='F5',
                               grp='CIN@CWS'), t='2026-08-13T17:11Z')], now=NOW)
    chk(v == 'FAIL' and 'live.py' in m_,
        "a leg whose game has started FAILS and is sent to live.py -- 97% at "
        "first pitch was worth half that by the third inning")
    v, _ = gate_stale([dict(L('TEX@LAA F5 Under 10.5', -7000, fam='F5',
                              grp='TEX@LAA'), t='2026-08-14T02:08Z')], now=NOW)
    chk(v in ('PASS', 'WARN'), "a leg that has not started is not blocked by it")

    # ---- DERIVED. Our arithmetic must never be quoted as the book's price.
    v, m_ = gate_derived([L('Philadelphia Union DC (derived)', -887, fam='SOC')])
    chk(v == 'WARN' and '-887' in m_,
        "a derived price is named with its number so it can be confirmed -- "
        "the two real quotes we ever checked were both 8% off")
    v, _ = gate_derived([L('Atlanta Dream', -520, fam='WNBA')])
    chk(v == 'PASS', "a real book price is not flagged as derived")

    # ---- PARK. Measured over 6681 games, not asserted.
    import json as _pj
    _h = _pj.load(open(os.path.join(HERE, 'f5hist.json')))
    _v = _h['venue']
    chk(_h['games'] > 5000,
        f"f5hist covers {_h['games']} games -- one season could not resolve the "
        "venue spread at all (p=0.126), three seasons put it at p<0.001")
    _coors = _v.get('Coors Field', {}).get('mult')
    _rate = _v.get('Rate Field', {}).get('mult')
    chk(_coors and _rate and _coors / _rate > 4,
        f"the park spread is real and large: Coors {_coors}x vs Rate Field "
        f"{_rate}x, a {_coors/_rate:.1f}x ratio on the same bet")
    # ---- SOCBASE. A league is not a pool, and an absence is not a default.
    import socbase as _sb
    _n, _r, _note = _sb.rates('soccer_efl_champ')
    _n2, _r2, _ = _sb.rates('soccer_netherlands_eredivisie')
    chk(_r and _r2 and _r['result']['draw'] - _r2['result']['draw'] > 0.03,
        f"the draw rate really does move by league: Championship "
        f"{_r['result']['draw']*100:.1f}% vs Eredivisie {_r2['result']['draw']*100:.1f}%, "
        "measured over 40347 matches at p=0.0011 -- and a Double Chance is "
        "nothing but the draw plus a side")
    _n3, _r3, _note3 = _sb.rates('soccer_uefa_champs_league_qualification')
    chk(_r3 is None and 'absent' in (_note3 or ''),
        "a competition with no history returns NOTHING and says so, rather than "
        "silently borrowing the pooled number -- Leagues Cup, MLS and every UEFA "
        "qualifier are in exactly this state and are what the money was on")
    _n4, _r4, _note4 = _sb.rates('soccer_concacaf_leagues_cup')
    chk(_r4 is not None and 'PROXY' in (_note4 or ''),
        "and where a proxy is used it is NAMED, because a proxy is a stated "
        "assumption and not a measurement")
    _v, _m = gate_soccer_base([L('Under 2.5 goals (x)', -200, fam='SOCT')])
    chk(_v == 'WARN' and 'NO league history' in _m,
        "a soccer leg with no competition recorded warns rather than passing")

    # ---- form on the ticket. The Sparta shape: 0.17 ppg priced like May.
    _tf = {'SOC A-B': ['Sparta Rotterdam', 'SC Telstar']}
    _ff = {'teams': {'Sparta Rotterdam': {'form': 'LLLDLL', 'ppg': 0.17,
                                          'newest': '2026-08-09'},
                     'SC Telstar': {'form': 'WWWDWL', 'ppg': 2.17,
                                    'newest': '2026-08-08'}}}
    _v, _m = gate_soccer_base([dict(L('SC Telstar DC (derived)', -400, fam='SOC'),
                                    grp='SOC A-B', lg='soccer_netherlands_eredivisie')],
                              form=_ff, teams_of=_tf)
    chk(_v == 'WARN' and 'COLD' in _m and 'Sparta Rotterdam' in _m,
        "a 0.17-ppg opponent is named COLD on the slip itself -- the "
        "form report stops being a side channel")
    chk('SC Telstar WWWDWL' in _m,
        "and both sides' form strings ride along for the read")
    _v2, _m2 = gate_soccer_base([dict(L('X DC (derived)', -400, fam='SOC'),
                                      grp='SOC C-D', lg='soccer_netherlands_eredivisie')],
                                form={'teams': {}}, teams_of={'SOC C-D': ['Unk FC']})
    chk('form unknown' in _m2,
        "an unmatched team reads 'form unknown' -- never bad form, never good")

    # ---- HAND legs reach this gate too, teams drawn from their own paste.
    # 8/13's screenshot slip took six soccer pairs through preflight with no
    # league and no form check because fam HAND skipped the gate entirely.
    _fh = {'teams': {}, 'all': {'kashiwa reysol':
                                {'form': 'LLLDLL', 'ppg': 0.5, 'name': 'Kashiwa Reysol',
                                 'newest': '2026-08-10'}}}
    _v3, _m3 = gate_soccer_base([dict(L('Kashiwa Reysol DC (app-quoted)', -426,
                                        fam='HAND'),
                                      mkt='Kashiwa Reysol|Albirex Niigata')],
                                form=_fh, teams_of={})
    chk(_v3 == 'WARN' and 'no competition recorded' in _m3,
        "a hand leg with no league is BLIND out loud, not silently skipped")
    chk('COLD' in _m3 and 'Kashiwa Reysol' in _m3,
        "its team is found in the persisted FULL table (socform 'all') and a "
        "0.5-ppg side is called COLD -- form the feed never carried")
    chk('Albirex Niigata: form unknown' in _m3,
        "the other side of the paste is looked for too, honestly unknown")

    # ---- FORM. The measured gopher check, injectable so the test owns its data.
    _fd = {'date': '2026-08-13', 'hr9_warn': 1.8, 'games': {
        'MIL@LAD': {'away_sp': {'name': 'Shane Drohan', 'hr9_5': 2.31},
                    'home_sp': {'name': 'Roki Sasaki', 'hr9_5': 0.95}},
        'TEX@LAA': {'away_sp': {'name': 'Jacob deGrom', 'hr9_5': 0.61},
                    'home_sp': {'name': 'W. Urena', 'hr9_5': 1.10}},
        'PIT@MIA': {'away_sp': {'name': None, 'hr9_5': None},
                    'home_sp': {'name': 'T. Phillips', 'hr9_5': 1.2}}}}
    _v, _m = gate_form([L('MIL@LAD F5 Under 10.5', -4000, fam='F5', grp='MIL@LAD')],
                       data=_fd, today='2026-08-13')
    chk(_v == 'WARN' and 'Drohan' in _m and '2.31' in _m,
        "a starter at HR/9 2.31 over five starts is NAMED on the leg -- the "
        "measured version of 'gopher baller', which twice had to be eyeballed")
    _v, _ = gate_form([L('TEX@LAA F5 Under 10.5', -7000, fam='F5', grp='TEX@LAA')],
                      data=_fd, today='2026-08-13')
    chk(_v == 'PASS', "deGrom in form passes without comment")
    _v, _m = gate_form([L('PIT@MIA F5 Under 10.5', -5000, fam='F5', grp='PIT@MIA')],
                       data=_fd, today='2026-08-13')
    chk(_v == 'WARN' and 'NOT LISTED' in _m,
        "a missing probable is itself the flag -- an opener or bullpen day is "
        "when an F5 under means something different")
    _v, _m = gate_form([L('MIL@LAD F5 Under 10.5', -4000, fam='F5', grp='MIL@LAD')],
                       data=_fd, today='2026-08-14')
    chk(_v == 'WARN' and 'form data is for' in _m,
        "yesterday's form is stale, not silently current -- same failure shape "
        "as the MLBTool slate that left rule 25 blind")

    # ---- METHOD carries its denominator now.
    _ur = {'modern_since': 2015,
           'title': {'dec': 0.436, 'ko': 0.378, 'sub': 0.183},
           'non_title': {'dec': 0.498, 'ko': 0.321, 'sub': 0.178}}
    _v, _m = gate_method([L('Islam Makhachev by Points', -137)], rates=_ur)
    chk(_v == 'WARN' and 'title dec 44' in _m,
        "a method prop is warned WITH the modern base rates beside it -- "
        "rules 9 and 27 argue from a denominator now, not from scar tissue")
    _v, _m = gate_method([L('X by Points', -137)], rates={})
    chk('priced blind' in _m,
        "and when the base rates are unreadable the gate says the prop is "
        "priced blind rather than quietly dropping the context")

    # ---- hand legs through the gates: the UEFA-night path.
    import json as _json, tempfile as _tf
    _hf = _tf.NamedTemporaryFile('w', suffix='.json', delete=False)
    _json.dump({'legs': [
        {'lab': 'Besiktas to advance (app-quoted)', 'p': 0.944, 'd': 1.0167,
         'price': -6000, 't': '2026-08-13T17:00Z'},
        {'lab': 'Tromso DC (derived) (app-quoted)', 'p': 0.833, 'd': 1.16,
         'price': -625}]}, _hf)
    _hf.close()
    _hl = hand_legs(_hf.name)
    chk(len(_hl) == 2 and all(l['fam'] == 'HAND' for l in _hl),
        "hand legs load shaped for the gates, tagged HAND")
    _v, _m = gate_stale([_hl[0]], now='2026-08-13T18:00Z')
    chk(_v == 'FAIL',
        "an app-quoted leg with its kickoff PAST fails STALE like any other -- "
        "the gates now cover the half of the slip the feed cannot see")
    _v, _m = gate_stale([_hl[1]], now='2026-08-13T12:00Z')
    chk(_v == 'WARN' and 'kickoff token' in _m,
        "and one with NO token warns by name instead of passing silently -- "
        "unknown start is unknown, not fine")
    _v, _m = gate_tie([_hl[0]])
    chk(_v == 'FAIL' and 'first leg NOT on file' in _m,
        "a hand-entered Besiktas leg still hits rule 40: ties.json has no "
        "first leg recorded, so the TIE gate blocks it -- app-quoted does "
        "not mean gate-exempt")

    chk(_h['rungs'][4]['rung'] == 10.5 and 0.930 < _h['rungs'][4]['p'] < 0.945,
        f"U10.5 sits at {_h['rungs'][4]['p']*100:.2f}% over three seasons, "
        "against 93.78% over one -- the de-vig calibration is not a one-season "
        "artefact")

    # ---- SHAPE: the 8/13 sixteen-legger, as a bound
    _pool = [{'lab': f'g{i}', 'grp': f'G{i}', 'price': -400, 'd': 1.2}
             for i in range(10)]
    _fat = [{'lab': f't{i}', 'grp': f'T{i}', 'price': -2000, 'd': 1.05}
            for i in range(8)]
    _v, _m = gate_shape(_fat, _pool)
    chk(_v == 'WARN' and 'heaviest-first bound' in _m and ' 3 ' in f' {_m} ',
        "eight -2000 legs for 1.48x are WARNED: the board reaches that "
        "price with 3 floor-legal legs -- the 8/13 shape, caught pregame")
    _tight = [{'lab': f'w{i}', 'grp': f'W{i}', 'price': -530, 'd': 1.19}
              for i in range(2)]
    _v, _m = gate_shape(_tight, _pool)
    chk(_v == 'PASS',
        "two 1.19 legs for 1.42x pass -- the bound is also 2; the first "
        "draft of this pin used legs so light that ONE pool leg covered "
        "their whole price, and the gate rightly called even three of "
        "them fat")
    _v, _m = gate_shape(_fat, None)
    chk(_v == 'PASS' and 'unchecked' in _m,
        "no pool -> shape honestly unchecked, never guessed")
    _huge = [{'lab': 'h', 'grp': 'H', 'price': -400, 'd': 9.0}]
    _v, _m = gate_shape(_huge, _pool)
    chk(_v == 'PASS' and 'cannot reach' in _m,
        "a price the floor-legal board cannot reach passes -- the ticket "
        "is as tight as available")

    # ---- SGPPAIR: the book reprices same-game pairs; naming them is the gate
    _sg = [{'lab': 'Union DC', 'grp': 'SOC PU-SL', 'price': -835},
           {'lab': 'U6.5 PU-SL', 'grp': 'SOC PU-SL', 'price': -4000},
           {'lab': 'CIN@CWS F5 U9.5', 'grp': 'CIN@CWS', 'price': -2000}]
    _v, _m = gate_sgppair(_sg)
    chk(_v == 'WARN' and 'Union DC + U6.5 PU-SL' in _m and 'sgplog' in _m,
        "a same-game pair is NAMED and sent to sgplog -- the naive product "
        "is not the slip's real price (book paid +4% above it once, n=1)")
    _v, _m = gate_sgppair(_sg[1:])
    chk(_v == 'PASS', "distinct games carry no pair warning")
    # first live run, 8/14: the UFC feed groups the WHOLE CARD under one grp
    _card = [{'lab': 'Myktybek Orolbai ML', 'grp': 'MMA 08-15', 'price': -1200},
             {'lab': 'Islam Makhachev ML', 'grp': 'MMA 08-15', 'price': -355}]
    _v, _m = gate_sgppair(_card)
    chk(_v == 'PASS',
        "two DIFFERENT bouts sharing the feed's card-level grp are NOT a "
        "same-game pair -- the gate's first live run flagged exactly this")
    _same = [{'lab': 'Islam Makhachev ML', 'grp': 'MMA 08-15', 'price': -355},
             {'lab': 'Islam Makhachev by Points', 'grp': 'MMA 08-15', 'price': 120}]
    _v, _m = gate_sgppair(_same)
    chk(_v == 'WARN' and 'Makhachev' in _m,
        "two legs on the SAME bout still pair, matched by fighter not grp")
    # ...and OVERLAP matches by EVENT across slips (the live false negative)
    _v, _m = gate_overlap([{'lab': 'Islam Makhachev ML', 'price': -355}],
                          [('bonus 4-leg',
                            ['Islam Makhachev by Points (v Garry)'], 0.013)])
    chk(_v == 'WARN' and 'kill both' in _m,
        "Makhachev ML vs Makhachev-by-Points on an open slip is ONE event "
        "-- a Garry upset kills both, and the gate now says so")
    _v, _m = gate_overlap([{'lab': 'CIN@CWS F5 Under 9.5', 'price': -500}],
                          [('bonus', ['Islam Makhachev by Points'], 0.5)])
    chk(_v == 'PASS',
        "a fightless label with no fighter tokens never fuzzy-matches")

    # ---- DH: the feed keys one game per matchup per day
    _slate = {'games': [{'away': 'St. Louis Cardinals', 'home': 'Chicago Cubs'},
                        {'away': 'St. Louis Cardinals', 'home': 'Chicago Cubs'},
                        {'away': 'New York Yankees', 'home': 'Toronto Blue Jays'}]}
    _v, _m = gate_dh([{'lab': 'STL@CHC F5 U9.5', 'grp': 'STL@CHC', 'price': -500}],
                     _slate)
    chk(_v == 'WARN' and 'DOUBLEHEADER' in _m and 'nightcap' in _m,
        "a leg on a twin-bill matchup is WARNED: the feed keys ONE game, "
        "the line may belong to the other start")
    _v, _m = gate_dh([{'lab': 'NYY@TOR F5 U8.5', 'grp': 'NYY@TOR', 'price': -500}],
                     _slate)
    chk(_v == 'PASS' and 'no leg on them' in _m,
        "a doubleheader elsewhere is stated but does not warn this leg")
    _v, _m = gate_dh([{'lab': 'x', 'grp': 'X', 'price': -500}],
                     {'games': [{'away': 'A', 'home': 'B'}]})
    chk(_v == 'PASS' and 'no doubleheaders' in _m,
        "a single-game slate passes clean")

    # ---- LIVE: the 8/14 Mercado case, replayed. The board pool is the
    # POST-pull board (Tagoe-Mercado absent); the ticket is the pre-pull one.
    _now = '2026-08-14T20:00Z'
    _pool = [{'lab': 'Claressa Shields', 'price': -3000, 'grp': 'BOX Shields-Scott',
              't': '2026-08-16T05:00Z'},
             {'lab': 'Troy Isley', 'price': -650, 'grp': 'BOX Hicks-Isley',
              't': '2026-08-16T01:50Z'},
             {'lab': 'Myktybek Orolbai ML', 'price': -1200, 'grp': 'MMA 08-15',
              't': '2026-08-15T21:45Z'}]
    _tik = [{'lab': 'Ernesto Mercado', 'price': -3000, 'grp': 'BOX Tagoe-Mercado',
             't': '2026-08-16T00:00Z'},
            {'lab': 'Claressa Shields', 'price': -3000, 'grp': 'BOX Shields-Scott',
             't': '2026-08-16T05:00Z'}]
    _v, _m = gate_live(_tik, _pool, now=_now)
    chk(_v == 'FAIL' and 'Mercado' in _m and 'BOX Tagoe-Mercado' in _m,
        "the pulled bout FAILS by name -- the exact 8/14 miss, replayed")
    _v, _m = gate_live([_tik[1]], _pool, now=_now)
    chk(_v == 'PASS' and 'still on the board' in _m,
        "a leg still on the board at its quoted price passes clean")

    # A method prop's GROUP survives (the card is there), the selection never
    # existed in the feed. That is unverifiable, not vanished.
    _v, _m = gate_live([{'lab': 'Islam Makhachev by Points', 'price': 120,
                         'grp': 'MMA 08-15', 't': '2026-08-16T03:30Z'}],
                       _pool, now=_now)
    chk(_v == 'PASS' and 'cannot confirm' in _m and 'Makhachev' in _m,
        "a method prop is named unverifiable, NOT failed as vanished")

    # Price movement: p is stale even when the name still matches.
    _v, _m = gate_live([{'lab': 'Troy Isley', 'price': -650,
                         'grp': 'BOX Hicks-Isley', 't': '2026-08-16T01:50Z'}],
                       [dict(_pool[1], price=-900)], now=_now)
    chk(_v == 'WARN' and '-650 -> -900' in _m,
        "a moved price WARNs with both numbers, because p came from the old one")
    _v, _m = gate_live([{'lab': 'Troy Isley', 'price': -650,
                         'grp': 'BOX Hicks-Isley', 't': '2026-08-16T01:50Z'}],
                       [dict(_pool[1], price=-300)], now=_now)
    chk(_v == 'FAIL' and '-300' in _m,
        "a leg that moved THROUGH the -350 floor fails at the current price")
    _v, _m = gate_live([{'lab': 'Troy Isley', 'price': -650,
                         'grp': 'BOX Hicks-Isley', 't': '2026-08-16T01:50Z'}],
                       [dict(_pool[1], price=160)], now=_now)
    chk(_v == 'FAIL' and '+160' in _m, "and one that moved to plus money fails (rule 3)")

    # A started leg is STALE's business, not this gate's -- and must not be
    # reported as vanished when the feed drops a live game.
    _v, _m = gate_live([{'lab': 'Gone Team', 'price': -500, 'grp': 'NOPE',
                         't': '2026-08-14T19:00Z'}], _pool, now=_now)
    chk(_v == 'PASS' and 'started' in _m,
        "a started leg is skipped and named, not failed as off-board")
    chk(gate_live([{'lab': 'x', 'price': -500, 'grp': 'y'}], None)[0] == 'PASS',
        "no pool means unchecked, not a false alarm")

    # ---- THE FALSE POSITIVE THIS GATE FOUND IN ITSELF, 8/14. Ryan's U5.5 is
    # quoted off his app at a rung the feed does not carry, filed under a
    # self-named group. First live run called it vanished. It is not.
    _fx = [{'lab': 'Alverca DC (derived)', 'price': -334,
            'grp': 'SOC Alverca-Estrela', 't': '2026-08-15T14:30Z'}]
    _app = {'lab': 'U5.5 Alverca v CF Estrela', 'price': -8000, 'fam': 'SOCT',
            'grp': 'U5.5 Alverca v CF Estrela', 'match': 'Alverca v CF Estrela',
            't': '2026-08-15T14:30Z'}
    _v, _m = gate_live([_app], _fx, now=_now)
    chk(_v == 'PASS' and 'SOC Alverca-Estrela' in _m and 'fixture level' in _m,
        "an app-quoted rung is CONFIRMED by its fixture, not failed as vanished")
    _v, _m = gate_live([_app], _pool, now=_now)
    chk(_v == 'WARN' and 'FIXTURE is not on the board' in _m,
        "but an app-quoted leg whose match is gone entirely still WARNs")
    chk(_app_quoted(_app) and _app_quoted({'lab': 'SGP: Porto DC + U5.5 (app quote)',
                                           'grp': 'SOC Porto-RA'})
        and not _app_quoted({'lab': 'Troy Isley', 'grp': 'BOX Hicks-Isley'}),
        "self-named group and 'app quote' wording mark a quote; a board leg is not marked")
    chk(_fixture_live({'match': 'FC Porto v Rio Ave FC', 'lab': 'x'},
                      [{'lab': 'y', 'grp': 'SOC Porto-RA'}]) == 'SOC Porto-RA',
        "one distinctive 5+ char club token is enough to confirm a fixture")
    chk(_fixture_live({'lab': 'Under 5.5 goals', 'match': ''}, _fx) is None,
        "a leg with only noise words confirms nothing -- no accidental match")

    # Same label on two fixtures: grade the one we BET, by start time.
    _twin = [{'lab': 'NYCFC DC (derived)', 'price': -493, 'grp': 'A',
              't': '2026-08-15T23:30Z'},
             {'lab': 'NYCFC DC (derived)', 'price': -262, 'grp': 'B',
              't': '2026-08-17T23:30Z'}]
    _v, _m = gate_live([dict(_twin[0])], _twin, now=_now)
    chk(_v == 'PASS' and 'still on the board' in _m,
        "the twin-fixture label grades ITS OWN start time, not the other one")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1

if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

#!/usr/bin/env python3
"""socbase.py — map an odds-API competition to its empirical base rates.

sochist.py measures 40347 matches but names leagues the way openfootball does;
the board names them the way The Odds API does. This is the join, and it is a
hand-written table on purpose: a fuzzy name match between two vocabularies is
exactly the kind of silent mis-join that would price a Championship leg off
Eredivisie numbers and never say a word.

The ABSENCES matter more than the matches. Leagues Cup, MLS, and every UEFA
qualifying round have NO row in the history at all, and those are the
competitions today's money was actually on. A missing entry returns None and
callers must say "no data" rather than reaching for the pooled number --
pooling across leagues is what this whole file exists to stop.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

# odds-API key -> sochist league name. None means MEASURED ABSENT: the
# competition is real, we know it is not in openfootball, and the honest
# answer is no prior rather than a borrowed one.
MAP = {
    "soccer_epl": "England Premier League",
    "soccer_efl_champ": "England Championship",
    "soccer_spain_la_liga": "Spain La Liga",
    "soccer_italy_serie_a": "Italy Serie A",
    "soccer_germany_bundesliga": "Germany Bundesliga",
    "soccer_france_ligue_one": "France Ligue 1",
    "soccer_netherlands_eredivisie": "Netherlands Eredivisie",
    "soccer_portugal_primeira_liga": "Portugal Primeira Liga",
    "soccer_austria_bundesliga": "Austria Bundesliga",
    "soccer_belgium_first_div": "Belgium Pro League",
    "soccer_mexico_ligamx": "Mexico Liga MX",
    # --- measured absent. Named explicitly so a future reader knows the gap was
    # checked rather than overlooked, and so the count of untagged leagues is
    # not mistaken for a mapping bug.
    "soccer_concacaf_leagues_cup": None,      # MLS v Liga MX, no rows anywhere
    "soccer_usa_mls": None,
    "soccer_uefa_champs_league_qualification": None,
    "soccer_conmebol_copa_libertadores": None,
    "soccer_conmebol_copa_sudamericana": None,
    "soccer_argentina_primera_division": None,
    "soccer_brazil_campeonato": None,
}
# Nearest scoring environment when there is no direct row. A PROXY IS NOT DATA:
# it is a stated assumption, and every caller must print which proxy it used.
PROXY = {
    "soccer_concacaf_leagues_cup": ("Mexico Liga MX",
                                    "MLS v Liga MX; only the Liga MX half is measured"),
    "soccer_usa_mls": ("Mexico Liga MX", "same continent, similar scoring era"),
}


# Leagues measured by sococalib.py -- football-data.co.uk, results WITH closing
# odds. These were 'measured absent' when only openfootball existed; now MLS
# alone is 6085 matches. Key discovery in the numbers: Argentina draws 30.2%
# of the time (pooled Europe: 25.2%) at 2.23 goals a game -- a DC and an under
# are structurally STRONGER there than anywhere else on the board.
CALIB = {
    # second tiers + Turkey/Greece (8/17): three of the five unmeasured legs
    # on that afternoon's live slip were Segunda; the league was one dict
    # entry away from measured the whole time.
    'soccer_spain_segunda_division': 'Spain Segunda',
    'soccer_turkey_super_league': 'Turkey Super Lig',
    'soccer_greece_super_league': 'Greece Super League',
    'soccer_germany_bundesliga2': 'Germany Bundesliga 2',
    'soccer_italy_serie_b': 'Italy Serie B',
    'soccer_france_ligue_two': 'France Ligue 2',
    'soccer_england_league1': 'England League One',
    'soccer_england_league2': 'England League Two',
    'soccer_usa_mls': 'USA MLS',
    'soccer_mexico_ligamx': 'Mexico Liga MX',
    'soccer_argentina_primera_division': 'Argentina Primera',
    'soccer_brazil_campeonato': 'Brazil Serie A',
    'soccer_japan_j_league': 'Japan J-League',
    'soccer_china_superleague': 'China Super League',
    'soccer_denmark_superliga': 'Denmark Superliga',
    'soccer_finland_veikkausliiga': 'Finland Veikkausliiga',
    'soccer_norway_eliteserien': 'Norway Eliteserien',
    'soccer_poland_ekstraklasa': 'Poland Ekstraklasa',
    'soccer_russia_premier_league': 'Russia Premier League',
    'soccer_sweden_allsvenskan': 'Sweden Allsvenskan',
    'soccer_switzerland_superleague': 'Switzerland Super League',
}


def _calib(name):
    """sococalib league row reshaped to the sochist result contract."""
    try:
        with open(os.path.join(HERE, 'sococalib.json')) as fh:
            c = json.load(fh)
    except Exception:
        return None
    b = (c.get('leagues') or {}).get(name)
    if not b:
        return None
    return {'result': {'draw': b['draw'], 'home': b['home'], 'away': b['away'],
                       'mean_goals': b['mean_goals'], 'n': b['n']},
            'under': b.get('under'), 'src': 'sococalib'}


# socextra: leagues football-data.co.uk does not publish at all (Colombia,
# Peru and whatever else Wikipedia's results matrices yield). Kept as its own
# source and its own lookup so the provenance never blurs -- these rows are
# read off a season grid, not off closing odds, so they carry no de-vigged
# market and MUST NOT be compared against sococalib rows as if they were.
EXTRA = {
    "soccer_colombia_primera_a": "Colombia Primera A",
    "soccer_peru_liga_1":        "Peru Liga 1",
    "soccer_chile_campeonato":   "Chile Liga de Primera",
    "soccer_bolivia_primera":    "Bolivia Profesional",
    "soccer_uruguay_primera_division": "Uruguay Primera",
}


def _extra(name):
    try:
        with open(os.path.join(HERE, 'socextra.json')) as fh:
            d = json.load(fh)
    except Exception:
        return None
    v = d.get(name)
    if not v or not v.get('rates'):
        return None
    r = dict(v['rates'])
    r['src'] = 'socextra'
    return r


def extra_splits(name):
    """(home, away, h2h) for a socextra league, or None. The two signals a
    dateless results grid can honestly support -- never form."""
    try:
        with open(os.path.join(HERE, 'socextra.json')) as fh:
            d = json.load(fh)
    except Exception:
        return None
    v = d.get(name)
    return v.get('splits') if v else None


def rates(key):
    """(league_name, dict, note) or (None, None, why) if nothing fits."""
    if key in CALIB:
        r = _calib(CALIB[key])
        if r:
            return CALIB[key], r, None
    if key in EXTRA:
        r = _extra(EXTRA[key])
        if r:
            n = EXTRA[key]
            note = ('socextra: measured off Wikipedia season grids, NOT '
                    'closing odds -- no de-vig')
            # Do not claim "no form" for a league that has it: Chile and
            # Bolivia carry dated Spanish rounds, Colombia's dates stop in
            # May, Peru has none. socsignals gates on the age; say only
            # what is true here.
            try:
                with open(os.path.join(HERE, 'socextra.json')) as fh:
                    if not (json.load(fh).get(n) or {}).get('form'):
                        note += '; no dated results, so no form for this league'
            except Exception:
                pass
            return n, r, note
    if key == 'soccer_concacaf_leagues_cup':
        a, b = _calib('USA MLS'), _calib('Mexico Liga MX')
        if a and b:
            blend = {'result': {k: round((a['result'][k] + b['result'][k]) / 2, 5)
                                for k in ('draw', 'home', 'away', 'mean_goals')},
                     'src': 'blend'}
            blend['result']['n'] = a['result']['n'] + b['result']['n']
            return 'MLS+Liga MX blend', blend, (
                'PROXY blend for the Leagues Cup: both halves now MEASURED '
                '(6085 MLS + 4682 Liga MX matches), averaged evenly')
    try:
        with open(os.path.join(HERE, 'sochist.json')) as fh:
            h = json.load(fh)
    except Exception:
        return None, None, 'sochist.json unreadable'
    name = MAP.get(key)
    if name and name in h['leagues']:
        return name, h['leagues'][name], None
    if key in PROXY:
        pn, why = PROXY[key]
        if pn in h['leagues']:
            return pn, h['leagues'][pn], f'PROXY for {key}: {why}'
    if key not in MAP:
        return None, None, f'{key} is not in socbase.MAP -- unmapped, not absent'
    return None, None, f'{key} has no historical rows (measured absent)'


if __name__ == '__main__':
    import sys
    # --selftest used to fall through as a LEAGUE KEY and print
    # "--selftest is not in socbase.MAP", which reads exactly like a real
    # coverage answer. A flag that silently means something else is a trap;
    # socbase has no suite of its own, so say that.
    if '--selftest' in sys.argv:
        print('socbase has no selftest of its own -- it is covered through '
              'preflight (82), edge (24) and socextra (40). '
              'Run: python3 socbase.py <odds_api_key> to inspect one league.')
        raise SystemExit(0)
    for k in (sys.argv[1:] or list(MAP) + list(EXTRA)):
        n, r, note = rates(k)
        if r:
            print(f"  {k:<44} {n:<26} draw {r['result']['draw']*100:.1f}%  "
                  f"goals {r['result']['mean_goals']:.2f}" + (f"   [{note}]" if note else ""))
        else:
            print(f"  {k:<44} -- {note}")

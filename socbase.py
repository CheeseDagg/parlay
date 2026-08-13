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
    'soccer_usa_mls': 'USA MLS',
    'soccer_mexico_ligamx': 'Mexico Liga MX',
    'soccer_argentina_primera_division': 'Argentina Primera',
    'soccer_brazil_campeonato': 'Brazil Serie A',
    'soccer_japan_j_league': 'Japan J-League',
    'soccer_china_superleague': 'China Super League',
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


def rates(key):
    """(league_name, dict, note) or (None, None, why) if nothing fits."""
    if key in CALIB:
        r = _calib(CALIB[key])
        if r:
            return CALIB[key], r, None
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
    for k in (sys.argv[1:] or list(MAP)):
        n, r, note = rates(k)
        if r:
            print(f"  {k:<44} {n:<26} draw {r['result']['draw']*100:.1f}%  "
                  f"goals {r['result']['mean_goals']:.2f}" + (f"   [{note}]" if note else ""))
        else:
            print(f"  {k:<44} -- {note}")

#!/usr/bin/env python3
"""ufcform.py — recent fights for everyone on the card, from the full record.

    python3 ufcform.py                          # everyone in fights.CARD
    python3 ufcform.py "Islam Makhachev" ...
    python3 ufcform.py --selftest

fights.py carries hand-sourced career splits for Saturday's card; this pulls
each fighter's actual last five bouts from the complete UFC results file --
opponent, result, method, year -- plus how their WINS end and how their LOSSES
end. The split matters for method props: a fighter whose losses are all
decisions is durable in exactly the way that beats an opponent's KO prop, and
that is a different fact from his own finish rate.

Name matching is the hazard again and again it is not allowed to be silent:
every card name that cannot be found in the record is listed as UNMATCHED.
Nicknames and diacritics fold; a name that matches two different fighters is
refused rather than guessed.
"""
import csv, io, json, os, sys, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'ufcform.json')
RAW = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def norm(name):
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return ' '.join(''.join(c if c.isalnum() or c == ' ' else ' '
                            for c in s).split())


def norm_method(m):
    m = (m or '').lower()
    if 'decision' in m:
        return 'dec'
    if 'ko' in m or 'tko' in m or 'doctor' in m:
        return 'ko'
    if 'submission' in m:
        return 'sub'
    return 'other'


def parse_bouts(results_text, years):
    """[{a, b, winner, method, year}] -- a/b as printed, winner 'a'/'b'."""
    out = []
    for row in csv.DictReader(io.StringIO(results_text)):
        bout = (row.get('BOUT') or '')
        oc = (row.get('OUTCOME') or '').strip()
        if ' vs. ' not in bout or oc not in ('W/L', 'L/W'):
            continue
        a, b = [x.strip() for x in bout.split(' vs. ', 1)]
        out.append({'a': a, 'b': b, 'winner': 'a' if oc == 'W/L' else 'b',
                    'method': norm_method(row.get('METHOD')),
                    'year': years.get((row.get('EVENT') or '').strip())})
    return out


def parse_events(text):
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get('EVENT') or '').strip()
        yr = None
        for tok in (row.get('DATE') or '').replace(',', ' ').split():
            if tok.isdigit() and len(tok) == 4:
                yr = int(tok)
        if name and yr:
            out[name] = yr
    return out


def record_of(bouts, name):
    """(fights_newest_first, how) for one fighter, or (None, why)."""
    q = norm(name)
    mine = []
    names = set()
    for bt in bouts:
        for side, opp in (('a', 'b'), ('b', 'a')):
            if norm(bt[side]) == q:
                names.add(bt[side])
                mine.append({'opp': bt[opp], 'win': bt['winner'] == side,
                             'method': bt['method'], 'year': bt['year'] or 0})
    if not mine:
        return None, 'unmatched'
    if len(names) > 1:
        return None, f'ambiguous: {sorted(names)}'
    mine.sort(key=lambda f: f['year'])
    return mine[::-1], sorted(names)[0]


def profile(fights):
    wins = [f for f in fights if f['win']]
    losses = [f for f in fights if not f['win']]
    def mix(fs):
        n = len(fs)
        if not n:
            return None
        return {m: round(sum(1 for f in fs if f['method'] == m) / n, 3)
                for m in ('dec', 'ko', 'sub')} | {'n': n}
    return {'record': f"{len(wins)}-{len(losses)} in UFC",
            'win_by': mix(wins), 'lose_by': mix(losses)}


def card_names():
    try:
        import fights
        out = []
        for fav, d in fights.CARD.items():
            out.append(fav)
            if d.get('opp'):
                out.append(d['opp'])
        return out
    except Exception:
        try:
            from times import FIGHT_START
            return list(FIGHT_START)
        except Exception:
            return []


def main():
    years = parse_events(get(f"{RAW}/ufc_event_details.csv"))
    bouts = parse_bouts(get(f"{RAW}/ufc_fight_results.csv"), years)
    want = [a for a in sys.argv[1:] if not a.startswith('--')] or card_names()
    print(f"{len(bouts)} decided bouts on record; {len(want)} names requested\n")
    table, miss = {}, []
    for name in want:
        fights_, how = record_of(bouts, name)
        if fights_ is None:
            miss.append(f"{name} ({how})")
            continue
        pr = profile(fights_)
        last5 = fights_[:5]
        line = '  '.join(f"{'W' if f['win'] else 'L'}-{f['method']}({f['year']}) "
                         f"{f['opp'][:14]}" for f in last5)
        print(f"  {name:<24} {pr['record']:<14} {line}")
        wb, lb = pr['win_by'], pr['lose_by']
        if wb:
            print(f"  {'':<24} wins:  dec {wb['dec']*100:.0f}% ko {wb['ko']*100:.0f}% "
                  f"sub {wb['sub']*100:.0f}%  (n={wb['n']})")
        if lb:
            print(f"  {'':<24} loses: dec {lb['dec']*100:.0f}% ko {lb['ko']*100:.0f}% "
                  f"sub {lb['sub']*100:.0f}%  (n={lb['n']})")
        table[name] = {'profile': pr,
                       'last5': last5, 'matched_as': how}
    if miss:
        print(f"\n  UNMATCHED: " + '; '.join(miss))
        print("  -- debuts and Contender Series fighters have no UFC record; "
              "that is information, not an error.")
    with open(OUT, 'w') as fh:
        json.dump({'teams': table, 'unmatched': miss}, fh, indent=1)
    print(f"\nwrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    ev = "EVENT,URL,DATE\nUFC 1,u,\"March 1, 2020\"\nUFC 2,u,\"June 5, 2023\"\n"
    years = parse_events(ev)
    res = ("EVENT,BOUT,OUTCOME,WEIGHTCLASS,METHOD\n"
           "UFC 1,Islam Makhachev vs. Bobby Green,W/L,Lightweight Bout,KO/TKO\n"
           "UFC 2,Charles Oliveira vs. Islam Makhachev,L/W,Lightweight Title Bout,Submission\n"
           "UFC 2,A vs. B,D/D,Lightweight Bout,Decision - Majority\n")
    bouts = parse_bouts(res, years)
    chk(len(bouts) == 2, "draws drop; decided bouts carry both names and a year")
    f, how = record_of(bouts, 'islam makhachev')
    chk(how == 'Islam Makhachev' and len(f) == 2 and f[0]['year'] == 2023,
        "a fighter's record folds both sides of the BOUT column, newest first")
    chk(f[0]['win'] and f[0]['method'] == 'sub' and f[0]['opp'] == 'Charles Oliveira',
        "L/W means the SECOND-named fighter won -- attribution is per side, "
        "and getting it backwards would invert every record in the file")
    pr = profile(f)
    chk(pr['record'] == '2-0 in UFC' and pr['lose_by'] is None,
        "an unbeaten fighter has no losses profile rather than a zeroed one")
    bouts2 = bouts + [{'a': 'Jon Smith', 'b': 'X', 'winner': 'a',
                       'method': 'ko', 'year': 2021},
                      {'a': 'Jon  Smith', 'b': 'Y', 'winner': 'a',
                       'method': 'ko', 'year': 2022}]
    chk(record_of(bouts2, 'Bobby Green')[0][0]['win'] is False,
        "the loser's side of a W/L bout records a loss")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

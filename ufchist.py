#!/usr/bin/env python3
"""ufchist.py — how UFC fights actually end, by division, from every recorded bout.

    python3 ufchist.py
    python3 ufchist.py --selftest

Rule 27 calls method props "a distinct failure mode" and rule 9 exists
because of them -- but both rules argue from losses, not from base rates.
Ryan bets method props anyway ("These are my plays so there's no floor"), and
UFC 330 is Saturday with two of his method legs on the main event. The honest
upgrade is not another warning, it is the denominator: what fraction of
lightweight fights actually end by decision, KO, submission.

Greco1899/scrape_ufc_stats republishes every UFC bout's result -- method,
weight class, round -- and its event index carries dates, so the rates can be
computed on the MODERN era (2015+) rather than averaged across two decades of
rule changes. Title fights are split out: five championship rounds and elite
durability change how fights end, and a main-event method prop is priced
against exactly that population.

WHAT THIS IS NOT: fighter-specific. Islam Makhachev's own finish rate is not
in here, only the population his fight is drawn from. A base rate is the
floor of an argument, not the argument.
"""
import csv, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'ufchist.json')
RAW = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"
UA = "Mozilla/5.0 (compatible; parlay-research/1.0)"
MODERN = 2015


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def norm_method(m):
    """'Decision - Split' -> dec, 'KO/TKO' -> ko, doctor stoppage counts as ko;
    DQ / overturned / could-not-continue are 'other', never silently dropped."""
    m = (m or '').lower()
    if 'decision' in m:
        return 'dec'
    if 'ko' in m or 'tko' in m or 'doctor' in m:
        return 'ko'
    if 'submission' in m:
        return 'sub'
    return 'other'


def norm_class(wc):
    """('Lightweight', title?) from strings like 'UFC Lightweight Title Bout',
    "Women's Strawweight Bout". Women's divisions keep their prefix -- a
    women's flyweight and a men's flyweight are different populations."""
    wc = (wc or '').strip()
    title = 'title' in wc.lower()
    w = wc.lower()
    for d in ('strawweight', 'flyweight', 'bantamweight', 'featherweight',
              'lightweight', 'welterweight', 'middleweight',
              'light heavyweight', 'heavyweight'):
        if d in w:
            name = d.title()
            if "women" in w:
                name = "Women's " + name
            return name, title
    return None, title


def parse_results(text):
    """[{event, division, title, method}] for decided bouts. Draws and NCs are
    excluded: a method prop on a fight that ends NC pushes, it does not hit."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        oc = (row.get('OUTCOME') or '').strip()
        if oc not in ('W/L', 'L/W'):
            continue
        div, title = norm_class(row.get('WEIGHTCLASS'))
        if div is None:
            continue
        out.append({'event': (row.get('EVENT') or '').strip(),
                    'division': div, 'title': title,
                    'method': norm_method(row.get('METHOD'))})
    return out


def parse_events(text):
    """{event name: year} from the event index."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get('EVENT') or '').strip()
        date = (row.get('DATE') or '').strip()
        yr = None
        for tok in date.replace(',', ' ').split():
            if tok.isdigit() and len(tok) == 4:
                yr = int(tok)
        if name and yr:
            out[name] = yr
    return out


def rates(bouts):
    n = len(bouts)
    if not n:
        return None
    c = {'dec': 0, 'ko': 0, 'sub': 0, 'other': 0}
    for b in bouts:
        c[b['method']] += 1
    return {'n': n, **{k: round(v / n, 4) for k, v in c.items()}}


def main():
    bouts = parse_results(get(f"{RAW}/ufc_fight_results.csv"))
    years = parse_events(get(f"{RAW}/ufc_event_details.csv"))
    for b in bouts:
        b['year'] = years.get(b['event'])
    modern = [b for b in bouts if b['year'] and b['year'] >= MODERN]
    print(f"{len(bouts)} decided bouts, {len(modern)} in the modern era ({MODERN}+)\n")
    divs = {}
    for b in modern:
        divs.setdefault(b['division'], []).append(b)
    print(f"  {'division':<24}{'n':>6}{'dec':>7}{'ko':>7}{'sub':>7}{'other':>7}")
    table = {}
    for d in sorted(divs, key=lambda k: -len(divs[k])):
        r = rates(divs[d])
        table[d] = r
        print(f"  {d:<24}{r['n']:>6}{r['dec']*100:>6.1f}%{r['ko']*100:>6.1f}%"
              f"{r['sub']*100:>6.1f}%{r['other']*100:>6.1f}%")
    t = rates([b for b in modern if b['title']])
    nt = rates([b for b in modern if not b['title']])
    print(f"\n  title fights     n={t['n']:<5} dec {t['dec']*100:.1f}%  ko {t['ko']*100:.1f}%  sub {t['sub']*100:.1f}%")
    print(f"  non-title        n={nt['n']:<5} dec {nt['dec']*100:.1f}%  ko {nt['ko']*100:.1f}%  sub {nt['sub']*100:.1f}%")
    with open(OUT, 'w') as fh:
        json.dump({'modern_since': MODERN, 'bouts': len(modern),
                   'divisions': table, 'title': t, 'non_title': nt}, fh, indent=1)
    print(f"\nwrote {OUT}")
    return 0


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    chk(norm_method('Decision - Split') == 'dec' and norm_method('KO/TKO') == 'ko'
        and norm_method('TKO - Doctor\'s Stoppage') == 'ko'
        and norm_method('Submission') == 'sub' and norm_method('DQ') == 'other',
        "methods normalise: doctor stoppage is a KO-family ending, DQ is other")
    chk(norm_class('UFC Lightweight Title Bout') == ('Lightweight', True),
        "a title bout is recognised and split out -- five rounds change endings")
    chk(norm_class("Women's Strawweight Bout") == ("Women's Strawweight", False),
        "women's divisions keep their prefix; they are a different population")
    chk(norm_class('Light Heavyweight Bout')[0] == 'Light Heavyweight',
        "light heavyweight does not fall through to heavyweight")

    csvtext = (
        "EVENT,BOUT,OUTCOME,WEIGHTCLASS,METHOD,ROUND,TIME\n"
        "UFC 1,A vs. B,W/L,Lightweight Bout,KO/TKO,1,1:00\n"
        "UFC 1,C vs. D,D/D,Lightweight Bout,Decision - Majority,3,5:00\n"
        "UFC 1,E vs. F,NC/NC,Welterweight Bout,Overturned,2,3:00\n"
        "UFC 1,G vs. H,L/W,UFC Flyweight Title Bout,Submission,4,2:11\n")
    bouts = parse_results(csvtext)
    chk(len(bouts) == 2,
        "draws and no-contests are excluded -- a method prop on an NC pushes, "
        "and counting it as an ending would dilute every rate")
    chk(bouts[1]['title'] and bouts[1]['method'] == 'sub',
        "the L/W bout still counts: the FIGHT ended by submission either way")

    ev = ("EVENT,URL,DATE,LOCATION\n"
          "UFC 1,u,\"November 12, 1993\",Denver\n"
          "UFC 300,u,\"April 13, 2024\",Vegas\n")
    yrs = parse_events(ev)
    chk(yrs == {'UFC 1': 1993, 'UFC 300': 2024},
        "event dates parse to years, which is what the modern-era cut needs")

    r = rates([{'method': 'dec'}, {'method': 'dec'}, {'method': 'ko'},
               {'method': 'sub'}])
    chk(r['dec'] == 0.5 and r['n'] == 4, "rates sum over the four buckets")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())

#!/usr/bin/env python3
"""idx.py — what openfootball actually carries, by season and league.

Written because the goal-under comparison was drawn against the wrong
population once already. Before any empirical claim about a competition, know
whether that competition is in the data, whether the CURRENT season is in it
(form needs that, not history), and what stands in when it is not.
"""
import json, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (compatible; parlay-research/1.0)"}


def g(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))


seasons = []
try:
    root = g("https://api.github.com/repos/openfootball/football.json/contents/")
    seasons = sorted(x['name'] for x in root if x['type'] == 'dir' and '-' in x['name'])
except Exception as e:
    print("root listing failed:", type(e).__name__)
print(f"seasons present: {' '.join(seasons)}\n")
for s in seasons[-4:]:
    try:
        d = g(f"https://api.github.com/repos/openfootball/football.json/contents/{s}")
        files = sorted(x['name'].replace('.json', '') for x in d if x['name'].endswith('.json'))
        print(f"{s}: {len(files)} leagues -- {' '.join(files)}")
        # how complete is the newest season? an empty shell is not form data
        if s == seasons[-1]:
            for code in files[:40]:
                try:
                    doc = g(f"https://raw.githubusercontent.com/openfootball/football.json/master/{s}/{code}.json")
                    played = sum(1 for m in doc.get('matches', [])
                                 if (m.get('score') or {}).get('ft'))
                    if played:
                        print(f"    {code:<10} {played:>4} played of {len(doc.get('matches', []))}")
                except Exception:
                    pass
    except Exception as e:
        print(s, type(e).__name__)

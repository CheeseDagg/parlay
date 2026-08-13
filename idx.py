import json, urllib.request
UA={"User-Agent":"Mozilla/5.0 (compatible; parlay-research/1.0)"}
def g(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30))
for season in ("2024-25","2023-24"):
    try:
        d=g(f"https://api.github.com/repos/openfootball/football.json/contents/{season}")
        print(f"{season}: " + ' '.join(sorted(x['name'].replace('.json','') for x in d if x['name'].endswith('.json'))))
    except Exception as e:
        print(season, type(e).__name__)
